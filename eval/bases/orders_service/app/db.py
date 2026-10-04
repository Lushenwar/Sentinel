import psycopg2.pool

from app import settings

_pool = None


def get_pool():
    global _pool
    if _pool is None:
        _pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=1,
            maxconn=settings.get("db", "pool_size"),
            host=settings.get("db", "host"),
            port=settings.get("db", "port"),
            dbname=settings.get("db", "name"),
            connect_timeout=settings.get("db", "connect_timeout_s"),
        )
    return _pool


def fetch_all(sql: str, params: tuple = ()) -> list:
    pool = get_pool()
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()
    finally:
        pool.putconn(conn)


def fetch_one(sql: str, params: tuple = ()):
    rows = fetch_all(sql, params)
    return rows[0] if rows else None
