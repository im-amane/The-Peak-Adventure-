import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from offsite_backup import download_backup, restore_offsite_postgres_backup, upload_backup, upload_backup_from_environment


class FakeS3Client:
    def __init__(self, data=b"verified backup bytes"):
        self.calls = []
        self.data = data

    def upload_file(self, filename, bucket, key, ExtraArgs):
        self.calls.append((filename, bucket, key, ExtraArgs))

    def head_object(self, Bucket, Key):
        import hashlib
        return {
            "ContentLength": len(self.data),
            "Metadata": {"sha256": hashlib.sha256(self.data).hexdigest()},
        }

    def download_file(self, bucket, key, filename):
        Path(filename).write_bytes(self.data)


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

    def test_download_verifies_checksum_before_publishing_file(self):
        destination = Path(self.temp.name) / "restored" / "database.dump"
        result = download_backup(
            bucket="peak-backups", key="prod/postgres/database.dump",
            destination=destination, s3_client=self.client,
        )
        self.assertEqual(result, destination)
        self.assertEqual(destination.read_bytes(), b"verified backup bytes")

    def test_download_rejects_checksum_mismatch_and_preserves_existing_destination(self):
        destination = Path(self.temp.name) / "database.dump"
        destination.write_bytes(b"known good local file")
        client = FakeS3Client(data=b"tampered remote bytes")
        client.head_object = lambda **kwargs: {
            "ContentLength": len(b"tampered remote bytes"),
            "Metadata": {"sha256": "0" * 64},
        }
        with self.assertRaisesRegex(ValueError, "SHA-256 verification"):
            download_backup(
                bucket="peak-backups", key="database.dump",
                destination=destination, s3_client=client,
            )
        self.assertEqual(destination.read_bytes(), b"known good local file")

    def test_download_can_recreate_postgres_checksum_sidecar_from_verified_metadata(self):
        destination = Path(self.temp.name) / "database.dump"
        result = download_backup(
            bucket="peak-backups", key="database.dump", destination=destination,
            write_checksum_sidecar=True, s3_client=self.client,
        )
        sidecar = Path(str(result) + ".sha256")
        self.assertTrue(sidecar.is_file())
        self.assertEqual(
            sidecar.read_text(encoding="ascii"),
            hashlib.sha256(destination.read_bytes()).hexdigest()
            + "  database.dump\n",
        )

    def test_download_rejects_missing_checksum_metadata(self):
        client = FakeS3Client()
        client.head_object = lambda **kwargs: {
            "ContentLength": len(client.data), "Metadata": {},
        }
        with self.assertRaisesRegex(ValueError, "missing valid SHA-256"):
            download_backup(
                bucket="peak-backups", key="database.dump",
                destination=Path(self.temp.name) / "database.dump",
                s3_client=client,
            )

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

    def test_offsite_restore_verifies_archive_and_requires_disposable_target(self):
        captured = {}
        def verify(path, database_url):
            captured["path"] = path
            captured["database_url"] = database_url
            return True
        def restore(path, database_url, *, confirm_database):
            self.assertTrue(path.is_file())
            captured["confirmed"] = confirm_database
        with patch("postgres_backup.verify_backup", side_effect=verify) as verify_mock, patch(
            "postgres_backup.restore_backup", side_effect=restore
        ) as restore_mock:
            result = restore_offsite_postgres_backup(
                bucket="peak-backups", key="nightly/source.dump",
                database_url="postgresql://user:pass@localhost/peak_restore_test",
                confirm_database="peak_restore_test", target_database_is_disposable=True,
                s3_client=self.client,
            )
        verify_mock.assert_called_once()
        restore_mock.assert_called_once()
        self.assertEqual(captured["confirmed"], "peak_restore_test")
        self.assertFalse(captured["path"].exists(), "temporary off-site archive must be removed")
        self.assertEqual(result["object_key"], "nightly/source.dump")
        self.assertTrue(result["verified"] and result["restored"])

    def test_offsite_restore_requires_explicit_disposable_target_confirmation(self):
        with self.assertRaisesRegex(ValueError, "explicit confirmation"):
            restore_offsite_postgres_backup(
                bucket="peak-backups", key="nightly/source.dump",
                database_url="postgresql://user:pass@localhost/peak_restore_test",
                confirm_database="peak_restore_test", target_database_is_disposable=False,
                s3_client=self.client,
            )
        self.assertEqual(self.client.calls, [])

    def test_offsite_restore_stops_when_archive_is_not_readable(self):
        with patch("postgres_backup.verify_backup", return_value=False), patch(
            "postgres_backup.restore_backup"
        ) as restore_mock:
            with self.assertRaisesRegex(RuntimeError, "failed local integrity or readability"):
                restore_offsite_postgres_backup(
                    bucket="peak-backups", key="nightly/source.dump",
                    database_url="postgresql://user:pass@localhost/peak_restore_test",
                    confirm_database="peak_restore_test", target_database_is_disposable=True,
                    s3_client=self.client,
                )
        restore_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
