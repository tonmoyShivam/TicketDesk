"""Attachment storage: local disk for development, Amazon S3 on AWS.

On AWS the app uses the EC2 instance role (no access keys). Downloads are
served as short-lived pre-signed URLs, so the bucket stays fully private.
The Lambda file processor tags each uploaded object; `processing_status`
reads those tags so the UI can show what the Lambda decided.
"""
from __future__ import annotations

import logging
import re
import shutil
import uuid
from pathlib import Path
from typing import BinaryIO

from fastapi.responses import FileResponse, RedirectResponse, Response

from .config import Settings

log = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "pdf", "txt", "log", "csv", "docx", "xlsx"}


def safe_filename(name: str) -> str:
    base = (name or "").replace("\\", "/").split("/")[-1]
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._")
    return base[:100] or "file"


def extension_of(name: str) -> str:
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


def build_key(prefix: str, ticket_id: int, filename: str) -> str:
    return f"{prefix}tickets/{ticket_id}/{uuid.uuid4().hex}-{safe_filename(filename)}"


class LocalStorage:
    backend = "local"

    def __init__(self, root: str):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if self.root not in path.parents:
            raise ValueError("invalid storage key")
        return path

    def save(self, key: str, fileobj: BinaryIO, content_type: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as out:
            shutil.copyfileobj(fileobj, out)

    def download_response(self, key: str, filename: str, content_type: str) -> Response:
        return FileResponse(self._path(key), filename=safe_filename(filename), media_type=content_type)

    def processing_status(self, key: str) -> dict[str, str]:
        return {"processing-status": "local"}


class S3Storage:
    backend = "s3"

    def __init__(self, bucket: str, region: str | None):
        import boto3
        from botocore.config import Config

        self.bucket = bucket
        self.client = boto3.client("s3", region_name=region, config=Config(signature_version="s3v4"))

    def save(self, key: str, fileobj: BinaryIO, content_type: str) -> None:
        self.client.upload_fileobj(
            fileobj,
            self.bucket,
            key,
            ExtraArgs={"ContentType": content_type, "ServerSideEncryption": "AES256"},
        )
        log.info("Uploaded s3://%s/%s", self.bucket, key)

    def download_response(self, key: str, filename: str, content_type: str) -> Response:
        url = self.client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": self.bucket,
                "Key": key,
                "ResponseContentDisposition": f'attachment; filename="{safe_filename(filename)}"',
            },
            ExpiresIn=300,
        )
        return RedirectResponse(url, status_code=302)

    def processing_status(self, key: str) -> dict[str, str]:
        from botocore.exceptions import ClientError

        try:
            tags = self.client.get_object_tagging(Bucket=self.bucket, Key=key)["TagSet"]
        except ClientError as exc:
            log.warning("Could not read tags for %s: %s", key, exc)
            return {"processing-status": "unknown"}
        result = {t["Key"]: t["Value"] for t in tags}
        result.setdefault("processing-status", "pending")
        return result


def build_storage(settings: Settings):
    if settings.storage_backend == "s3":
        return S3Storage(settings.s3_bucket, settings.aws_region)
    return LocalStorage(settings.upload_dir)
