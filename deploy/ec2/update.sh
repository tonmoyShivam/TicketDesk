#!/bin/bash
# Pull the latest code and redeploy. Run as root on the instance (or via SSM / GitHub Actions):
#   sudo bash /opt/ticketdesk/app/deploy/ec2/update.sh
set -euo pipefail
git -C /opt/ticketdesk/app pull --ff-only
exec bash /opt/ticketdesk/app/deploy/ec2/install.sh
