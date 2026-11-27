#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIRECTORY="/opt/sensor-spike"
RESULTS_DIRECTORY="/var/lib/sensor-spike/results"
AVAILABILITY_FILE="$RESULTS_DIRECTORY/availability.env"
ACTIVE_RULES_FILE="$RESULTS_DIRECTORY/auditd-active.rules"
SPIKE_AUDIT_KEYS=(agent_exec agent_file agent_net)
AGENT_USER="agentuser"
ACTION="${1:-}"
SENSOR="${2:-all}"

read_availability_flag() {
  local flag_value=""
  if [[ -f "$AVAILABILITY_FILE" ]]; then
    flag_value="$(grep -m1 -E "^$1=(yes|no)$" "$AVAILABILITY_FILE" | cut -d= -f2 || true)"
  fi
  echo "${flag_value:-no}"
}

TETRAGON_AVAILABLE="$(read_availability_flag TETRAGON_AVAILABLE)"
AUDITD_AVAILABLE="$(read_availability_flag AUDITD_AVAILABLE)"

print_usage() {
  cat >&2 <<'USAGE'
usage: manage_sensor.sh <enable|disable|verify> <tetragon|auditd|all>
       manage_sensor.sh status
       manage_sensor.sh recommend
USAGE
  exit 1
}

require_root() {
  if [[ $EUID -ne 0 ]]; then
    echo "Run with sudo: sudo $0 $*" >&2
    exit 1
  fi
}

sensor_is_available() {
  case "$1" in
    tetragon) [[ "$TETRAGON_AVAILABLE" == "yes" ]] ;;
    auditd) [[ "$AUDITD_AVAILABLE" == "yes" ]] ;;
  esac
}

enable_tetragon() {
  systemctl start tetragon
  sleep 5
  echo "tetragon: enabled (policies from /etc/tetragon/tetragon.tp.d)"
}

disable_tetragon() {
  systemctl stop tetragon 2> /dev/null || true
  echo "tetragon: disabled"
}

verify_tetragon() {
  local marker events_file stream_pid
  marker="tetragon-verify-$RANDOM"
  events_file="$(mktemp)"
  if ! systemctl is-active --quiet tetragon; then
    echo "tetragon verify: FAIL (service not active)"
    return 1
  fi
  tetra tracingpolicy list
  timeout 6 tetra getevents -o json > "$events_file" &
  stream_pid=$!
  sleep 2
  sudo -u "$AGENT_USER" /bin/echo "$marker" > /dev/null
  wait "$stream_pid" || true
  if grep -q "$marker" "$events_file"; then
    echo "tetragon verify: PASS (exec event seen for $marker)"
  else
    echo "tetragon verify: FAIL (no exec event seen for $marker)"
    return 1
  fi
}

remove_spike_auditd_rules() {
  local rule_line
  local rule_arguments=()
  [[ -f "$ACTIVE_RULES_FILE" ]] || return 0
  while IFS= read -r rule_line; do
    [[ "$rule_line" == -a* ]] || continue
    read -r -a rule_arguments <<< "$rule_line"
    rule_arguments[0]="-d"
    auditctl "${rule_arguments[@]}" > /dev/null 2>&1 || true
  done < "$ACTIVE_RULES_FILE"
}

count_spike_auditd_rules() {
  auditctl -l 2> /dev/null | grep -cE 'agent_(exec|file|net)' || true
}

enable_auditd() {
  local audit_key loaded_rules
  mkdir -p "$RESULTS_DIRECTORY"
  remove_spike_auditd_rules
  sed "s/AGENT_UID/$(id -u "$AGENT_USER")/" "$INSTALL_DIRECTORY/auditd.rules" > "$ACTIVE_RULES_FILE"
  auditctl -c -R "$ACTIVE_RULES_FILE" > /dev/null || echo "auditd: some rules did not load (expected for syscalls this architecture lacks)" >&2
  loaded_rules="$(auditctl -l)"
  for audit_key in "${SPIKE_AUDIT_KEYS[@]}"; do
    if ! grep -q "$audit_key" <<< "$loaded_rules"; then
      echo "auditd: no rule loaded for $audit_key" >&2
      return 1
    fi
  done
  echo "auditd: enabled ($(count_spike_auditd_rules) spike rules for uid $(id -u "$AGENT_USER"))"
}

disable_auditd() {
  remove_spike_auditd_rules
  echo "auditd: disabled (spike rules removed; other rules and existing logs untouched)"
}

verify_auditd() {
  local marker
  marker="auditd-verify-$RANDOM"
  auditctl -l | grep -E 'agent_(exec|file|net)' || true
  sudo -u "$AGENT_USER" /bin/echo "$marker" > /dev/null
  sleep 2
  if ausearch -i -k agent_exec 2> /dev/null | grep -q "$marker"; then
    echo "auditd verify: PASS (execve record seen for $marker)"
  else
    echo "auditd verify: FAIL (no execve record seen for $marker)"
    return 1
  fi
}

run_for_sensors() {
  local action="$1" sensor="$2" each_sensor
  case "$sensor" in
    tetragon|auditd)
      if [[ "$action" != "disable" ]] && ! sensor_is_available "$sensor"; then
        echo "$sensor is unavailable on this host (see $AVAILABILITY_FILE)" >&2
        return 1
      fi
      "${action}_${sensor}"
      ;;
    all)
      for each_sensor in tetragon auditd; do
        if [[ "$action" == "disable" ]] || sensor_is_available "$each_sensor"; then
          "${action}_${each_sensor}"
        else
          echo "$each_sensor: skipped (unavailable)"
        fi
      done
      ;;
    *) print_usage ;;
  esac
}

show_status() {
  echo "tetragon service: $(systemctl is-active tetragon 2> /dev/null || true)"
  echo "auditd spike rules loaded: $(count_spike_auditd_rules)"
  echo "availability: tetragon=$TETRAGON_AVAILABLE auditd=$AUDITD_AVAILABLE"
}

recommend_sensor() {
  local reasons=()
  [[ -e /sys/kernel/btf/vmlinux ]] || reasons+=("BTF missing at /sys/kernel/btf/vmlinux")
  [[ "$TETRAGON_AVAILABLE" == "yes" ]] || reasons+=("Tetragon not installed or its service failed to start (see tetragon-startup-error.txt)")

  if ((${#reasons[@]} == 0)); then
    echo "recommended sensor: tetragon"
  elif [[ "$AUDITD_AVAILABLE" == "yes" ]]; then
    echo "recommended sensor: auditd (fallback)"
    printf '  reason: %s\n' "${reasons[@]}"
  else
    echo "recommended sensor: none (auditd is also unavailable)"
    printf '  reason: %s\n' "${reasons[@]}"
  fi
  echo "Also switch to auditd if, in summary.txt, Tetragon captures under 95% of the known activities while auditd meets it."
}

case "$ACTION" in
  enable|disable|verify)
    require_root "$@"
    run_for_sensors "$ACTION" "$SENSOR"
    ;;
  status) show_status ;;
  recommend) recommend_sensor ;;
  *) print_usage ;;
esac
