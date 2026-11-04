import unittest

from scripts.launch_preflight import inspect_environment


class LaunchPreflightTests(unittest.TestCase):
    def valid_environment(self):
        return {
            "BOT_TOKEN": "987654:valid-but-not-real-token",
            "WEBAPP_URL": "https://peak-adventure-edge.example.workers.dev",
            "ADMIN_IDS": "123456789",
            "DATABASE_PATH": "/data/peak_adventure.db",
            "BACKUP_INTERVAL_SECONDS": "21600",
            "BACKUP_RETENTION": "7",
            "ENABLE_TELEGRAM_STARS": "false",
        }

    def test_valid_controlled_prototype_configuration_warns_without_offsite_storage(self):
        issues = inspect_environment(self.valid_environment())
        self.assertEqual({issue["code"] for issue in issues}, {"offsite_backup_not_configured"})
        self.assertEqual(issues[0]["severity"], "warning")

    def test_missing_webapp_url_is_an_error_without_echoing_bot_token(self):
        env = self.valid_environment()
        secret = "sensitive-bot-token-value"
        env["BOT_TOKEN"] = secret
        env["WEBAPP_URL"] = ""
        issues = inspect_environment(env)
        codes = {issue["code"] for issue in issues}
        self.assertIn("webapp_url_missing", codes)
        self.assertNotIn(secret, str(issues))

    def test_rejects_http_webapp_url_and_invalid_admin_ids(self):
        env = self.valid_environment()
        env["WEBAPP_URL"] = "http://example.com"
        env["ADMIN_IDS"] = "123,not-a-number"
        codes = {issue["code"] for issue in inspect_environment(env)}
        self.assertIn("webapp_url_invalid", codes)
        self.assertIn("admin_ids_invalid", codes)

    def test_rejects_placeholder_bot_token_and_invalid_database_url(self):
        env = self.valid_environment()
        env["BOT_TOKEN"] = "123456:replace_with_your_bot_token"
        env["DATABASE_URL"] = "sqlite:///local.db"
        codes = {issue["code"] for issue in inspect_environment(env)}
        self.assertIn("bot_token_placeholder", codes)
        self.assertIn("database_url_invalid", codes)

    def test_flags_non_persistent_relative_sqlite_path(self):
        env = self.valid_environment()
        env["DATABASE_PATH"] = "peak_adventure.db"
        issues = inspect_environment(env)
        self.assertIn("database_path_not_absolute", {issue["code"] for issue in issues})

    def test_valid_postgres_url_and_payment_disabled_configuration(self):
        env = self.valid_environment()
        env.pop("DATABASE_PATH")
        env["DATABASE_URL"] = "postgresql://user:password@db.example.com:5432/peak"
        env["POSTGRES_BACKUP_DIR"] = "/data/postgres_backups"
        self.assertEqual({issue["code"] for issue in inspect_environment(env)}, {"offsite_backup_not_configured"})

    def test_invalid_port_and_backup_settings_are_errors(self):
        env = self.valid_environment()
        env["PORT"] = "70000"
        env["BACKUP_INTERVAL_SECONDS"] = "60"
        env["BACKUP_RETENTION"] = "0"
        codes = {issue["code"] for issue in inspect_environment(env)}
        self.assertIn("web_port_invalid", codes)
        self.assertIn("backup_interval_invalid", codes)
        self.assertIn("backup_retention_invalid", codes)

    def test_postgres_backup_configuration_defaults_to_database_mount(self):
        env = self.valid_environment()
        env.pop("DATABASE_PATH")
        env["DATABASE_URL"] = "postgresql://user:password@db.example.com:5432/peak"
        env["POSTGRES_BACKUP_DIR"] = "/data/postgres_backups"
        self.assertEqual({issue["code"] for issue in inspect_environment(env)}, {"offsite_backup_not_configured"})

    def test_relative_postgres_backup_directory_warns_and_bad_retention_fails(self):
        env = self.valid_environment()
        env["DATABASE_URL"] = "postgresql://user:password@db.example.com:5432/peak"
        env["POSTGRES_BACKUP_DIR"] = "postgres_backups"
        env["POSTGRES_BACKUP_RETENTION"] = "0"
        codes = {issue["code"] for issue in inspect_environment(env)}
        self.assertIn("postgres_backup_dir_not_absolute", codes)
        self.assertIn("postgres_backup_retention_invalid", codes)

    def test_warns_when_offsite_backup_is_not_configured(self):
        env = self.valid_environment()
        issues = inspect_environment(env)
        warning = next(issue for issue in issues if issue["code"] == "offsite_backup_not_configured")
        self.assertEqual(warning["severity"], "warning")
        self.assertIn("off-site", warning["message"])

    def test_configured_offsite_storage_requires_restore_rehearsal(self):
        env = self.valid_environment()
        env["OFFSITE_BACKUP_BUCKET"] = "peak-backups"
        env["OFFSITE_BACKUP_REGION"] = "ap-south-1"
        issues = inspect_environment(env)
        self.assertNotIn("offsite_backup_not_configured", {issue["code"] for issue in issues})
        warning = next(issue for issue in issues if issue["code"] == "offsite_restore_rehearsal_required")
        self.assertEqual(warning["severity"], "warning")

    def test_invalid_offsite_bucket_is_an_error(self):
        env = self.valid_environment()
        env["OFFSITE_BACKUP_BUCKET"] = "Bad_Bucket"
        codes = {issue["code"] for issue in inspect_environment(env)}
        self.assertIn("offsite_backup_bucket_invalid", codes)

    def test_invalid_offsite_endpoint_is_an_error(self):
        env = self.valid_environment()
        env["OFFSITE_BACKUP_BUCKET"] = "peak-backups"
        env["OFFSITE_BACKUP_ENDPOINT_URL"] = "ftp://example.com"
        codes = {issue["code"] for issue in inspect_environment(env)}
        self.assertIn("offsite_backup_endpoint_invalid", codes)

    def test_warns_when_telegram_stars_are_enabled(self):
        env = self.valid_environment()
        env["ENABLE_TELEGRAM_STARS"] = "true"
        issues = inspect_environment(env)
        self.assertIn("telegram_stars_enabled", {issue["code"] for issue in issues})


if __name__ == "__main__":
    unittest.main()
