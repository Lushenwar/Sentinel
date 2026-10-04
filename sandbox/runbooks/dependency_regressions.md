# Runbook: Dependency Version Regressions

**ID:** rb_deps_01  
**Severity:** High  
**Tags:** dependencies, upgrade, importerror, compatibility

## Symptoms

- Errors immediately after a deploy that only changed lockfiles or requirements
- Log lines containing `ImportError`, `ModuleNotFoundError`, `AttributeError: module ... has no attribute`, or `unexpected keyword argument`
- Behaviour changes (serialization, defaults, timezone handling) without application code changes

## Root Causes

1. **Breaking change in a major or minor upgrade**: removed or renamed API
2. **Unpinned transitive dependency**: an indirect package moved to a new version
3. **Changed default behaviour**: a library changed a default value between versions
4. **Environment drift**: build image or runtime version differs from what was tested

## Immediate Actions

1. Diff the resolved dependency set against the last good deploy
2. Read the changelog of every package that changed version
3. Pin the previous version and redeploy if the cause is not immediately clear
4. Add the affected call to a test that runs against the pinned versions

## Escalation

If a security patch forced the upgrade, coordinate with the security team before rolling back.
