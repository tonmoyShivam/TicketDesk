#!/bin/bash
# Build and (re)start TicketDesk with Docker Compose on the EC2 instance.
# Called by the first-boot bootstrap and by update.sh. Safe to run repeatedly. Run as root.
set -euo pipefail

APP_DIR=/opt/ticketdesk/app
COMPOSE=(docker compose --env-file /etc/ticketdesk/compose.env -f "$APP_DIR/deploy/ec2/docker-compose.prod.yml")

[ "$(id -u)" -eq 0 ] || { echo "Run as root: sudo $0"; exit 1; }
[ -f /etc/ticketdesk/ticketdesk.env ] || { echo "Missing /etc/ticketdesk/ticketdesk.env"; exit 1; }

echo "==> Building the application image"
"${COMPOSE[@]}" build app

echo "==> Applying the database schema (retries while RDS finishes starting)"
ok=0
for attempt in 1 2 3 4 5 6 7 8; do
  if "${COMPOSE[@]}" run --rm --no-deps app python -m scripts.init_db; then
    ok=1; break
  fi
  echo "   attempt $attempt failed, retrying in 20s"; sleep 20
done
[ "$ok" -eq 1 ] || { echo "Could not apply the database schema"; exit 1; }

echo "==> Starting containers"
"${COMPOSE[@]}" up -d --remove-orphans
docker image prune -f >/dev/null

echo "==> Health check"
for _ in $(seq 1 30); do
  if curl -fsS http://127.0.0.1/health; then
    echo; echo "TicketDesk is up."; exit 0
  fi
  sleep 3
done
echo "Health check failed. Container status and recent logs:"
"${COMPOSE[@]}" ps
"${COMPOSE[@]}" logs --tail 50 app || true
exit 1
