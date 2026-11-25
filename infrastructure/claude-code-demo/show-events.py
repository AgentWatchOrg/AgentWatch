#!/usr/bin/env python3

import json
import sys


sample_path = sys.argv[1]

for line in sys.stdin:
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        continue

    process = event.get("process_exec", {}).get("process", {})
    if process.get("binary") == "/usr/bin/wc" and process.get("arguments") == "-l sample.txt":
        print(f"Tetragon | COMMAND  wc -l sample.txt | PID {process.get('pid', '?')}")

    probe = event.get("process_kprobe", {})
    function = probe.get("function_name")
    pid = probe.get("process", {}).get("pid", "?")
    for argument in probe.get("args", []):
        if function == "security_file_open" and argument.get("file_arg", {}).get("path") == sample_path:
            print(f"Tetragon | FILE OPEN  sample.txt | PID {pid}")
            break
        if function == "tcp_connect":
            socket = argument.get("sock_arg", {})
            if socket.get("daddr") == "127.0.0.1" and socket.get("dport") == 8765:
                print(f"Tetragon | NETWORK  TCP to 127.0.0.1:8765 | PID {pid}")
                break
