#!/usr/bin/env bash
set -euo pipefail

deployed_commit=${1:-origin/main}
repository_directory=/opt/agent-watch
virtual_environment_directory=/opt/agent-watch-virtual-environment
secret_parameter_path=/agent-watch/rest-api
environment_file=/etc/agent-watch/rest-api.env

git -C "$repository_directory" fetch --quiet origin
git -C "$repository_directory" reset --quiet --hard "$deployed_commit"

[[ -d $virtual_environment_directory ]] || python3.12 -m venv "$virtual_environment_directory"
"$virtual_environment_directory/bin/pip" install --quiet --upgrade "$repository_directory/lib[rest-api]"

write_environment_file_from_secret_parameters() {
  local instance_metadata_token region
  instance_metadata_token=$(curl --silent --request PUT http://169.254.169.254/latest/api/token \
    --header "X-aws-ec2-metadata-token-ttl-seconds: 60")
  region=$(curl --silent --header "X-aws-ec2-metadata-token: $instance_metadata_token" \
    http://169.254.169.254/latest/meta-data/placement/region)
  install -d -m 700 "$(dirname "$environment_file")"
  aws ssm get-parameters-by-path --region "$region" --path "$secret_parameter_path" --with-decryption \
    --query 'Parameters[].[Name,Value]' --output text \
    | while IFS=$'\t' read -r parameter_name parameter_value; do
        variable_name=$(basename "$parameter_name" | tr '[:lower:]-' '[:upper:]_')
        printf '%s=%s\n' "$variable_name" "$parameter_value"
      done > "$environment_file.new"
  install -m 600 "$environment_file.new" "$environment_file"
  rm -f "$environment_file.new"
}
write_environment_file_from_secret_parameters

install -m 644 "$repository_directory/infrastructure/web-server/agent-watch-web-server.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --quiet agent-watch-web-server
systemctl restart agent-watch-web-server
echo "Deployed $(git -C "$repository_directory" rev-parse --short HEAD)"
