import os, json
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
                CREATE TABLE IF NOT EXISTS app_logs (
                    id          SERIAL PRIMARY KEY,
                    incident_id TEXT REFERENCES incidents(id),
                    ts          TIMESTAMPTZ DEFAULT NOW(),
                    level       TEXT,
                    message     TEXT,
                    endpoint    TEXT,
                    raw         JSONB
                );
            """)
    conn.close()

def save_incident(incident: dict):
    conn = _conn()
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO incidents (id, status, trigger_data, diagnostics, postmortem)
                   VALUES (%s, %s, %s, %s, %s)
                   ON CONFLICT (id) DO UPDATE SET
                     status = EXCLUDED.status,
                     diagnostics = EXCLUDED.diagnostics,
                     updated_at = NOW()""",
                (
                    incident["incident_id"],
                    incident["status"],
                    json.dumps(incident["trigger"]),
                    json.dumps(incident.get("diagnostics")),
                    incident.get("postmortem_draft_url"),
                ),
            )
    conn.close()

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
                "UPDATE incidents SET diagnostics = %s, status = 'triaging', updated_at = NOW() WHERE id = %s",
                (json.dumps(diagnostics), incident_id),
            )
    conn.close()
