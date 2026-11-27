# Sensor spike scripts

Scripts in `infrastructure/sensor-spike/` install Tetragon and auditd on one Ubuntu host, run the same workload under no sensor, Tetragon, and auditd, and collect the results for tickets #4 and #57. Step-by-step setup, including WSL, is in the [folder README](https://github.com/AgentWatchOrg/AgentWatch/blob/main/infrastructure/sensor-spike/README.md). The scripts have not yet run on a real host; the Tetragon release URL pattern and tracing policy syntax are unverified.

Host: Ubuntu 22.04 or 24.04 with systemd and BTF at `/sys/kernel/btf/vmlinux`, root access. Tetragon needs BTF; without it the host uses auditd.

## Enable, verify, disable

Run through `sudo /opt/sensor-spike/manage_sensor.sh <action> <tetragon|auditd|all>`.

| Action | Tetragon | auditd |
|---|---|---|
| `enable` | Starts the service, which loads `/etc/tetragon/tetragon.tp.d/*.yaml` | Loads `auditd.rules` for `agentuser`, replacing only a previous run's spike rules |
| `verify` | Runs a known command and checks Tetragon emitted its exec event | Runs a known command and checks the `agent_exec` rule recorded it |
| `disable` | Stops the service | Removes only the spike rules (keys `agent_exec`, `agent_file`, `agent_net`) |

`manage_sensor.sh status` shows what is active. `manage_sensor.sh recommend` names the sensor the host supports.

The scripts never truncate audit logs or remove rules they did not add, so they are safe on a host with its own audit configuration.

The auditd rules cover `execve`, `execveat`, `open`, `openat`, `openat2`, `creat`, and `connect` on the 64-bit and 32-bit interfaces. Syscalls not listed, and mechanisms that avoid them such as `io_uring`, are not recorded. Rules for syscalls an architecture lacks fail to load and are skipped; `enable` fails only if a whole activity type ends up with no rule.

## Switch to auditd

| Condition | Check |
|---|---|
| No BTF | `/sys/kernel/btf/vmlinux` missing |
| Tetragon does not start | `tetragon-startup-error.txt` in the results folder |
| Capture below target | Tetragon under 95% of known activities while auditd meets it (`summary.txt`) |

## Scripts

| Script | Purpose |
|---|---|
| `install_sensors.sh` | Installs both sensors, policies, and `agentuser`; records which sensors work. |
| `manage_sensor.sh` | Enable, verify, disable, status, recommend. |
| `run_workload.sh` | `capture`: known exec, file-open, and connect actions with unique markers. `stress`: loop for timing. |
| `compare_sensors.sh` | Runs the three phases; reports captured and missing markers, stress time, sensor CPU and memory. Reads only audit records created after the run starts. |
| `report_fields.sh` | Lists the process identity, lineage, and activity fields present in each sample. |
| `sanitize_samples.sh` | Redacts hostnames, usernames, non-loopback IPs, and API key patterns. Rewrites `exec_id` and `parent_exec_id`, which Tetragon builds as base64 of `<hostname>:<start time>:<pid>`, so they carry no hostname and still link child to parent. Fails if the hostname is still recoverable. |
| `archive_results.sh` | Packs the results folder. |

## Options

| Variable | Default | Used by |
|---|---|---|
| `TETRAGON_VERSION` | latest release | `install_sensors.sh` |
| `EXEC_COUNT` | 35 | `compare_sensors.sh` |
| `FILE_COUNT` | 35 | `compare_sensors.sh` |
| `NETWORK_COUNT` | 30 | `compare_sensors.sh` |
| `STRESS_ITERATIONS` | 2000 | `compare_sensors.sh` |

## Results

Written to `/var/lib/sensor-spike/results/`, a root-owned directory. The scripts run as root and read `availability.env` as data, accepting only `yes` or `no`; they never execute it.

| File | Contents |
|---|---|
| `host-info.txt` | Kernel, distribution, BTF, Tetragon version, loaded policies. |
| `availability.env` | Which sensors work on the host. |
| `summary.txt` | Capture counts and missing markers per activity per sensor; overhead per phase. |
| `fields-report.txt` | Field inventory per sample. |
| `samples/`, `samples-sanitized/` | Raw events per sensor and activity; sanitized copies are the ones to commit. |

Tracing policies leave enforcement actions out. The Claude Code session is not scripted; run it manually as `agentuser` with the API key set only in that shell.
