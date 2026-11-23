import importlib.util
import io
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50


@pytest.fixture
def processor(monkeypatch):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "ap-south-1")
    spec = importlib.util.spec_from_file_location("file_processor", ROOT / "lambda" / "file_processor.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    class FakeS3:
        def __init__(self):
            self.objects = {}
            self.tags = {}

        def get_object(self, Bucket, Key):
            data = self.objects[Key]
            return {"Body": io.BytesIO(data), "ContentLength": len(data), "ContentType": "x", "VersionId": "v1"}

        def put_object_tagging(self, Bucket, Key, Tagging):
            self.tags[Key] = {t["Key"]: t["Value"] for t in Tagging["TagSet"]}

    module.s3 = FakeS3()
    return module


def event(key):
    return {"Records": [{"s3": {"bucket": {"name": "b"}, "object": {"key": key}}}]}


def run(processor, key, data, event_key=None):
    processor.s3.objects[key] = data
    processor.handler(event(event_key or key), None)
    return processor.s3.tags[key]


def test_valid_text_file_gets_checksum(processor):
    tags = run(processor, "attachments/tickets/1/abc-log file.txt", b"hello",
               event_key="attachments/tickets/1/abc-log+file.txt")
    assert tags["processing-status"] == "processed"
    assert tags["sha256"] == "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"


def test_valid_png(processor):
    assert run(processor, "attachments/a.png", PNG)["processing-status"] == "processed"


def test_rejects_disallowed_extension(processor):
    tags = run(processor, "attachments/x.exe", b"MZ\x90\x00")
    assert tags == {"processing-status": "rejected", "reason": "file type not allowed"}


def test_rejects_renamed_executable(processor):
    tags = run(processor, "attachments/photo.png", b"MZ\x90\x00" + b"\x00" * 60)
    assert tags["reason"] == "content does not match extension"


def test_rejects_binary_disguised_as_text(processor):
    tags = run(processor, "attachments/notes.txt", b"\x00\x01\x02binary")
    assert tags["processing-status"] == "rejected"


def test_rejects_empty_and_oversized(processor, monkeypatch):
    assert run(processor, "attachments/e.txt", b"")["reason"] == "empty file"
    monkeypatch.setattr(processor, "MAX_BYTES", 10)
    assert run(processor, "attachments/big.txt", b"x" * 11)["reason"] == "file too large"


def test_docx_is_zip(processor):
    assert run(processor, "attachments/r.docx", b"PK\x03\x04rest")["processing-status"] == "processed"


def test_terraform_layout():
    tf = ROOT / "terraform"
    for module in ["network", "security", "iam", "rds", "s3", "lambda", "cloudwatch", "ec2"]:
        assert (tf / "modules" / module / "main.tf").exists(), module
    main = (tf / "main.tf").read_text()
    assert "lambda/file_processor.py" in main
    rds = (tf / "modules" / "rds" / "main.tf").read_text()
    assert "publicly_accessible    = false" in rds and "manage_master_user_password = true" in rds


def test_no_secrets_committed():
    suspicious = ["AKIA", "aws_secret_access_key", "BEGIN RSA PRIVATE KEY", "BEGIN OPENSSH PRIVATE KEY"]
    exts = {".py", ".tf", ".tftpl", ".yaml", ".yml", ".sh", ".txt", ".conf", ".example", ".json"}
    skip = {".git", ".terraform", ".venv", "node_modules"}
    for path in ROOT.rglob("*"):
        if path.is_file() and not skip & set(path.parts) and path.suffix in exts:
            if path.name == "test_lambda_and_infra.py":
                continue
            text = path.read_text(errors="ignore")
            for marker in suspicious:
                assert marker not in text, f"{marker} found in {path}"
