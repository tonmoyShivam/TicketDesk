#!/bin/bash
# Ship new application code to the running instance (git pull + docker compose rebuild)
# through SSM Run Command - no SSH. GitHub Actions does the same on every push to main.
#   ./deploy/aws/redeploy_app.sh
set -euo pipefail
cd "$(dirname "$0")/../../terraform"
TF=${TF:-terraform}
REGION=${AWS_REGION:-ap-south-1}
INSTANCE_ID=$("$TF" output -raw instance_id)
echo "Redeploying on $INSTANCE_ID"

COMMAND_ID=$(aws ssm send-command --region "$REGION" \
  --instance-ids "$INSTANCE_ID" \
  --document-name AWS-RunShellScript \
  --comment "TicketDesk redeploy" \
  --parameters 'commands=["bash /opt/ticketdesk/app/deploy/ec2/update.sh"]' \
  --query Command.CommandId --output text)

aws ssm wait command-executed --region "$REGION" --command-id "$COMMAND_ID" --instance-id "$INSTANCE_ID" || true
aws ssm get-command-invocation --region "$REGION" --command-id "$COMMAND_ID" --instance-id "$INSTANCE_ID" \
  --query "{Status:Status,Output:StandardOutputContent,Errors:StandardErrorContent}" --output text
