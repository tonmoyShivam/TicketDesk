# Deployment guide

Follows the POC milestones in order. Everything is code: running these steps against a fresh AWS
account produces the same environment (pass/fail item 4), and `teardown.sh` removes it (item 5).

**Region in examples:** `ap-south-1` (Mumbai). **Tools:** AWS CLI v2, Terraform ≥ 1.6 (or OpenTofu),
Git, Python 3.11+, Docker (local only). **Windows:** run the `.sh` scripts in Git Bash or WSL.

---

## M0 — Understand the application (Days 1–2)

```
Browser ──HTTP:80──▶ nginx container ──▶ app container (uvicorn + FastAPI)
                                            │
                                            ├── SQLAlchemy ──TLS──▶ PostgreSQL (local Docker / Amazon RDS)
                                            ├── boto3 ─────────────▶ S3 bucket ──ObjectCreated──▶ Lambda
                                            └── stdout ──awslogs──▶ CloudWatch Logs /ticketdesk/app
```

| Piece | File | What to know for the review |
|---|---|---|
| App factory | `app/main.py` | `create_app()` reads settings, builds the DB engine and storage backend |
| Config | `app/config.py` | Only environment variables; fails fast with a clear message if something is missing |
| DB connection | `app/db.py` | `DATABASE_URL` locally; on AWS `DB_HOST` + `DB_SECRET_ARN`, password read from Secrets Manager at connect time, refreshed on rotation |
| Data model | `app/models.py`, `sql/schema.sql` | users, tickets, attachments, ticket_history |
| Routes | `app/routes.py` | login/logout, dashboard, tickets, status, assignment, attachments, `/health` |
| Storage | `app/storage.py` | `LocalStorage` or `S3Storage` (instance role, 5-minute pre-signed downloads) |
| Lambda | `lambda/file_processor.py` | extension + size + magic-byte check, SHA-256, S3 tags, JSON audit log |

**Done when:** you can explain the diagram and run the app locally.

---

## M1 — Local configuration (Days 3–5)

1. `cp .env.example .env`; set `SECRET_KEY`, `LOCAL_DB_PASSWORD` and the matching `DATABASE_URL`.
2. `docker compose up -d db` → PostgreSQL 16 on `127.0.0.1:5432`.
3. `python -m scripts.init_db` → runs `sql/schema.sql` (safe to rerun).
4. Create an admin, an agent and two users with `python -m scripts.create_user`.
5. `uvicorn app.main:create_app --factory --reload`; run TC-01…TC-16 in `docs/TEST_PLAN.md`.
6. `pytest -q` (all pass). Optional: `docker compose --profile app up -d --build` runs the app container too.

```bash
docker compose exec db psql -U ticketdesk -d ticketdesk -c "select id, title, status from tickets;"
```

**Done when:** every local test case passes and ticket rows are visible in PostgreSQL.

---

## M2 — Provision AWS and deploy on EC2 (Days 6–8)

### 1. Push the repo and configure Terraform

```bash
git push origin main
cp terraform/terraform.tfvars.example terraform/terraform.tfvars
# set repo_url, and allowed_http_cidr to "$(curl -s https://checkip.amazonaws.com)/32"
# optional: alert_email, github_repository
```

`terraform.tfvars` is git-ignored. It holds no secrets.

### 2. Apply

```bash
./deploy/aws/deploy.sh          # = terraform init && terraform apply
```

Review the plan (51 resources by default; +3 with `github_repository`, +1 with `alert_email`) and type `yes`.

| Module | Builds | Key settings |
|---|---|---|
| network | VPC `10.0.0.0/16`, public subnet `10.0.1.0/24`, private `10.0.10.0/24` + `10.0.11.0/24` in 2 AZs | private route table has **no** internet route; no NAT Gateway cost |
| security | app SG, DB SG | app: in 80 from your IP only, **no 22**; out 80/443 + 5432 to DB SG. DB: in 5432 from app SG only |
| iam | EC2 role + instance profile, optional GitHub OIDC role | scoped to one bucket prefix, one secret, one log group (see ARCHITECTURE doc) |
| rds | PostgreSQL 16, `db.t3.micro`, 20 GB gp3 encrypted | `publicly_accessible=false`, managed master password, `rds.force_ssl=1`, 7-day backups, logs to CloudWatch |
| s3 | attachments bucket | public access blocked, SSE-S3, **versioning**, 30-day old-version expiry, TLS-only policy |
| lambda | file processor (Python 3.12) | S3 `ObjectCreated` on `attachments/`, 14-day log retention |
| cloudwatch | `/ticketdesk/app` log group, metric filters, 6 alarms + SNS, dashboard | see M5 |
| ec2 | `t3.micro` Amazon Linux 2023 | IMDSv2 only, encrypted gp3 root, user data installs Docker + Compose, clones repo, writes `/etc/ticketdesk/ticketdesk.env` (no DB password), runs `deploy/ec2/install.sh` |

`install.sh` builds the image, applies the schema (retrying until RDS answers), starts the
`app` and `nginx` containers (`restart: unless-stopped`), and checks `/health`.

### 3. Watch the first boot (~5 minutes after apply)

```bash
aws ssm start-session --target "$(cd terraform && terraform output -raw instance_id)"
sudo tail -f /var/log/ticketdesk-bootstrap.log         # ends with "TicketDesk is up."
```

(Or EC2 console → instance → Connect → Session Manager.)

### 4. Create users

```bash
sudo bash /opt/ticketdesk/app/deploy/ec2/create_user.sh admin --role admin --full-name "Admin"
sudo bash /opt/ticketdesk/app/deploy/ec2/create_user.sh agent1 --role agent --full-name "Support Agent"
sudo bash /opt/ticketdesk/app/deploy/ec2/create_user.sh ravi --full-name "Ravi Kumar"
```

### 5. Verify

- Open `terraform output app_url`, log in, run the main flow.
- Containers: `sudo docker compose --env-file /etc/ticketdesk/compose.env -f /opt/ticketdesk/app/deploy/ec2/docker-compose.prod.yml ps`
- **Restart test:** `sudo docker restart $(sudo docker ps -q)` → back in seconds. `sudo reboot` →
  Docker starts on boot and the containers come back on their own.

**Done when:** the app works from the AWS URL and survives a container restart and a reboot.

---

## M3 — Amazon RDS (Days 9–10)

The app is already on RDS after M2; verify and be ready to explain it.

```bash
curl -s "$(cd terraform && terraform output -raw app_url)/health"        # "database":"ok"
aws rds describe-db-instances --db-instance-identifier ticketdesk-db \
  --query "DBInstances[0].{public:PubliclyAccessible,engine:EngineVersion,backups:BackupRetentionPeriod,encrypted:StorageEncrypted}"
```

On the instance, count tickets straight from RDS with the app's own config:

```bash
sudo bash -c 'cd /opt/ticketdesk/app && docker compose --env-file /etc/ticketdesk/compose.env \
  -f deploy/ec2/docker-compose.prod.yml exec app python -c "
from app.config import Settings; from app.db import build_engine; from sqlalchemy import text
print(build_engine(Settings.from_env()).connect().execute(text(\"select status, count(*) from tickets group by status\")).all())"'
```

Credentials: RDS generated the master password and keeps it in Secrets Manager
(`terraform output db_secret_arn`). It never appears in code, user data, the env file or Terraform state.

Local test data is not migrated: the schema is applied to RDS by `install.sh` and test data is
recreated through the app on AWS (the normal approach for this POC).

**Done when:** tickets created on AWS are in RDS and `public` is `false`.

---

## M4 — S3 and Lambda (Days 11–12)

1. Upload a PNG/PDF to a ticket; after a few seconds the **Processing** column shows *processed* + checksum.
2. Rename a non-image to `.png` and upload: Lambda tags it *rejected — content does not match extension*.
3. Logs and objects:
   ```bash
   aws logs tail /aws/lambda/ticketdesk-file-processor --since 15m --follow
   aws s3api list-object-versions --bucket "$(cd terraform && terraform output -raw attachments_bucket)" --prefix attachments/ \
     --query "Versions[].{key:Key,version:VersionId,latest:IsLatest}"
   ```
4. Direct object URL without signature → `AccessDenied`. Download links from the app expire after 5 minutes.

**Done when:** files are in S3 (versioned), Lambda logs one JSON line per file, and the UI shows the result.

---

## M5 — Monitoring, testing and completion (Days 13–14)

### CloudWatch

- Dashboard: `terraform output dashboard_url` → EC2 CPU, RDS connections/CPU/free storage,
  Lambda invocations/errors, app errors and failed logins, alarm status, recent Lambda results,
  recent app warnings/errors.
- App logs: `aws logs tail /ticketdesk/app --follow` (streams `app` and `nginx`).
- Alarms (`ticketdesk-*`): EC2 CPU > 80 %, EC2 status check, RDS CPU > 80 %, RDS free storage < 2 GB,
  Lambda errors ≥ 1, app ERROR lines ≥ 5 in 5 min. With `alert_email` set, confirm the SNS email.
  Demo an alarm: `aws cloudwatch set-alarm-state --alarm-name ticketdesk-lambda-errors --state-value ALARM --state-reason demo`.

### CI/CD (GitHub Actions)

- `ci.yml` runs on every push: pytest, `tofu fmt/validate/test`, Docker build.
- `deploy.yml` redeploys after CI passes on `main`. Setup once:
  1. Set `github_repository = "<owner>/<repo>"` in `terraform.tfvars` and re-run `deploy.sh`
     (set `create_github_oidc_provider = false` if the account already has the GitHub provider).
  2. Repo → Settings → Secrets and variables → Actions → **Variables**:
     `AWS_DEPLOY_ROLE_ARN` (`terraform output github_deploy_role_arn`), `EC2_INSTANCE_ID`, `AWS_REGION`.
  No AWS keys are stored in GitHub; the role can only run `AWS-RunShellScript` on this one instance.

### Finish

1. Run every case in `docs/TEST_PLAN.md` on AWS and fill in results; record real problems in the
   issue log in `docs/TROUBLESHOOTING.md`.
2. Update the report (`docs/Project_TicketDesk_POC_Report.docx`) statuses and evidence.
3. Demo (10 min): architecture → user raises ticket + screenshot → S3 version + Lambda log line →
   agent resolves/closes → dashboard → CloudWatch dashboard → RDS private + IAM → reboot test.
4. **Teardown:**
   ```bash
   ./deploy/aws/teardown.sh          # terraform destroy; prints remaining state count (expect 0)
   ```
   Then confirm in the console: no EC2, RDS, S3 bucket, Lambda, `ticketdesk` log groups or alarms left.
   The RDS-managed secret is deleted with the database.

## Costs

Instance types are free-tier eligible, but what's free depends on your account. Set a billing budget
before starting and run the teardown when you're done — RDS is the most likely charge if left running.
