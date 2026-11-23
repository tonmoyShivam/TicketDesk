#!/bin/bash
# Provision (or update) the whole TicketDesk environment with Terraform.
# Run from your laptop with the AWS CLI configured (aws configure / SSO).
#
#   REPO_URL=https://github.com/<you>/<repo>.git ./deploy/aws/deploy.sh
#
# Optional: AWS_REGION (default ap-south-1), ALLOWED_CIDR (default: your public IP /32),
#           BRANCH (default main), ALERT_EMAIL, GITHUB_REPOSITORY (owner/name), TF (terraform|tofu)
# If terraform/terraform.tfvars exists, those values are used and the env vars are optional.
set -euo pipefail
cd "$(dirname "$0")/../../terraform"
TF=${TF:-terraform}

ARGS=()
if [ ! -f terraform.tfvars ]; then
  : "${REPO_URL:?Set REPO_URL (or create terraform/terraform.tfvars from the example)}"
  if [ -z "${ALLOWED_CIDR:-}" ]; then
    ALLOWED_CIDR="$(curl -fsS https://checkip.amazonaws.com | tr -d '[:space:]')/32"
  fi
  ARGS+=(-var "repo_url=$REPO_URL" -var "allowed_http_cidr=$ALLOWED_CIDR"
         -var "aws_region=${AWS_REGION:-ap-south-1}" -var "repo_branch=${BRANCH:-main}")
  [ -n "${ALERT_EMAIL:-}" ] && ARGS+=(-var "alert_email=$ALERT_EMAIL")
  [ -n "${GITHUB_REPOSITORY:-}" ] && ARGS+=(-var "github_repository=$GITHUB_REPOSITORY")
  echo "HTTP access allowed from $ALLOWED_CIDR"
fi

"$TF" init -input=false
"$TF" apply -input=false "${ARGS[@]}"

echo
echo "Infrastructure is ready. The instance needs ~5 more minutes to install Docker, build and start the app."
echo "Watch it:  aws ssm start-session --target $("$TF" output -raw instance_id)   then   sudo tail -f /var/log/ticketdesk-bootstrap.log"
echo "App URL:   $("$TF" output -raw app_url)"
