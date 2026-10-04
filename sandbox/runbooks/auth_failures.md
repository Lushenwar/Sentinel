# Runbook: Authentication and Credential Failures

**ID:** rb_auth_01  
**Severity:** Critical  
**Tags:** auth, 401, 403, credentials, tokens

## Symptoms

- Spike in HTTP 401 Unauthorized or 403 Forbidden responses
- Log lines containing `InvalidSignatureError`, `ExpiredSignatureError`, `invalid_grant`, `authentication failed`, or `permission denied`
- Calls to a third-party API rejected while the provider's status page is green

## Root Causes

1. **Expired or rotated credential**: an API key, certificate, or secret rotated without updating consumers
2. **Clock skew**: token validation failing on `iat`/`exp` checks because of drift between hosts
3. **Wrong key or audience**: signing key, issuer, or audience changed in config or code
4. **Scope or permission change**: a role lost a permission the service relies on

## Immediate Actions

1. Determine whether rejections are inbound (our users rejected) or outbound (we are rejected by a dependency)
2. Check credential expiry dates and recent rotations
3. Compare token validation settings (algorithm, issuer, audience, leeway) against the last good deploy
4. Verify host clocks are synchronized

## Escalation

Treat any unexplained auth change as a potential security event and notify the security on-call.
