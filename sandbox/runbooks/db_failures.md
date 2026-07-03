# Runbook: Database Connection Pool Exhaustion

**ID:** rb_db_04  
**Severity:** Critical  
**Tags:** postgres, connection-pool, 5xx

## Symptoms

- HTTP 500 errors on all endpoints that touch the database
- Log lines containing `OperationalError: connection to server` or `Connection refused`
- Sudden spike in response latency followed by total failure

## Root Causes

1. **Pool size misconfigured** — `max_connections` set to a string instead of integer
2. **Connection leak** — requests acquiring connections without releasing them
3. **Database process crashed** — postgres process down or OOM-killed
4. **Network partition** — app cannot reach DB host

## Immediate Actions

1. Check database process: `pg_isready -h $DB_HOST -p $DB_PORT`
2. Inspect pool config: verify `MAX_POOL_SIZE` env var is an integer
3. Restart the application to flush leaked connections
4. Check `pg_stat_activity` for connections stuck in idle-in-transaction state

## Escalation

If database is unreachable for > 5 minutes, escalate to on-call DBA.
