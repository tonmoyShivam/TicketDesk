"""Database engine setup.

Two modes:
  * DATABASE_URL set  -> connect with it directly (local PostgreSQL or SQLite).
  * DB_HOST + DB_SECRET_ARN -> Amazon RDS. The username/password are read from
    the RDS-managed secret in AWS Secrets Manager each time a new connection is
    opened (cached for a few minutes). If RDS rotates the password, the next
    failed login triggers a fresh read, so the app keeps working without a
    restart and without the password ever being written to disk.
"""
from __future__ import annotations

import json
import logging
import threading
import time

from sqlalchemy import create_engine, event
from sqlalchemy.engine import URL, Engine
from sqlalchemy.orm import DeclarativeBase

from .config import Settings

log = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


class SecretsManagerCredentials:
    """Reads {"username", "password"} from a Secrets Manager secret, with a short cache."""

    def __init__(self, secret_arn: str, region: str | None, ttl_seconds: int = 300):
        import boto3  # imported lazily so local runs don't need AWS libraries configured

        self._client = boto3.client("secretsmanager", region_name=region)
        self._arn = secret_arn
        self._ttl = ttl_seconds
        self._lock = threading.Lock()
        self._value: tuple[str, str] | None = None
        self._fetched_at = 0.0

    def get(self, force_refresh: bool = False) -> tuple[str, str]:
        with self._lock:
            stale = time.monotonic() - self._fetched_at > self._ttl
            if force_refresh or self._value is None or stale:
                secret = json.loads(self._client.get_secret_value(SecretId=self._arn)["SecretString"])
                self._value = (secret["username"], secret["password"])
                self._fetched_at = time.monotonic()
                log.info("Database credentials loaded from Secrets Manager")
            return self._value


def build_engine(settings: Settings) -> Engine:
    if settings.database_url:
        kwargs: dict = {"pool_pre_ping": True}
        if settings.database_url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False}
        return create_engine(settings.database_url, **kwargs)

    url = URL.create(
        "postgresql+psycopg",
        host=settings.db_host,
        port=settings.db_port,
        database=settings.db_name,
    )
    engine = create_engine(
        url,
        pool_pre_ping=True,
        pool_recycle=1800,
        # RDS PostgreSQL enforces TLS by default; require it on our side too.
        connect_args={"sslmode": "require", "connect_timeout": 5},
    )
    credentials = SecretsManagerCredentials(settings.db_secret_arn, settings.aws_region)

    @event.listens_for(engine, "do_connect")
    def _connect_with_secret(dialect, conn_rec, cargs, cparams):
        user, password = credentials.get()
        cparams.update(user=user, password=password)
        try:
            return dialect.loaded_dbapi.connect(*cargs, **cparams)
        except Exception as exc:  # password rotated since we cached it?
            if "password authentication failed" not in str(exc):
                raise
            log.warning("Database login failed; refreshing credentials from Secrets Manager")
            user, password = credentials.get(force_refresh=True)
            cparams.update(user=user, password=password)
            return dialect.loaded_dbapi.connect(*cargs, **cparams)

    return engine
