# ponytail: /alert signature check end to end with the sandbox's signer; orchestrator mocked
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from core import main
from sandbox import alert_signing

_ALERT = {"source": "t", "alert_name": "a", "timestamp": "2026-09-01T12:00:00Z", "error_signature": "E"}


@pytest.fixture
def client():
    with (
        patch.object(
            main.orchestrator, "handle_alert", return_value={"incident_id": "inc_1", "status": "triggered"}
        ),
        patch.object(main.orchestrator, "run_diagnostics") as run,
    ):
        yield TestClient(main.app), run  # no `with`: skips lifespan (db, chroma)


def _post(client, body: bytes, headers: dict | None = None):
    return client.post(
        "/alert", content=body, headers={"Content-Type": "application/json", **(headers or {})}
    )


def test_secret_set_requires_valid_signature(client, monkeypatch):
    c, run = client
    monkeypatch.setattr(main, "_ALERT_SECRET", "s3cret")
    monkeypatch.setenv("SENTINEL_ALERT_SECRET", "s3cret")
    body, headers = alert_signing.signed(_ALERT)

    assert _post(c, body).status_code == 401
    assert _post(c, body, {"X-Sentinel-Signature": "sha256=" + "0" * 64}).status_code == 401
    assert _post(c, body + b" ", headers).status_code == 401  # signature covers the exact bytes
    run.assert_not_called()

    r = _post(c, body, headers)
    assert r.status_code == 200 and r.json()["incident_id"] == "inc_1"
    run.assert_called_once_with("inc_1", _ALERT)


def test_wrong_secret_is_rejected(client, monkeypatch):
    c, _ = client
    monkeypatch.setattr(main, "_ALERT_SECRET", "server-secret")
    monkeypatch.setenv("SENTINEL_ALERT_SECRET", "sender-secret")
    body, headers = alert_signing.signed(_ALERT)
    assert _post(c, body, headers).status_code == 401


def test_secret_unset_accepts_unsigned(client, monkeypatch):
    c, _ = client
    monkeypatch.setattr(main, "_ALERT_SECRET", "")
    assert _post(c, b'{"error_signature": "E", "timestamp": "2026-09-01T12:00:00Z"}').status_code == 200


@pytest.mark.parametrize("body", [b"not json", b"[1, 2]"])
def test_body_must_be_a_json_object(client, monkeypatch, body):
    c, run = client
    monkeypatch.setattr(main, "_ALERT_SECRET", "")
    assert _post(c, body).status_code == 400
    run.assert_not_called()
