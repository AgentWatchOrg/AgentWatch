# Local Claude Code demo on Ubuntu

AgentWatch uses Claude Code to generate activity for [Sprint 1](https://github.com/AgentWatchOrg/AgentWatch/issues/56). [Ollama runs the Qwen model locally](https://docs.ollama.com/integrations/claude-code), so this setup uses the local model server for inference. Tetragon observes activity on the same Linux host. Sensor installation and policy configuration are tracked in [#57](https://github.com/AgentWatchOrg/AgentWatch/issues/57).

The reference run used Ubuntu 24.04 on x86-64 WSL 2, kernel `5.15.167.4-microsoft-standard-WSL2`, Claude Code `2.1.331`, Ollama `0.40.18`, and `qwen3.5:4b`. Initial downloads total about 5 GB. A local prompt can take a minute or two.

## One-time setup

On Windows, open PowerShell and check that Ubuntu 24.04 is listed with WSL version 2. Install the distribution if it is missing.

```powershell
wsl.exe --list --verbose
wsl.exe --install -d Ubuntu-24.04
```

In Ubuntu, run the following as your regular administrator account. The first command installs the CLI dependencies. Create `agentwatch` once as the dedicated unprivileged account.

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl git python3 zstd
sudo adduser --disabled-password --gecos '' agentwatch
sudo -iu agentwatch
```

Run the rest of the setup as `agentwatch`. Install the tested [Claude Code version](https://code.claude.com/docs/en/setup#install-a-specific-version) and unpack the [pinned Ollama release](https://github.com/ollama/ollama/releases/tag/v0.40.18) inside the account's home directory.

```bash
curl -fsSL https://claude.ai/install.sh | bash -s 2.1.331

archive=$(mktemp --suffix=.tar.zst)
ollama_dir="$HOME/.local/opt/ollama-0.40.18"
curl -fL https://github.com/ollama/ollama/releases/download/v0.40.18/ollama-linux-amd64.tar.zst -o "$archive" &&
  printf '%s  %s\n' \
    b82649006cb5b54ed1237fa2d1a26a7f939a4fd03150033759acbff7ff315adf "$archive" | sha256sum -c - &&
  mkdir -p "$ollama_dir" &&
  tar --zstd -xf "$archive" -C "$ollama_dir" &&
  rm -- "$archive"
```

Clone AgentWatch inside the Linux home directory. Use a checkout that includes this guide and its launcher. The `prepare` command starts the loopback model server if needed and downloads Qwen.

```bash
git clone https://github.com/AgentWatchOrg/AgentWatch.git "$HOME/AgentWatch"
cd "$HOME/AgentWatch"
./infrastructure/claude-code-demo/rehearse.sh prepare
```

## Smoke test

From the repository checkout as `agentwatch`, record the versions and run the smoke test.

```bash
id -un
uname -r
"$HOME/.local/bin/claude" --version
"$HOME/.local/opt/ollama-0.40.18/bin/ollama" --version
./infrastructure/claude-code-demo/rehearse.sh smoke
```

Expect `Bash returned: 1 sample.txt`. The launcher generates a disposable sample repository, directs Claude Code to Ollama at `127.0.0.1:11434`, and allows the requested Bash command. The local connection uses a placeholder token and needs no Anthropic login or AWS credentials. Claude Code may print an unrecognized model warning when invoked directly with Qwen.

## Demo and sensor preflight

Run the launcher without arguments and choose `1` to count lines or `2` to fetch the sample file from the loopback test server. Enter `q` to quit.

```bash
./infrastructure/claude-code-demo/rehearse.sh
```

For Tetragon, have the sensor operator check that `/sys/kernel/btf/vmlinux` is readable and that the file-open and TCP-connect policies are enabled. With the standard `#57` service configuration, run `sudo tetra tracingpolicy list` from an Ubuntu administrator shell. Process execution is provided by Tetragon's base sensor.

If the demo user has access to the sensor's event socket, set `TETRA_ADDRESS` to its configured address for a combined view. For example, a loopback listener on the default port can be viewed with the following command.

```bash
TETRA_ADDRESS=127.0.0.1:54321 ./infrastructure/claude-code-demo/rehearse.sh
```

The viewer shows the command, sample file open, and connection to port `8765`. For a Unix socket, use its `unix:///…` address. Set `TETRA_BIN` if the `tetra` binary is outside `PATH`. The sensor operator can also stream events independently with `sudo tetra getevents -o json`.

For [#56](https://github.com/AgentWatchOrg/AgentWatch/issues/56), the second tester should post their Ubuntu and kernel versions, Claude Code and Ollama versions, sensor preflight, smoke-test result, and any setup corrections on the issue.
