#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIRECTORY="/opt/sensor-spike"
RESULTS_DIRECTORY="/var/tmp/sensor-spike-results"
AVAILABILITY_FILE="$RESULTS_DIRECTORY/availability.env"
AGENT_USER="agentuser"
ACTION="${1:-}"
SENSOR="${2:-all}"
TETRAGON_AVAILABLE="no"
AUDITD_AVAILABLE="no"

if [[ -f "$AVAILABILITY_FILE" ]]; then
  # shellcheck source=/dev/null
  source "$AVAILABILITY_FILE"
fi

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

enable_auditd() {
  local active_rules_file="$RESULTS_DIRECTORY/auditd-active.rules"
  mkdir -p "$RESULTS_DIRECTORY"
  sed "s/AGENT_UID/$(id -u "$AGENT_USER")/" "$INSTALL_DIRECTORY/auditd.rules" > "$active_rules_file"
  auditctl -D > /dev/null
  auditctl -R "$active_rules_file" > /dev/null
  echo "auditd: enabled ($(auditctl -l | wc -l) rules for uid $(id -u "$AGENT_USER"))"
}

disable_auditd() {
  auditctl -D > /dev/null 2>&1 || true
  echo "auditd: disabled (rules cleared)"
}

verify_auditd() {
  local marker
  marker="auditd-verify-$RANDOM"
  auditctl -l
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
  echo "auditd rules loaded: $(auditctl -l 2> /dev/null | grep -vc 'No rules' || true)"
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
