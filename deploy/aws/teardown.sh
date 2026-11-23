#!/bin/bash
# Destroy every resource Terraform created: EC2, RDS (no final snapshot), the S3 bucket
# including all object versions, Lambda, IAM, CloudWatch, VPC.
#   ./deploy/aws/teardown.sh
set -euo pipefail
cd "$(dirname "$0")/../../terraform"
TF=${TF:-terraform}

COUNT=$("$TF" state list | wc -l)
read -r -p "Destroy all $COUNT TicketDesk resources, including the database and every attachment? Type 'destroy': " answer
[ "$answer" = "destroy" ] || { echo "Cancelled."; exit 1; }

# Pass the same variables Terraform needs to evaluate the configuration.
ARGS=()
[ -f terraform.tfvars ] || ARGS+=(-var "repo_url=https://example.invalid/unused" -var "allowed_http_cidr=127.0.0.1/32")

"$TF" destroy -input=false -auto-approve "${ARGS[@]}"
echo "Remaining resources in state: $("$TF" state list | wc -l) (expected 0)"
