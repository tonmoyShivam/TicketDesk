# Architecture and security

## Architecture

```
                          Internet (allowed CIDR only, port 80)
                                       │
┌─ VPC 10.0.0.0/16 ────────────────────┼───────────────────────────────────────┐
│                                      ▼                                       │
│  Public subnet 10.0.1.0/24   ┌─────────────────────────────────┐             │
│                              │ EC2 ticketdesk-app (AL2023)     │             │
│                              │ Docker Compose:                 │             │
│                              │   nginx :80 ──▶ app :8000       │             │
│                              │ role: ticketdesk-ec2-role       │             │
│                              └───────┬──────────────────┬──────┘             │
│                       5432, TLS      │                  │ HTTPS (AWS APIs)    │
│  Private subnets          ┌──────────▼─────┐            │                    │
│  10.0.10.0/24 (AZ a)      │ RDS PostgreSQL │            │                    │
│  10.0.11.0/24 (AZ b)      │ 16, private    │            │                    │
│  (no internet route)      └────────────────┘            │                    │
└─────────────────────────────────────────────────────────┼────────────────────┘
                                                          │
     ┌──────────────────┬─────────────────┬───────────────┼──────────────────┐
     ▼                  ▼                 ▼               ▼                  ▼
Secrets Manager   S3 attachments     SSM (Session    CloudWatch Logs    CloudWatch
(RDS-managed      private, SSE-S3,   Manager, Run    /ticketdesk/app    dashboard +
 secret)          versioned          Command)        /aws/lambda/...    alarms ─▶ SNS
                       │ ObjectCreated attachments/*        ▲
                       ▼                                    │
                Lambda file-processor ── tags object ───────┘ JSON audit log

GitHub Actions ──OIDC──▶ deploy role ──ssm:SendCommand──▶ EC2 (git pull + compose rebuild)
```

**Upload:** browser → nginx → app checks type/size → `PutObject` to
`attachments/tickets/<id>/<uuid>-<name>` → DB row → S3 event → Lambda checks extension, size and
magic bytes, computes SHA-256, writes tags → app shows *processed* / *rejected*.

**Download:** app checks the user may see the ticket → 5-minute pre-signed URL.

## The five pass/fail requirements

| # | Requirement | How it's met | Evidence to show |
|---|---|---|---|
| 1 | No credentials in the repository | Config only from env vars; `.env` and `terraform.tfvars` git-ignored. RDS generates the DB password into Secrets Manager (not in code, user data or state). `SECRET_KEY` generated on the instance. EC2, Lambda and GitHub Actions use IAM roles/OIDC — no access keys anywhere. | `git grep -n -i -E "AKIA\|password="`; `pytest tests/test_lambda_and_infra.py` (secret scan) |
| 2 | Least-privilege IAM | Table below; every statement names a specific bucket prefix, secret, log group or instance. | IAM console → roles `ticketdesk-*` |
| 3 | RDS not public | `publicly_accessible = false`; private subnets with no internet route; DB SG accepts 5432 only from the app SG; `rds.force_ssl = 1`. | `aws rds describe-db-instances`; DB SG inbound rule |
| 4 | Repeatable deployment | Terraform modules + idempotent bootstrap/`install.sh`; offline `terraform test` and CI validate every change. | destroy → apply → app works; CI run |
| 5 | Clean teardown | All resources in Terraform state; bucket `force_destroy` drains all versions; RDS skips final snapshot; RDS log group pre-created so it's destroyed too. | `teardown.sh` prints 0 remaining |

## IAM

| Role | Actions | Resource |
|---|---|---|
| `ticketdesk-ec2-role` | `s3:PutObject`, `s3:GetObject`, `s3:GetObjectTagging` | `arn:aws:s3:::<bucket>/attachments/*` |
| | `secretsmanager:GetSecretValue` | the single RDS-managed secret |
| | `logs:CreateLogStream`, `logs:PutLogEvents`, `logs:DescribeLogStreams` | `/ticketdesk/app` log group |
| | `AmazonSSMManagedInstanceCore` (AWS managed) | Session Manager / Run Command (replaces SSH) |
| `ticketdesk-file-processor-role` | `s3:GetObject`, `s3:PutObjectTagging` | `<bucket>/attachments/*` |
| | `logs:CreateLogStream`, `logs:PutLogEvents` | its own log group |
| `ticketdesk-github-deploy` (optional) | `ssm:SendCommand` | this instance + `AWS-RunShellScript` document only |
| | `ssm:GetCommandInvocation`, `ssm:ListCommandInvocations` | `*` (these read-only actions don't support resource scoping) |
| | trust | GitHub OIDC, audience `sts.amazonaws.com`, subject `repo:<owner>/<repo>:ref:refs/heads/main` |

Deliberately not granted: `s3:ListBucket`, `s3:DeleteObject`, `s3:*`, other secrets, `logs:CreateLogGroup`,
`ec2:*`, `AdministratorAccess`.

## Other controls

- **Network:** no port 22; HTTP limited to `allowed_http_cidr`; egress limited to 80/443 and 5432 to the DB SG;
  app container reachable only by nginx on the Compose network.
- **Instance:** IMDSv2 required (hop limit 2 so the container can use the role), encrypted root volume,
  app container runs as a non-root user.
- **Data:** RDS storage encrypted, TLS enforced (`rds.force_ssl` + `sslmode=require`), 7-day automated
  backups; S3 SSE-S3, versioning (30-day recovery window), TLS-only bucket policy, public access blocked.
- **Application:** PBKDF2-SHA256 (600k iterations), signed 8-hour sessions, CSRF tokens, per-user ticket
  visibility, role checks on status changes, file type/size checks in the app and Lambda.
- **Monitoring:** container logs in CloudWatch; metric filters for app errors and failed logins; 6 alarms
  to SNS; operations dashboard.

## Known limits

- HTTP only — HTTPS needs a domain and certificate (ACM + load balancer, or Let's Encrypt on nginx).
- Single EC2 instance and single-AZ RDS: fine for a POC, not highly available.
- Terraform state is local; a team should move it to an S3 backend with locking (commented in `versions.tf`).
- The image is built on the instance; a production setup would push to ECR from CI.
