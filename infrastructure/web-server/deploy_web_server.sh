#!/usr/bin/env bash
set -euo pipefail

deployed_commit=${1:-origin/main}
repository_directory=/opt/agent-watch
virtual_environment_directory=/opt/agent-watch-virtual-environment

git -C "$repository_directory" fetch --quiet origin
git -C "$repository_directory" reset --quiet --hard "$deployed_commit"

[[ -d $virtual_environment_directory ]] || python3.12 -m venv "$virtual_environment_directory"
"$virtual_environment_directory/bin/pip" install --quiet --upgrade "$repository_directory/lib[rest-api]"

install -m 644 "$repository_directory/infrastructure/web-server/agent-watch-web-server.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --quiet agent-watch-web-server
systemctl restart agent-watch-web-server
echo "Deployed $(git -C "$repository_directory" rev-parse --short HEAD)"
