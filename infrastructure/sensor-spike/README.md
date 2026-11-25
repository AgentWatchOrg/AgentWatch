# Sensor spike: Tetragon vs auditd on WSL

Scripts that install, compare, and document two Linux host sensors for AgentWatch: **Tetragon** (eBPF, preferred) and **auditd** (fallback). They cover tickets [#4](https://github.com/AgentWatchOrg/AgentWatch/issues/4) (spike: which sensor?) and [#57](https://github.com/AgentWatchOrg/AgentWatch/issues/57) (configure Tetragon and the auditd fallback).

This README targets an Ubuntu distribution running in WSL2 on Windows. The same scripts run unchanged on any Ubuntu host with systemd.

## Objective

AgentWatch watches what an AI agent (first target: Claude Code) does on a Linux host, flags suspicious behavior, and sends everything to Splunk. The sensor is the first stage:

```
AI agent on Linux host -> Sensor (Tetragon) -> Forwarder -> Backend -> Detection engine -> Splunk
```

The sensor must observe three activity types, attributable to the agent and its child processes:

| Activity | Meaning |
|---|---|
| Process execution | Programs the agent starts, with arguments and parent lineage |
| File access | Files the agent opens |
| Network connections | Destinations the agent connects to |

The spike answers, with evidence from a real host:

1. Does Tetragon work on this host, and what does it need (kernel, BTF, privileges)?
2. Does it capture all three activity types, and which fields identify the process, its lineage, and the activity?
3. What does auditd capture for the same activities, and where are the gaps?
4. What is the overhead of each, informally?
5. When must AgentWatch fall back to auditd?

Out of scope: the forwarder, session correlation, backend ingestion, custom eBPF programs, formal benchmarking, and any enforcement. AgentWatch observes and reports; it never blocks or remediates, so no Tetragon policy may contain enforcement actions (`Sigkill`, `Override`, and similar).

## Notes for an AI agent working from this README

You are probably running on the WSL host. Follow these rules:

- **Report only what you measured.** Every result must come from output you saw. If a command fails, report the exact error. Do not fill in expected numbers.
- **These items are unverified and may need fixing on first run:** the Tetragon release URL pattern (`tetragon-<tag>-<arch>.tar.gz`), the `/etc/tetragon/tetragon.tp.d/` policy directory, the policy YAML in `policies/` (schema varies by Tetragon version), and the JSON field names the scripts grep for (`"dport"` in Tetragon output, `lport=` in `ausearch -i` output). If counts come back 0 where you can see events, check these first against the installed version's docs at https://tetragon.io/docs/ and fix the script.
- **Never add enforcement actions** to a tracing policy.
- **Never put real secrets in the workload, samples, or commits.** Claude Code's API key goes in the shell environment of the manual session only.
- **Commit only sanitized samples** (`samples-sanitized/`) and read them before committing. Redaction is pattern-based.
- **Ask before** installing a custom kernel or changing Windows settings.
- Ordinary tasks need root (`sudo`): loading eBPF programs and audit rules requires it. Record that as a host requirement.

How Tetragon works here, in short: it runs as a systemd service, loads eBPF programs into the kernel, and writes structured JSON events. It emits process exec and exit events by default. File and network events come from tracing policies (YAML) that attach kprobes to kernel functions: `security_file_open` for file opens and `tcp_connect` for outbound TCP connections. `tetra getevents -o json` streams events from the running service, and `tetra tracingpolicy list` shows loaded policies. Each process has an `exec_id`, and its parent's id is `parent_exec_id`, which gives process lineage with no extra work. auditd records raw syscalls instead: loaded rules (`auditctl`) log `execve`, `openat`, and `connect` for one user, and `ausearch -i` renders the records. Its lineage is only `pid`/`ppid`.

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

`install_sensors.sh` records host facts, installs Tetragon (latest release; pin with `sudo TETRAGON_VERSION=v1.x.x ./install_sensors.sh`) and its policies, installs auditd, creates the unprivileged `agentuser`, and copies the scripts to `/opt/sensor-spike/`. It never aborts because one sensor is unavailable. It records availability in `/var/tmp/sensor-spike-results/availability.env` and continues with what works.

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

`compare_sensors.sh` runs three phases (no sensor, Tetragon, auditd). Each runs the same workload as `agentuser`: 35 execs, 35 file opens, and 30 connects, each carrying a unique marker, then a timed stress loop. Skipped phases are labeled in the summary. Tunables: `EXEC_COUNT`, `FILE_COUNT`, `NETWORK_COUNT`, `STRESS_ITERATIONS`.

### Manual Claude Code session

The scripted workload is synthetic. For a realistic sample, run Claude Code as `agentuser` while a sensor is enabled:

```bash
sudo /opt/sensor-spike/manage_sensor.sh enable tetragon
sudo -u agentuser -i
export ANTHROPIC_API_KEY=...   # this shell only; never in a file
# run claude in a scratch project, ask it to read files and run a curl
```

In a second terminal: `sudo tetra getevents -o json | tee /tmp/claude-session.json`. Check that the agent's child processes (for example a `curl` it spawns) trace back to the agent through `parent_exec_id`.

## Enable, verify, disable

| Sensor | Enable | Verify | Disable |
|---|---|---|---|
| Tetragon | `sudo /opt/sensor-spike/manage_sensor.sh enable tetragon` | `... verify tetragon` runs a known command and checks Tetragon saw it; `tetra tracingpolicy list` shows policies | `... disable tetragon` |
| auditd | `sudo /opt/sensor-spike/manage_sensor.sh enable auditd` | `... verify auditd` checks the rules fired for a known command; `sudo auditctl -l` lists rules | `... disable auditd` (clears all audit rules) |

Policies live in `policies/`. Install copies them to `/etc/tetragon/tetragon.tp.d/`; edit them there and run `sudo systemctl restart tetragon` to reload. `auditd.rules` uses an `AGENT_UID` placeholder that `manage_sensor.sh enable auditd` replaces with `agentuser`'s uid. The rules also cover 32-bit syscalls (`arch=b32`) so an agent cannot bypass them by calling the 32-bit interface.

## When to switch to auditd

Use auditd instead of Tetragon when any of these hold. `manage_sensor.sh recommend` checks the first two.

1. `/sys/kernel/btf/vmlinux` is missing (no BTF).
2. The Tetragon service fails to start (`tetragon-startup-error.txt` in the results folder has the journal).
3. In `summary.txt`, Tetragon captures under 95% of the known activities while auditd meets the target (design doc Section 10: at least 95% of at least 100 known activities).

If auditd is also unavailable, the host cannot be monitored; record that and stop.

## Results

Everything lands in `/var/tmp/sensor-spike-results/`:

| File | Contents |
|---|---|
| `host-info.txt` | Kernel, distribution, WSL flag, BTF, Tetragon version, policies loaded, probe output |
| `availability.env` | Which sensors work on this host |
| `summary.txt` | Captured count and missing markers per activity per sensor, stress time, sensor CPU seconds and memory |
| `fields-report.txt` | Per sample, every field path plus checklists for process identity, lineage, and activity details |
| `samples/` | Raw events, unsanitized, from each sensor for each activity |
| `samples-sanitized/` | Same, with hostname, usernames, non-loopback IPs, and API key patterns redacted |

### What to deliver

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

- **Accept the fallback.** The scripts continue with auditd only, which demonstrates the switch condition above. Note that WSL2's stock kernel may also lack audit support; `install_sensors.sh` records that as `auditd: UNAVAILABLE`.
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
| Tetragon service inactive | `journalctl -u tetragon -n 50`; check `sudo tetra probe config`; confirm `/sys/fs/bpf` is mounted (`findmnt /sys/fs/bpf`) |
| Policy rejected | Policy schema differs by version; compare with https://tetragon.io/docs/reference/tracing-policy/ |
| `auditd: UNAVAILABLE` | Kernel lacks audit support (common on stock WSL2); needs a custom kernel or another host |
| Capture counts are 0 but events exist | The grep patterns in `compare_sensors.sh` do not match this version's field format; inspect `tetragon-capture-events.json` |
| Download fails | Check network, or pin a release with `TETRAGON_VERSION` |

## Files

| File | Purpose |
|---|---|
| `install_sensors.sh` | Install and configure both sensors; record availability |
| `manage_sensor.sh` | Enable, verify, disable, status, recommend |
| `run_workload.sh` | Known activities with unique markers (`capture`), and a timing loop (`stress`) |
| `compare_sensors.sh` | Baseline, Tetragon, and auditd phases; calls the two scripts below |
| `report_fields.sh` | Field inventory from the samples |
| `sanitize_samples.sh` | Redacted copies of the samples |
| `archive_results.sh` | Tarball of the results folder |
| `policies/` | Tetragon tracing policies (file open, network connect); exec is on by default |
| `auditd.rules` | auditd fallback rules |
