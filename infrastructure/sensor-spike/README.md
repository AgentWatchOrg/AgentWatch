# Sensor spike: Tetragon vs auditd on WSL

Scripts that install, compare, and document two Linux host sensors for AgentWatch: **Tetragon** (eBPF, preferred) and **auditd** (fallback). They cover tickets [#4](https://github.com/AgentWatchOrg/AgentWatch/issues/4) (spike: which sensor?) and [#57](https://github.com/AgentWatchOrg/AgentWatch/issues/57) (configure Tetragon and the auditd fallback).

This README is the WSL walkthrough. Script reference, enable/verify/disable commands, the condition for switching to auditd, options, and result files are in [documentation/infrastructure/sensor-spike.md](../../documentation/infrastructure/sensor-spike.md).

## Objective

AgentWatch watches what an AI agent (first target: Claude Code) does on a Linux host, flags suspicious behavior, and sends everything to Splunk. The sensor is the first stage:

```
AI agent on Linux host -> Sensor (Tetragon) -> Forwarder -> Backend -> Detection engine -> Splunk
```

The sensor must observe three activity types, attributable to the agent and its child processes: process execution, file access, and network connections. The spike answers, with evidence from a real host:

1. Does Tetragon work on this host, and what does it need (kernel, BTF, privileges)?
2. Does it capture all three activity types, and which fields identify the process, its lineage, and the activity?
3. What does auditd capture for the same activities, and where are the gaps?
4. What is the overhead of each, informally?
5. When must AgentWatch fall back to auditd?

Out of scope: the forwarder, session correlation, backend ingestion, custom eBPF programs, formal benchmarking, and any enforcement. AgentWatch observes and reports; it never blocks or remediates, so no Tetragon policy may contain enforcement actions (`Sigkill`, `Override`, and similar).

## Notes for an AI agent working from this README

You are probably running on the WSL host. Follow these rules:

- **Report only what you measured.** Every result must come from output you saw. If a command fails, report the exact error. Do not fill in expected numbers.
- **These items are unverified and may need fixing on first run:** the Tetragon release URL pattern (`tetragon-<tag>-<arch>.tar.gz`), the `/etc/tetragon/tetragon.tp.d/` policy directory, the policy YAML in `policies/` (schema varies by Tetragon version), the `ausearch --start` time format, and the JSON field names the scripts grep for (`"dport"` in Tetragon output, `lport=` in `ausearch -i` output). If counts come back 0 where you can see events, check these first against the installed version's docs at https://tetragon.io/docs/ and fix the script.
- **Never add enforcement actions** to a tracing policy.
- **Never put real secrets in the workload, samples, or commits.** Claude Code's API key goes in the shell environment of the manual session only.
- **Leave the host's audit setup alone.** The scripts never truncate audit logs and remove only their own rules (keys `agent_exec`, `agent_file`, `agent_net`). Do not add `auditctl -D` or clear `/var/log/audit`.
- **Commit only sanitized samples** (`samples-sanitized/`) and read them before committing. Redaction is pattern-based.
- **Ask before** installing a custom kernel or changing Windows settings.
- Loading eBPF programs and audit rules requires root (`sudo`). Record that as a host requirement.

How Tetragon works here, in short: it runs as a systemd service, loads eBPF programs into the kernel, and writes structured JSON events. It emits process exec and exit events by default. File and network events come from tracing policies (YAML) that attach kprobes to kernel functions: `security_file_open` for file opens and `tcp_connect` for outbound TCP connections. `tetra getevents -o json` streams events from the running service, and `tetra tracingpolicy list` shows loaded policies. Each process has an `exec_id`, and its parent's id is `parent_exec_id`, which gives process lineage with no extra work. auditd records raw syscalls instead: loaded rules (`auditctl`) log exec, open, and connect syscalls for one user, and `ausearch -i` renders the records. Its lineage is only `pid`/`ppid`.

## Prerequisites (Windows)

1. WSL2 with an Ubuntu 22.04 or 24.04 distribution. From PowerShell:
   ```powershell
   wsl --install -d Ubuntu-24.04
   wsl -l -v
   ```
   The `VERSION` column must show `2`.
2. systemd enabled. Inside Ubuntu, edit `/etc/wsl.conf`:
   ```ini
   [boot]
   systemd=true
   ```
   Then from PowerShell run `wsl --shutdown` and reopen Ubuntu. Check: `systemctl is-system-running` prints `running` or `degraded`.
3. Check the kernel features Tetragon needs, inside Ubuntu:
   ```bash
   uname -r
   ls /sys/kernel/btf/vmlinux
   ```
   `/sys/kernel/btf/vmlinux` must exist. If it does not, see [If BTF is missing](#if-btf-is-missing).

Work inside the Linux filesystem (`~`), not `/mnt/c`. Cloning from Windows can leave CRLF line endings that break the scripts.

## Run

```bash
git clone https://github.com/AgentWatchOrg/AgentWatch.git ~/AgentWatch
cd ~/AgentWatch/infrastructure/sensor-spike
sudo ./install_sensors.sh
```

`install_sensors.sh` records host facts, installs Tetragon (latest release; pin with `sudo TETRAGON_VERSION=v1.x.x ./install_sensors.sh`) and its policies, installs auditd, creates the unprivileged `agentuser`, and copies the scripts to `/opt/sensor-spike/`. It does not abort when one sensor is unavailable: it records availability in `/var/tmp/sensor-spike-results/availability.env` and continues with what works.

Then:

```bash
sudo /opt/sensor-spike/manage_sensor.sh recommend       # which sensor this host supports
sudo /opt/sensor-spike/manage_sensor.sh enable all
sudo /opt/sensor-spike/manage_sensor.sh verify all      # PASS means a known exec was seen
sudo /opt/sensor-spike/manage_sensor.sh disable all
sudo /opt/sensor-spike/compare_sensors.sh               # the full comparison
sudo /opt/sensor-spike/archive_results.sh
cp /var/tmp/sensor-spike-results.tar.gz /mnt/c/Users/<WindowsUserName>/Downloads/
```

### Manual Claude Code session

The scripted workload is synthetic. For a realistic sample, run Claude Code as `agentuser` while a sensor is enabled:

```bash
sudo /opt/sensor-spike/manage_sensor.sh enable tetragon
sudo -u agentuser -i
export ANTHROPIC_API_KEY=...   # this shell only; never in a file
# run claude in a scratch project, ask it to read files and run a curl
```

In a second terminal: `sudo tetra getevents -o json | tee /tmp/claude-session.json`. Check that the agent's child processes (for example a `curl` it spawns) trace back to the agent through `parent_exec_id`.

## What to deliver

For ticket #4:
1. A comparison against the design doc's Table 8.1 criteria (framework independence, bypass resistance, semantic context, overhead, team effort and risk, scenario coverage). Mark each preliminary rating confirmed or revised, with evidence from `summary.txt`.
2. Host requirements: distribution, kernel, BTF, privileges (root).
3. A recommendation and the open risks.
4. Follow-up implementation tickets.

For ticket #57:
1. The policies and rules in this folder (already checked in), adjusted to whatever actually worked.
2. Samples of all three event types from Tetragon, and the auditd run for the same activities. Commit sanitized samples under `infrastructure/sensor-spike/samples/`.
3. Coverage differences, stated per operation with the missing markers from `summary.txt` as evidence.
4. The field inventory from `fields-report.txt`: which fields give process identity, lineage, and activity details.

Record the outcome in `documentation/infrastructure/sensor-spike.md`, using the decision format from `.claude/skills/writing-project-documentation/SKILL.md`.

## If BTF is missing

The stock WSL2 kernel may not expose BTF. Sources I found disagree on whether it does (the Tetragon [FAQ](https://tetragon.io/docs/installation/faq/) only says it is required), so check with `ls /sys/kernel/btf/vmlinux` on your machine. If it is absent, the options are:

- **Accept the fallback.** The scripts continue with auditd only, which demonstrates the switch condition. Note that WSL2's stock kernel may also lack audit support; `install_sensors.sh` records that as `auditd: UNAVAILABLE`.
- **Build a WSL kernel with BTF (unverified steps).** Clone `microsoft/WSL2-Linux-Kernel`, start from its `Microsoft/config-wsl`, enable `CONFIG_DEBUG_INFO_BTF`, `CONFIG_BPF_SYSCALL`, `CONFIG_KPROBES`, and for the fallback `CONFIG_AUDIT` and `CONFIG_AUDITSYSCALL`, then build (needs `pahole` from the `dwarves` package). Point WSL at the image in `%UserProfile%\.wslconfig`:
  ```ini
  [wsl2]
  kernel=C:\\path\\to\\bzImage
  ```
  Then `wsl --shutdown`. Confirm with `ls /sys/kernel/btf/vmlinux` and `sudo tetra probe config` after installing Tetragon.
- **Use a different host.** A regular Ubuntu VM or an EC2 instance (see `documentation/infrastructure/web-server.md` for how AWS access works in this project) avoids the kernel work.

## Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| `systemd is not running` | Add `[boot] systemd=true` to `/etc/wsl.conf`, then `wsl --shutdown` |
| `bad interpreter` or `\r` errors | Scripts have Windows line endings; re-clone inside WSL, or `sed -i 's/\r$//' *.sh` |
| `No BTF at /sys/kernel/btf/vmlinux` | See [If BTF is missing](#if-btf-is-missing) |
| `tetragon_install: FAILED` in `host-info.txt` | Release lookup or download failed (rate limit, wrong URL pattern); pin a release with `TETRAGON_VERSION` |
| Tetragon service inactive | `journalctl -u tetragon -n 50`; check `sudo tetra probe config`; confirm `/sys/fs/bpf` is mounted (`findmnt /sys/fs/bpf`) |
| Policy rejected | Policy schema differs by version; compare with https://tetragon.io/docs/reference/tracing-policy/ |
| `auditd: UNAVAILABLE` | Kernel lacks audit support (common on stock WSL2) or the package failed to install; needs a custom kernel or another host |
| `auditd: no rule loaded for agent_file` | The kernel rejected every file-open syscall rule; check `auditctl -c -R /var/tmp/sensor-spike-results/auditd-active.rules` for which |
| Capture counts are 0 but events exist | The grep patterns or the `ausearch --start` time format do not match this version; inspect `tetragon-capture-events.json` and `auditd-*.txt` |
