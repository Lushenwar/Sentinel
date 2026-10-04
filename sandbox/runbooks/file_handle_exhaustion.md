# Runbook: Disk Space and File Handle Exhaustion

**ID:** rb_disk_01  
**Severity:** High  
**Tags:** disk, file-descriptors, enospc, emfile

## Symptoms

- Log lines containing `OSError: [Errno 24] Too many open files`, `[Errno 28] No space left on device`, `ENOSPC`, or `EMFILE`
- Writes, uploads, or log output failing while reads still work
- Error rate rising steadily with uptime and clearing after a restart

## Root Causes

1. **Unclosed handles**: files, sockets, or subprocess pipes opened without a context manager or close
2. **Unbounded temp or log files**: files written per request and never cleaned up
3. **Missing rotation**: log rotation disabled or misconfigured
4. **Low ulimit**: file descriptor limit lowered in the runtime environment

## Immediate Actions

1. Check free disk space (`df -h`) and open descriptors (`ls /proc/<pid>/fd | wc -l`)
2. Identify what is holding handles or space (`lsof -p <pid>`, `du -sh` on temp and log directories)
3. Review recent changes that open files, sockets, or temp files
4. Restart the process to release handles, then clean up temp space

## Escalation

If the volume is shared with a database, escalate immediately to avoid data corruption.
