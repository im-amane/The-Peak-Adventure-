import hashlib
import hmac
import json
import time
import unittest
from urllib.parse import urlencode

from telegram_auth import validate_init_data


class TelegramAuthTests(unittest.TestCase):
    token = "123456:test-token"

    def make_init_data(self, auth_date=None, user=None):
        fields = {
            "auth_date": str(auth_date or int(time.time())),
            "query_id": "AAExample",
            "user": json.dumps(user or {"id": 42, "first_name": "Tester"}, separators=(",", ":")),
        }
        check = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
        secret = hmac.new(b"WebAppData", self.token.encode(), hashlib.sha256).digest()
        fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
        return urlencode(fields)

    def test_valid_init_data_returns_user(self):
        user = validate_init_data(self.make_init_data(), self.token)
        self.assertEqual(user["id"], 42)

    def test_invalid_signature_is_rejected(self):
        data = self.make_init_data().replace("Tester", "Attacker")
        with self.assertRaises(ValueError):
            validate_init_data(data, self.token)

    def test_expired_init_data_is_rejected(self):
        stale = int(time.time()) - 90000
        with self.assertRaises(ValueError):
            validate_init_data(self.make_init_data(auth_date=stale), self.token)

    def test_duplicate_fields_are_rejected(self):
        data = self.make_init_data() + "&auth_date=1"
        with self.assertRaises(ValueError):
            validate_init_data(data, self.token)

    def test_oversized_init_data_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "too large"):
            validate_init_data("x" * 8193, self.token)

    def test_too_many_fields_are_rejected(self):
        data = self.make_init_data() + "".join(f"&extra{i}=x" for i in range(25))
        with self.assertRaisesRegex(ValueError, "Malformed"):
            validate_init_data(data, self.token)


if __name__ == "__main__":
    unittest.main()
