# Runbook: Null or Missing Field Errors

**ID:** rb_null_01  
**Severity:** High  
**Tags:** null, none, keyerror, validation, 500

## Symptoms

- HTTP 500 errors on a subset of requests, often tied to particular records or users
- Log lines containing `'NoneType' object has no attribute`, `KeyError`, `TypeError: 'NoneType' object is not subscriptable`, or `Cannot read properties of undefined`
- Error rate correlates with specific input shapes rather than with overall traffic

## Root Causes

1. **Optional field treated as required**: code accesses a field that some records or payloads omit
2. **Schema change without backfill**: a new column or key exists for new rows but is null for older ones
3. **Changed default**: a lookup or helper that used to return an empty value now returns `None`
4. **Upstream contract change**: a dependency stopped sending a field

## Immediate Actions

1. Capture a failing payload or record ID from the traceback and inspect which field is missing
2. Check recent changes to data models, serializers, and helper return values
3. Add a guarded default at the access site if a rollback is not possible
4. Query for how many records lack the field to size the impact

## Escalation

If corrupted or partially written records are involved, involve the data owner before backfilling.
