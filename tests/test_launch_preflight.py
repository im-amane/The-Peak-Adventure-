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

    def test_valid_controlled_prototype_configuration_passes(self):
        self.assertEqual(inspect_environment(self.valid_environment()), [])

    def test_missing_secrets_and_webapp_url_are_errors_without_echoing_values(self):
        issues = inspect_environment({})
        codes = {issue["code"] for issue in issues}
        self.assertIn("bot_token_missing", codes)
        self.assertIn("webapp_url_missing", codes)
        self.assertNotIn("BOT_TOKEN", str(issues))

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
        self.assertEqual(inspect_environment(env), [])

    def test_invalid_port_and_backup_settings_are_errors(self):
        env = self.valid_environment()
        env["PORT"] = "70000"
        env["BACKUP_INTERVAL_SECONDS"] = "60"
        env["BACKUP_RETENTION"] = "0"
        codes = {issue["code"] for issue in inspect_environment(env)}
        self.assertIn("web_port_invalid", codes)
        self.assertIn("backup_interval_invalid", codes)
        self.assertIn("backup_retention_invalid", codes)

    def test_warns_when_telegram_stars_are_enabled(self):
        env = self.valid_environment()
        env["ENABLE_TELEGRAM_STARS"] = "true"
        issues = inspect_environment(env)
        self.assertIn("telegram_stars_enabled", {issue["code"] for issue in issues})


if __name__ == "__main__":
    unittest.main()
