import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from offsite_backup import upload_backup, upload_backup_from_environment


class FakeS3Client:
    def __init__(self):
        self.calls = []

    def upload_file(self, filename, bucket, key, ExtraArgs):
        self.calls.append((filename, bucket, key, ExtraArgs))


class OffsiteBackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "database.dump"
        self.path.write_bytes(b"verified backup bytes")
        self.client = FakeS3Client()

    def tearDown(self):
        self.temp.cleanup()

    def test_upload_includes_checksum_metadata_and_encryption(self):
        key = upload_backup(
            self.path, bucket="peak-backups", region="ap-south-1",
            prefix="prod/postgres", s3_client=self.client,
        )
        self.assertEqual(key, "prod/postgres/database.dump")
        args = self.client.calls[0][3]
        self.assertEqual(args["ServerSideEncryption"], "AES256")
        self.assertEqual(len(args["Metadata"]["sha256"]), 64)

    def test_upload_supports_customer_managed_kms_key(self):
        upload_backup(
            self.path, bucket="peak-backups", kms_key_id="alias/peak-backups",
            s3_client=self.client,
        )
        args = self.client.calls[0][3]
        self.assertEqual(args["ServerSideEncryption"], "aws:kms")
        self.assertEqual(args["SSEKMSKeyId"], "alias/peak-backups")

    def test_rejects_empty_or_missing_backup(self):
        missing = Path(self.temp.name) / "missing.dump"
        with self.assertRaisesRegex(ValueError, "missing or empty"):
            upload_backup(missing, bucket="peak-backups", s3_client=self.client)

    def test_rejects_invalid_bucket_and_unsafe_prefix(self):
        with self.assertRaisesRegex(ValueError, "bucket name"):
            upload_backup(self.path, bucket="Bad_Bucket", s3_client=self.client)
        with self.assertRaisesRegex(ValueError, "unsafe path"):
            upload_backup(self.path, bucket="peak-backups", prefix="../escape", s3_client=self.client)

    def test_environment_export_is_disabled_without_bucket(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(upload_backup_from_environment(self.path))

    def test_environment_export_uses_configured_bucket(self):
        with patch.dict(os.environ, {
            "OFFSITE_BACKUP_BUCKET": "peak-backups",
            "OFFSITE_BACKUP_REGION": "ap-south-1",
            "OFFSITE_BACKUP_PREFIX": "nightly",
        }, clear=True):
            with patch("offsite_backup.upload_backup", return_value="nightly/database.dump") as upload:
                result = upload_backup_from_environment(self.path)
        self.assertEqual(result, "nightly/database.dump")
        upload.assert_called_once_with(
            self.path, bucket="peak-backups", region="ap-south-1",
            prefix="nightly", endpoint_url=None, kms_key_id=None,
        )


if __name__ == "__main__":
    unittest.main()
