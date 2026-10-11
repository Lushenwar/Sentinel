"""Signs alerts for core's /alert (see core.main.signature_ok) when SENTINEL_ALERT_SECRET is set."""

import hashlib
import hmac
import json
import os

from dotenv import load_dotenv

load_dotenv()


def signed(alert: dict) -> tuple[bytes, dict]:
    """(body, headers) to POST. The signature covers these exact bytes, so send body as-is."""
    body = json.dumps(alert).encode()
    headers = {"Content-Type": "application/json"}
    secret = os.getenv("SENTINEL_ALERT_SECRET")
    if secret:
        headers["X-Sentinel-Signature"] = (
            "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        )
    return body, headers
