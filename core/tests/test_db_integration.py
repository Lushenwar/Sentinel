# Runs the dedup/recovery SQL against a real Postgres. Opt-in, because DATABASE_URL in a dev .env is
# usually the shared Neon database: CI sets SENTINEL_DB_TESTS=1 with a throwaway Postgres service.
import os
import uuid

import pytest

pytestmark = pytest.mark.skipif(os.getenv("SENTINEL_DB_TESTS") != "1", reason="needs SENTINEL_DB_TESTS=1")

from core import db  # noqa: E402


def _inc():
    return {"incident_id": f"inc_test_{uuid.uuid4().hex[:8]}", "status": "triggered", "trigger": {"x": 1}}


@pytest.fixture(scope="module", autouse=True)
def schema():
    db.init_schema()
    db.init_schema()  # idempotent


def test_one_open_incident_per_signature():
    sig = f"sig-{uuid.uuid4().hex}"
    first, second, other = _inc(), _inc(), _inc()
    assert db.open_incident(first, sig) == (first["incident_id"], True)
    assert db.open_incident(second, sig) == (first["incident_id"], False)
    assert db.get_incident(second["incident_id"]) is None
    assert db.open_incident(other, sig + "-other")[1] is True

    db.update_status(first["incident_id"], "degraded")  # terminal: leaves the open set
    assert db.open_incident(second, sig) == (second["incident_id"], True)


def test_triaged_incident_is_still_open():
    sig = f"sig-{uuid.uuid4().hex}"
    first = _inc()
    db.open_incident(first, sig)
    db.update_diagnostics(first["incident_id"], {"suspect_commits": []})  # status triaging, awaiting resolve
    assert db.open_incident(_inc(), sig) == (first["incident_id"], False)
    db.update_postmortem(first["incident_id"], "# pm")  # resolved
    assert db.open_incident(_inc(), sig)[1] is True


def test_stuck_means_open_without_diagnostics_and_old():
    old, fresh, done = _inc(), _inc(), _inc()
    for inc in (old, fresh, done):
        db.open_incident(inc, f"sig-{uuid.uuid4().hex}")
    db.update_diagnostics(done["incident_id"], {"suspect_commits": []})
    conn = db._conn()
    with conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE incidents SET updated_at = NOW() - INTERVAL '1 hour' WHERE id IN (%s, %s)",
            (old["incident_id"], done["incident_id"]),
        )
    conn.close()
    stuck = {r["id"] for r in db.stuck_incidents(300)}
    assert old["incident_id"] in stuck
    assert fresh["incident_id"] not in stuck and done["incident_id"] not in stuck
    assert next(r for r in db.stuck_incidents(300) if r["id"] == old["incident_id"])["trigger_data"] == {
        "x": 1
    }
