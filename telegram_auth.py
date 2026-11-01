"""Telegram Mini App initData validation."""
import hashlib
import hmac
import json
import re
import time
from urllib.parse import parse_qsl


def validate_init_data(init_data: str, bot_token: str, max_age: int = 86400) -> dict:
    if not init_data or not bot_token:
        raise ValueError("Missing Telegram initData or bot token")
    pairs = parse_qsl(init_data, keep_blank_values=True, strict_parsing=True)
    data = {}
    for key, value in pairs:
        if key in data:
            raise ValueError("Duplicate initData field")
        data[key] = value
    received_hash = data.pop("hash", None)
    if not received_hash:
        raise ValueError("Missing initData hash")
    if not re.fullmatch(r"[0-9a-f]{64}", received_hash):
        raise ValueError("Malformed Telegram initData hash")
    check_string = "\n".join(f"{key}={value}" for key, value in sorted(data.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    calculated_hash = hmac.new(secret_key, check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calculated_hash, received_hash):
        raise ValueError("Invalid Telegram initData signature")
    try:
        auth_date = int(data["auth_date"])
        user = json.loads(data["user"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid Telegram initData payload") from exc
    now = int(time.time())
    if auth_date > now + 60 or now - auth_date > max_age:
        raise ValueError("Telegram initData has expired")
    if not isinstance(user, dict) or not isinstance(user.get("id"), int):
        raise ValueError("Telegram initData has no valid user")
    return user
