#!/bin/bash
# Create or update a TicketDesk user inside the running app container (prompts for the password).
#   sudo bash /opt/ticketdesk/app/deploy/ec2/create_user.sh admin --role admin --full-name "Admin"
set -euo pipefail
cd /opt/ticketdesk/app
exec docker compose --env-file /etc/ticketdesk/compose.env -f deploy/ec2/docker-compose.prod.yml \
  exec app python -m scripts.create_user "$@"
