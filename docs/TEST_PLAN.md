# Test plan and results

Run each case locally (M1) and again on AWS (M5). Fill in **Result** (Pass/Fail) and **Notes**
(evidence: screenshot name, log line, command output). Automated coverage: `pytest -q` (22 tests) and `terraform test` (3 mocked runs) — both run in GitHub Actions CI.

Test accounts: one `admin`, one `agent`, two `user` accounts (e.g. `ravi`, `meena`).

## Application

| ID | Area | Steps | Expected | Local | AWS | Notes |
|---|---|---|---|---|---|---|
| TC-01 | Login | Log in as `ravi` with the correct password | Dashboard shows "Your tickets" | | | |
| TC-02 | Login | Wrong password | "Invalid username or password", stays on login, warning in app log | | | |
| TC-03 | Login | Open `/dashboard` in a private window | Redirected to `/login` | | | |
| TC-04 | Logout | Click Log out, then press Back and reload | Redirected to `/login` | | | |
| TC-05 | Create | New ticket with title, category, priority, description | Ticket page, status **Open**, history shows "created" | | | |
| TC-06 | Create | Submit with a 1-character title and empty description | Validation errors, nothing saved | | | |
| TC-07 | View | Tickets page; filter by status; search a word from a description | Correct rows only | | | |
| TC-08 | Visibility | As `meena`, open `ravi`'s ticket URL | 404 Not found | | | |
| TC-09 | Status | As `agent`: Open → In Progress → Resolved → Closed | Each change saved, shown in history with note; auto-assigned to agent on In Progress | | | |
| TC-10 | Status | As `agent` on an Open ticket, use browser dev tools to change the *Move to* option's value to `Closed` and submit | Rejected: "Can't move a ticket from Open to Closed" | | | |
| TC-11 | Status | As `ravi` (user role) | No status controls shown; direct POST returns 403 | | | |
| TC-12 | Dashboard | Compare counts with the tickets list | Status and priority counts match | | | |
| TC-13 | Attachment | Upload a PNG to a ticket | Listed with size; download works | | | |
| TC-14 | Attachment | Upload `.exe`, an empty file, and a 12 MB file | Each refused with a clear message | | | |
| TC-15 | Attachment | As `meena`, open `/attachments/<id>` of `ravi`'s file | 404 | | | |
| TC-16 | Health | `curl <url>/health` | `{"status":"ok","database":"ok",...}` | | | |

## AWS integration

| ID | Area | Steps | Expected | Result | Notes |
|---|---|---|---|---|---|
| AWS-01 | EC2 | Open `AppUrl` from an allowed IP | Login page loads | | |
| AWS-02 | EC2 | Open `AppUrl` from a non-allowed network (mobile data) | Times out (SG blocks it) | | |
| AWS-03 | EC2 | `sudo docker restart $(sudo docker ps -q)`, reload page | Back within ~10 s | | |
| AWS-04 | EC2 | `sudo reboot`, wait 1–2 min | App returns without manual steps | | |
| AWS-05 | RDS | `/health` + query ticket counts from the instance (DEPLOYMENT.md M3) | Counts match the dashboard | | |
| AWS-06 | RDS | `aws rds describe-db-instances` | `PubliclyAccessible: false` | | |
| AWS-07 | RDS | DB security group inbound rules | Only 5432 from the app SG | | |
| AWS-08 | S3 | Upload via app, then `aws s3 ls s3://<bucket>/attachments/ --recursive` | Object exists under `attachments/tickets/<id>/` | | |
| AWS-09 | S3 | Open the object's S3 URL directly (not pre-signed) | AccessDenied | | |
| AWS-10 | S3 | Click a download link, wait > 5 min, reuse the URL | Expired | | |
| AWS-11 | Lambda | After upload, check `aws logs tail /aws/lambda/ticketdesk-file-processor` | One JSON log line per file, status processed | | |
| AWS-12 | Lambda | Ticket page after upload | Processing column shows **processed** + checksum | | |
| AWS-13 | Lambda | Rename a non-image file to `fake.png` and upload it in the app | Processing shows **rejected** — content does not match extension | | |
| AWS-14 | S3 | `aws s3api list-object-versions --bucket <bucket> --prefix attachments/` | Each object has a VersionId (versioning on) | | |
| CW-01 | CloudWatch | `aws logs tail /ticketdesk/app --since 10m` | `app` and `nginx` streams with recent requests | | |
| CW-02 | CloudWatch | Open the `ticketdesk-operations` dashboard | All widgets show data | | |
| CW-03 | CloudWatch | Log in 3 times with a wrong password, wait 5 min | FailedLogins metric > 0 on dashboard | | |
| CW-04 | CloudWatch | `aws cloudwatch set-alarm-state --alarm-name ticketdesk-lambda-errors --state-value ALARM --state-reason demo` | Alarm shows ALARM; SNS email arrives if configured | | |
| CI-01 | CI/CD | Push a commit to `main` | CI green; Deploy workflow redeploys via SSM | | |
| IAC-01 | Terraform | `terraform plan` right after apply | "No changes" (no drift) | | |

## Security

| ID | Check | Expected | Result | Notes |
|---|---|---|---|---|
| SEC-01 | `git grep -n -i -E "password=\|secret_key=\|AKIA"` on the pushed repo | Only placeholders in `.env.example` | | |
| SEC-02 | `pytest tests/test_lambda_and_infra.py -q` | Secret scan and Lambda checks pass | | |
| SEC-03 | IAM roles in console | Only the actions in ARCHITECTURE_AND_SECURITY.md | | |
| SEC-04 | App SG inbound | Port 80 from your IP only; no port 22 | | |
| SEC-05 | `sudo cat /etc/ticketdesk/ticketdesk.env` | No DB password in the file | | |
| SEC-06 | `sudo ls -l /etc/ticketdesk/ticketdesk.env` | `-rw------- root root` | | |
| SEC-07 | `./deploy/aws/teardown.sh`, then console check: EC2, RDS, S3, Lambda, log groups, alarms, secret | 0 resources in state; none left | | |

## Summary

| Total | Passed | Failed | Date | Tester |
|---|---|---|---|---|
| | | | | |
