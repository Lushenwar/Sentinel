# Runbook: Configuration Type and Parse Errors

**ID:** rb_config_01  
**Severity:** Critical  
**Tags:** config, env, parsing, startup, types

## Symptoms

- Service fails on startup, or fails on the first request that reads a setting
- Log lines containing `ValueError: invalid literal for int()`, `TypeError: '<' not supported between instances of 'str' and 'int'`, `JSONDecodeError`, or `could not convert string to float`
- Errors appear immediately after a deploy or config change, across all instances at once

## Root Causes

1. **Wrong type**: a numeric or boolean setting provided as a string (environment variables are always strings)
2. **Malformed config file**: invalid JSON/YAML, trailing commas, wrong nesting
3. **Renamed or removed key**: code reads a key the config no longer contains, falling back to an unexpected default
4. **Unit mismatch**: seconds vs. milliseconds, bytes vs. megabytes

## Immediate Actions

1. Diff the effective configuration against the last known good deploy
2. Validate config files with a parser before redeploying
3. Check that every setting read from the environment is explicitly cast to its expected type
4. Roll back the config change if the correct value is not obvious

## Escalation

If secrets or credentials are part of the changed configuration, involve the platform team.
