import json
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()
DSN = os.environ["DATABASE_URL"]


# ponytail: new connection per call; add psycopg2.pool.ThreadedConnectionPool if throughput matters
def _conn():
    return psycopg2.connect(DSN)


def init_schema():
    conn = _conn()
    with conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS incidents (
                    id           TEXT PRIMARY KEY,
                    status       TEXT NOT NULL DEFAULT 'triggered',
                    trigger_data JSONB NOT NULL,
                    diagnostics  JSONB,
                    postmortem   TEXT,
                    created_at   TIMESTAMPTZ DEFAULT NOW(),
                    updated_at   TIMESTAMPTZ DEFAULT NOW()
                );
                -- dedup key. Rows created before this column existed stay NULL and never dedup.
                ALTER TABLE incidents ADD COLUMN IF NOT EXISTS signature TEXT;
                -- at most one open incident per error signature, across workers and restarts
                CREATE UNIQUE INDEX IF NOT EXISTS incidents_one_open_per_signature
                    ON incidents (signature) WHERE status IN ('triggered', 'triaging');
            """)
    conn.close()


_OPEN = "status IN ('triggered', 'triaging')"  # must match the partial index predicate


def open_incident(incident: dict, signature: str) -> tuple[str, bool]:
    """Insert the incident unless one is already open for this signature.
    Returns (incident_id, created); when not created, the id is the open incident's."""
    conn = _conn()
    try:
        for _ in range(3):  # the open incident can close between the conflict and the lookup
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        f"""INSERT INTO incidents (id, status, trigger_data, signature)
                            VALUES (%s, %s, %s, %s)
                            ON CONFLICT (signature) WHERE {_OPEN} DO NOTHING
                            RETURNING id""",
                        (
                            incident["incident_id"],
                            incident["status"],
                            json.dumps(incident["trigger"]),
                            signature,
                        ),
                    )
                    if cur.fetchone():
                        return incident["incident_id"], True
                    cur.execute(f"SELECT id FROM incidents WHERE signature = %s AND {_OPEN}", (signature,))
                    row = cur.fetchone()
                    if row:
                        return row[0], False
        raise RuntimeError(f"could not open or find an incident for signature {signature!r}")
    finally:
        conn.close()


def stuck_incidents(older_than_s: float) -> list[dict]:
    """Open incidents with no diagnostics whose last update is older than older_than_s:
    the process running their triage died."""
    conn = _conn()
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            f"""SELECT id, trigger_data FROM incidents
                WHERE {_OPEN} AND (diagnostics IS NULL OR diagnostics = 'null'::jsonb)
                  AND updated_at < NOW() - make_interval(secs => %s)
                ORDER BY created_at""",
            (older_than_s,),
        )
        rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_incident(incident_id: str) -> dict | None:
    conn = _conn()
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT * FROM incidents WHERE id = %s", (incident_id,))
        row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def list_incidents() -> list:
    conn = _conn()
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT * FROM incidents ORDER BY created_at DESC")
        rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_status(incident_id: str, status: str):
    conn = _conn()
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE incidents SET status = %s, updated_at = NOW() WHERE id = %s",
                (status, incident_id),
            )
    conn.close()


def update_diagnostics(incident_id: str, diagnostics: dict):
    conn = _conn()
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE incidents SET diagnostics = %s, status = 'triaging', updated_at = NOW() "
                "WHERE id = %s",
                (json.dumps(diagnostics), incident_id),
            )
    conn.close()


def update_postmortem(incident_id: str, postmortem: str):
    conn = _conn()
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE incidents SET postmortem = %s, status = 'resolved', updated_at = NOW() WHERE id = %s",
                (postmortem, incident_id),
            )
    conn.close()
