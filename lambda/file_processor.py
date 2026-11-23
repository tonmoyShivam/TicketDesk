"""TicketDesk attachment processor (AWS Lambda).

Triggered by S3 ObjectCreated events under attachments/. For each new file it:
  1. checks the extension against the allow-list and the size against the 10 MB limit,
  2. sniffs the real file type from its first bytes (magic numbers) and rejects files
     whose content doesn't match their extension (e.g. an .exe renamed to .png),
  3. computes a SHA-256 checksum,
  4. records the outcome as S3 object tags (shown in the TicketDesk UI) and writes
     one structured JSON audit line to CloudWatch Logs.
"""
import hashlib
import json
import logging
import os
import urllib.parse

import boto3
from botocore.exceptions import ClientError

log = logging.getLogger()
log.setLevel(logging.INFO)
s3 = boto3.client("s3")

ALLOWED = set(os.environ.get("ALLOWED_EXTENSIONS", "png,jpg,jpeg,gif,pdf,txt,log,csv,docx,xlsx").split(","))
MAX_BYTES = int(os.environ.get("MAX_BYTES", str(10 * 1024 * 1024)))

# Which detected content types each extension may contain.
EXPECTED = {
    "png": {"image/png"},
    "jpg": {"image/jpeg"},
    "jpeg": {"image/jpeg"},
    "gif": {"image/gif"},
    "pdf": {"application/pdf"},
    "docx": {"application/zip"},
    "xlsx": {"application/zip"},
    "txt": {"text/plain"},
    "log": {"text/plain"},
    "csv": {"text/plain"},
}


def sniff(head):
    """Detect a file type from its first bytes."""
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if head.startswith(b"%PDF-"):
        return "application/pdf"
    if head.startswith(b"PK\x03\x04"):
        return "application/zip"
    if head.startswith(b"MZ"):
        return "application/x-msdownload"
    if head.startswith(b"\x7fELF"):
        return "application/x-executable"
    if b"\x00" not in head:
        try:
            head.decode("utf-8")
            return "text/plain"
        except UnicodeDecodeError:
            # the 4 KB sample may end mid-character
            try:
                head[:-3].decode("utf-8")
                return "text/plain"
            except UnicodeDecodeError:
                pass
    return "application/octet-stream"


def evaluate(key, size, detected):
    ext = key.rsplit(".", 1)[-1].lower() if "." in key.rsplit("/", 1)[-1] else ""
    if ext not in ALLOWED:
        return "rejected", "file type not allowed"
    if size == 0:
        return "rejected", "empty file"
    if size > MAX_BYTES:
        return "rejected", "file too large"
    if detected not in EXPECTED.get(ext, set()):
        return "rejected", "content does not match extension"
    return "processed", "ok"


def handler(event, context):
    results = []
    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        key = urllib.parse.unquote_plus(record["s3"]["object"]["key"])
        try:
            obj = s3.get_object(Bucket=bucket, Key=key)
        except ClientError as err:
            log.warning(json.dumps({"event": "attachment_missing", "key": key, "error": str(err)}))
            continue

        body = obj["Body"]
        size = obj["ContentLength"]
        head = body.read(4096)
        detected = sniff(head)
        status, reason = evaluate(key, size, detected)

        tags = {"processing-status": status, "reason": reason}
        if status == "processed":
            digest = hashlib.sha256(head)
            for chunk in iter(lambda: body.read(1024 * 1024), b""):
                digest.update(chunk)
            tags["sha256"] = digest.hexdigest()
        body.close()

        s3.put_object_tagging(
            Bucket=bucket,
            Key=key,
            Tagging={"TagSet": [{"Key": k, "Value": v} for k, v in tags.items()]},
        )
        result = {
            "event": "attachment_processed",
            "bucket": bucket,
            "key": key,
            "version_id": obj.get("VersionId"),
            "size": size,
            "declared_type": obj.get("ContentType"),
            "detected_type": detected,
            **tags,
        }
        log.info(json.dumps(result))
        results.append(result)
    return {"processed": len(results), "results": results}
