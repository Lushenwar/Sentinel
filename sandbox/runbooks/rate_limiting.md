# Runbook: Rate Limiting and HTTP 429

**ID:** rb_ratelimit_01  
**Severity:** Medium  
**Tags:** 429, rate-limit, throttling, quota

## Symptoms

- HTTP 429 Too Many Requests, either returned to our clients or received from a dependency
- Log lines containing `429`, `Too Many Requests`, `rate limit exceeded`, `quota exceeded`, or `Retry-After`
- Rejections arrive in bursts and recover on a fixed interval

## Root Causes

1. **Request volume increase**: a change that calls a dependency more often, e.g. per item inside a loop instead of per batch
2. **Lost caching**: a cache bypassed, disabled, or given a much shorter TTL
3. **Aggressive retries**: retrying 429s immediately instead of honouring `Retry-After`
4. **Lowered limit**: a quota or limiter threshold changed in config

## Immediate Actions

1. Determine whether we are being limited or doing the limiting
2. Compare outbound request rate per dependency before and after the start of the incident
3. Check recent changes to caching, batching, retry policies, and limiter settings
4. Back off or reduce concurrency on the affected client

## Escalation

If a vendor quota must be raised, contact the account owner for that vendor.
