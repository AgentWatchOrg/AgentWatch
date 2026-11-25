#!/usr/bin/env bash
set -euo pipefail

BUNDLE_DIRECTORY="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIRECTORY="/opt/sensor-spike"
RESULTS_DIRECTORY="/var/tmp/sensor-spike-results"
TRACING_POLICY_DIRECTORY="/etc/tetragon/tetragon.tp.d"
AGENT_USER="agentuser"
TETRAGON_VERSION="${TETRAGON_VERSION:-}"
HOST_INFO_FILE="$RESULTS_DIRECTORY/host-info.txt"
AVAILABILITY_FILE="$RESULTS_DIRECTORY/availability.env"
BUNDLE_FILES=(run_workload.sh compare_sensors.sh archive_results.sh manage_sensor.sh report_fields.sh sanitize_samples.sh auditd.rules)
TETRAGON_AVAILABLE="yes"
AUDITD_AVAILABLE="no"

require_root() {
  if [[ $EUID -ne 0 ]]; then
    echo "Run with sudo: sudo ./install_sensors.sh" >&2
    exit 1
  fi
}

is_wsl() {
  grep -qi microsoft /proc/version
}

require_systemd() {
  if [[ ! -d /run/systemd/system ]]; then
    cat >&2 <<'MESSAGE'
systemd is not running, and Tetragon is installed as a systemd service.
In WSL, add this to /etc/wsl.conf:

  [boot]
  systemd=true

Then run `wsl --shutdown` from Windows PowerShell and reopen Ubuntu.
MESSAGE
    exit 1
  fi
}

detect_tetragon_architecture() {
  case "$(uname -m)" in
    x86_64) echo "amd64" ;;
    aarch64) echo "arm64" ;;
    *) echo "Unsupported architecture: $(uname -m)" >&2; exit 1 ;;
  esac
}

record_host_info() {
  mkdir -p "$RESULTS_DIRECTORY"
  {
    echo "date: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "kernel: $(uname -r)"
    echo "architecture: $(uname -m)"
    echo "wsl: $(is_wsl && echo yes || echo no)"
    grep -E '^(PRETTY_NAME|VERSION_ID)=' /etc/os-release
    echo "cpus: $(nproc)"
    echo "memory: $(free -h | awk '/^Mem:/ {print $2}')"
  } > "$HOST_INFO_FILE"
}

check_btf_support() {
  if [[ -e /sys/kernel/btf/vmlinux ]]; then
    echo "btf: present" >> "$HOST_INFO_FILE"
  else
    echo "btf: MISSING" >> "$HOST_INFO_FILE"
    TETRAGON_AVAILABLE="no"
    echo "No BTF at /sys/kernel/btf/vmlinux: Tetragon cannot run here, so this host needs the auditd fallback." >&2
    echo "On WSL, see 'If BTF is missing' in infrastructure/sensor-spike/README.md." >&2
  fi
}

resolve_tetragon_version() {
  if [[ -z "$TETRAGON_VERSION" ]]; then
    TETRAGON_VERSION="$(curl -fsSL https://api.github.com/repos/cilium/tetragon/releases/latest | grep -m1 '"tag_name"' | cut -d'"' -f4)"
  fi
  echo "tetragon_version: $TETRAGON_VERSION" >> "$HOST_INFO_FILE"
}

install_tetragon() {
  local architecture download_directory tarball_url install_script
  architecture="$(detect_tetragon_architecture)"
  download_directory="$INSTALL_DIRECTORY/tetragon-download"
  tarball_url="https://github.com/cilium/tetragon/releases/download/${TETRAGON_VERSION}/tetragon-${TETRAGON_VERSION}-${architecture}.tar.gz"

  rm -rf "$download_directory"
  mkdir -p "$download_directory"
  curl -fsSL "$tarball_url" -o "$download_directory/tetragon.tar.gz"
  tar -xzf "$download_directory/tetragon.tar.gz" -C "$download_directory"

  install_script="$(find "$download_directory" -name install.sh | head -1)"
  (cd "$(dirname "$install_script")" && ./install.sh)
}

install_tracing_policies() {
  mkdir -p "$TRACING_POLICY_DIRECTORY"
  cp "$BUNDLE_DIRECTORY"/policies/*.yaml "$TRACING_POLICY_DIRECTORY/"
  systemctl restart tetragon || true
  sleep 5
  if systemctl is-active --quiet tetragon; then
    echo "tetragon_service: active" >> "$HOST_INFO_FILE"
    tetra tracingpolicy list >> "$HOST_INFO_FILE" 2>&1 || true
    tetra probe config >> "$HOST_INFO_FILE" 2>&1 || true
  else
    TETRAGON_AVAILABLE="no"
    journalctl -u tetragon -n 50 --no-pager > "$RESULTS_DIRECTORY/tetragon-startup-error.txt" 2>&1 || true
    echo "tetragon_service: FAILED (see tetragon-startup-error.txt)" >> "$HOST_INFO_FILE"
    echo "Tetragon did not start. See $RESULTS_DIRECTORY/tetragon-startup-error.txt" >&2
  fi
}

install_auditd() {
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq auditd
  systemctl enable --now auditd || true
  if auditctl -s > /dev/null 2>&1; then
    AUDITD_AVAILABLE="yes"
    echo "auditd: available" >> "$HOST_INFO_FILE"
  else
    echo "auditd: UNAVAILABLE (kernel audit support missing or auditd not running)" >> "$HOST_INFO_FILE"
    echo "auditd cannot talk to the kernel audit subsystem; the auditd comparison will be skipped." >&2
  fi
}

create_agent_user() {
  if ! id "$AGENT_USER" > /dev/null 2>&1; then
    useradd --create-home --shell /bin/bash "$AGENT_USER"
  fi
}

install_bundle_scripts() {
  local bundle_file
  mkdir -p "$INSTALL_DIRECTORY"
  for bundle_file in "${BUNDLE_FILES[@]}"; do
    cp "$BUNDLE_DIRECTORY/$bundle_file" "$INSTALL_DIRECTORY/"
  done
  chmod 755 "$INSTALL_DIRECTORY"/*.sh
  chmod 644 "$INSTALL_DIRECTORY/auditd.rules"
  chmod 755 "$INSTALL_DIRECTORY"
}

write_availability() {
  {
    echo "TETRAGON_AVAILABLE=$TETRAGON_AVAILABLE"
    echo "AUDITD_AVAILABLE=$AUDITD_AVAILABLE"
  } > "$AVAILABILITY_FILE"
}

require_root
record_host_info
require_systemd
DEBIAN_FRONTEND=noninteractive apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq curl jq
check_btf_support
if [[ "$TETRAGON_AVAILABLE" == "yes" ]]; then
  resolve_tetragon_version
  install_tetragon
  install_tracing_policies
fi
install_auditd
create_agent_user
install_bundle_scripts
write_availability

echo "Setup complete. Host info:"
cat "$HOST_INFO_FILE"
echo "Availability: tetragon=$TETRAGON_AVAILABLE auditd=$AUDITD_AVAILABLE"
echo "Next: sudo $INSTALL_DIRECTORY/manage_sensor.sh recommend"
