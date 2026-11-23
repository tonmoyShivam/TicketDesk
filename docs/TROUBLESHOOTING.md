# Troubleshooting

Check the logs before changing anything.

## Where the logs are

| What | Command / place |
|---|---|
| First-boot bootstrap | `sudo cat /var/log/ticketdesk-bootstrap.log` |
| Application + nginx | `aws logs tail /ticketdesk/app --follow` (CloudWatch, streams `app`, `nginx`) |
| Containers | `cd /opt/ticketdesk/app && sudo docker compose --env-file /etc/ticketdesk/compose.env -f deploy/ec2/docker-compose.prod.yml ps` |
| Lambda | `aws logs tail /aws/lambda/ticketdesk-file-processor --follow` |
| Terraform | the error printed by `terraform apply`; `TF_LOG=DEBUG` for detail |
| RDS | `/aws/rds/instance/ticketdesk-db/postgresql` log group, or console → database → Logs & events |

## Common problems

| Symptom | Likely cause | Fix |
|---|---|---|
| `terraform apply` finishes but the URL doesn't load | First boot still running (~5 min) or bootstrap failed | Session Manager → `sudo tail -100 /var/log/ticketdesk-bootstrap.log` |
| Bootstrap: `git clone` fails | Wrong `repo_url`/branch or private repo | Fix `terraform.tfvars`, `terraform apply` (user data change replaces the instance) |
| `EntityAlreadyExists` for the OIDC provider | Account already has the GitHub provider | Set `create_github_oidc_provider = false` |
| `BucketAlreadyExists` | Name collision (rare: name includes account + region) | Change `project` |
| Browser times out | Your IP changed, so the SG no longer allows you | Update `allowed_http_cidr` in `terraform.tfvars` and `terraform apply` (changes only the SG rule) |
| `502 Bad Gateway` | nginx is up, the app container isn't | `docker compose ... logs app` or the `app` stream in CloudWatch; usually a config error at startup |
| Containers start but no logs in CloudWatch | Role lacks `logs:PutLogEvents` on the group, or wrong `APP_LOG_GROUP` | Check `/etc/ticketdesk/compose.env` and the role policy |
| App can't reach S3/Secrets Manager from the container (`Unable to locate credentials`) | IMDS hop limit 1 | Instance metadata hop limit must be 2 (set in Terraform) |
| App log: `Invalid configuration: ...` | Missing variable in `/etc/ticketdesk/ticketdesk.env` | Fix the file, then `sudo bash /opt/ticketdesk/app/deploy/ec2/install.sh` |
| `/health` → `database: unreachable` | DB SG rule, RDS still starting, or wrong `DB_HOST` | Check RDS status is *Available*; DB SG inbound source = app SG |
| `AccessDeniedException ... secretsmanager:GetSecretValue` | Role policy doesn't match the secret ARN | Compare `DB_SECRET_ARN` in the env file with the role policy resource |
| Upload fails, log shows `AccessDenied` on `PutObject` | Key outside `attachments/` or bucket policy | Keys must start with `attachments/`; requests must use HTTPS (boto3 does) |
| Upload works but status stays **pending** | Lambda didn't run or failed | `aws logs tail ...`; check bucket → Properties → Event notifications; Lambda → Monitor |
| Status shows **unknown** | App role lacks `s3:GetObjectTagging` | Check the role policy |
| `413 Request Entity Too Large` | File > nginx limit (12 MB) | Expected for big files; app limit is 10 MB |
| `Form expired` | Session expired or opened in another tab after logout | Reload the page and resubmit |
| Locally: `connection refused` on 5432 | Postgres container not running | `docker compose up -d db`; `docker compose logs db` |

### Private repository

The instance clones over HTTPS without credentials. For a private repo either make it public for the
POC (it contains no secrets), or: create a fine-grained read-only GitHub token, store it in Secrets
Manager, grant the instance role `GetSecretValue` on it, and clone with it in user data. Never put
the token in Terraform variables or the repo.

### Teardown leaves something behind

`terraform state list` should be empty after `teardown.sh`. Anything still in the console was created
by hand: delete it, and add it to the issue log.

## Issue log (fill in during the POC)

Record every real issue — the review asks how you troubleshoot.

| # | Date | Milestone | Symptom / error message | What I checked | Root cause | Fix |
|---|---|---|---|---|---|---|
| 1 | | | | | | |
| 2 | | | | | | |
| 3 | | | | | | |
