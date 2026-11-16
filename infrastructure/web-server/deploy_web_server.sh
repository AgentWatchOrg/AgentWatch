#!/usr/bin/env bash
set -euo pipefail

deployed_commit=${1:-origin/main}
repository_directory=/opt/agent-watch
virtual_environment_directory=/opt/agent-watch-virtual-environment
environment_file=/etc/agent-watch-web-server.env
project_board_token_parameter=/agent-watch/web-server/project-board-token

git -C "$repository_directory" fetch --quiet origin
git -C "$repository_directory" reset --quiet --hard "$deployed_commit"

[[ -d $virtual_environment_directory ]] || python3.12 -m venv "$virtual_environment_directory"
"$virtual_environment_directory/bin/pip" install --quiet --upgrade "$repository_directory/lib" "$repository_directory/web-server"

metadata_token=$(curl -s -X PUT http://169.254.169.254/latest/api/token -H "X-aws-ec2-metadata-token-ttl-seconds: 60")
aws_region=$(curl -s -H "X-aws-ec2-metadata-token: $metadata_token" http://169.254.169.254/latest/meta-data/placement/region)
project_board_token=$(aws ssm get-parameter --region "$aws_region" --name "$project_board_token_parameter" \
  --with-decryption --query Parameter.Value --output text 2>/dev/null || true)
install -m 600 /dev/null "$environment_file"
echo "PROJECT_BOARD_TOKEN=$project_board_token" > "$environment_file"

install -m 644 "$repository_directory/infrastructure/web-server/agent-watch-web-server.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --quiet agent-watch-web-server
systemctl restart agent-watch-web-server
echo "Deployed $(git -C "$repository_directory" rev-parse --short HEAD)"
