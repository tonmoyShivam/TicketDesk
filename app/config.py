"""Application settings, read from environment variables only.

Nothing secret lives in this repository:
  * locally, values come from a git-ignored `.env` file;
  * on EC2, they come from /etc/ticketdesk/ticketdesk.env (written at boot,
    readable only by root and the app user), and the database password is
    fetched at runtime from AWS Secrets Manager using the instance's IAM role.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


def _bool(value: str | None) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Settings:
    # Database: either a full DATABASE_URL (local) or host + Secrets Manager ARN (AWS).
    database_url: str | None = None
    db_host: str | None = None
    db_port: int = 5432
    db_name: str = "ticketdesk"
    db_secret_arn: str | None = None
    aws_region: str | None = None

    # Attachments: "local" (disk) or "s3".
    storage_backend: str = "local"
    upload_dir: str = "./uploads"
    s3_bucket: str | None = None
    s3_prefix: str = "attachments/"
    max_upload_mb: int = 10

    # Sessions.
    secret_key: str = ""
    https_only_cookies: bool = False

    @classmethod
    def from_env(cls) -> "Settings":
        try:  # optional convenience for local development
            from dotenv import load_dotenv

            load_dotenv()
        except ImportError:
            pass

        settings = cls(
            database_url=os.getenv("DATABASE_URL") or None,
            db_host=os.getenv("DB_HOST") or None,
            db_port=int(os.getenv("DB_PORT", "5432")),
            db_name=os.getenv("DB_NAME", "ticketdesk"),
            db_secret_arn=os.getenv("DB_SECRET_ARN") or None,
            aws_region=os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or None,
            storage_backend=os.getenv("STORAGE_BACKEND", "local").lower(),
            upload_dir=os.getenv("UPLOAD_DIR", "./uploads"),
            s3_bucket=os.getenv("S3_BUCKET") or None,
            s3_prefix=os.getenv("S3_PREFIX", "attachments/"),
            max_upload_mb=int(os.getenv("MAX_UPLOAD_MB", "10")),
            secret_key=os.getenv("SECRET_KEY", ""),
            https_only_cookies=_bool(os.getenv("HTTPS_ONLY_COOKIES", "false")),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        problems = []
        if len(self.secret_key) < 32:
            problems.append("SECRET_KEY must be set to a random value of at least 32 characters")
        if not self.database_url and not (self.db_host and self.db_secret_arn):
            problems.append("set DATABASE_URL, or DB_HOST together with DB_SECRET_ARN")
        if self.storage_backend not in {"local", "s3"}:
            problems.append("STORAGE_BACKEND must be 'local' or 's3'")
        if self.storage_backend == "s3" and not self.s3_bucket:
            problems.append("S3_BUCKET is required when STORAGE_BACKEND=s3")
        if problems:
            raise RuntimeError("Invalid configuration: " + "; ".join(problems))

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024
