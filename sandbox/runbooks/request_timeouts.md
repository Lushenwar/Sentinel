# Runbook: Request Timeouts and Upstream Latency

**ID:** rb_timeout_01  
**Severity:** High  
**Tags:** latency, timeout, 504, upstream

## Symptoms

- HTTP 504 Gateway Timeout or 503 responses from the edge or load balancer
- Log lines containing `ReadTimeout`, `TimeoutError`, `timed out`, or `deadline exceeded`
- p95/p99 latency climbing on one endpoint while others stay normal
- Worker or thread pool saturation as requests wait on slow calls

## Root Causes

1. **Timeout budget mismatch**: a client-side timeout shorter than the upstream's normal response time, or an inner timeout longer than the outer one
2. **Slow dependency**: a downstream service or query whose latency has regressed
3. **Retry amplification**: retries without backoff multiplying load on an already slow upstream
4. **Blocking call on a hot path**: synchronous I/O added to a request handler

## Immediate Actions

1. Identify which hop is slow: compare latency at the edge, the app, and each dependency
2. Review timeout and retry settings across the call chain; inner timeouts must be shorter than outer ones
3. Check recent changes to timeout constants, retry policies, and client configuration
4. Shed load or raise the outer timeout temporarily if a dependency is healthy but slow

## Escalation

If a shared dependency is slow for more than 15 minutes, page the owning team.
