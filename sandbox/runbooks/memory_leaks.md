# Runbook: Application Memory Leak

**ID:** rb_mem_02  
**Severity:** High  
**Tags:** memory, oom, performance

## Symptoms

- Gradual increase in process RSS over time
- Eventually: `MemoryError` exceptions or OOM kill from the OS
- Response times degrading as GC pressure increases

## Root Causes

1. **Accumulating request buffers** — large objects allocated per-request and never freed
2. **Unbounded caches** — in-memory caches with no eviction policy
3. **Circular references** — Python GC not collecting cyclic object graphs

## Immediate Actions

1. Check process memory: `ps aux | grep python` or `top`
2. Restart the application process to reclaim memory immediately
3. Identify the offending commit: `git log --oneline -10 sandbox/app/`
4. Profile with `tracemalloc` or `memory-profiler` to find the allocation site

## Escalation

If restart doesn't stabilize memory within 10 minutes, check for external I/O accumulation (temp files, unclosed file handles).
