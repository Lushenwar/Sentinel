# Runbook: Pagination and Off-by-One Errors

**ID:** rb_paging_01  
**Severity:** Medium  
**Tags:** pagination, off-by-one, indexerror, data-correctness

## Symptoms

- `IndexError: list index out of range` or similar boundary errors on list endpoints
- Clients report duplicated or missing items between pages
- Errors concentrated on the last page, the first page, or empty result sets

## Root Causes

1. **Boundary arithmetic**: offset computed from 1-based page numbers as if 0-based, or vice versa
2. **Inclusive vs. exclusive ranges**: slice or range end treated inconsistently
3. **Unstable sort order**: paging over a query without a deterministic ORDER BY
4. **Empty-set handling**: code assumes at least one result

## Immediate Actions

1. Reproduce with a page size of 1 and with an empty result set
2. Review recent changes to offset, limit, cursor, and slicing logic
3. Confirm the query has a deterministic ordering key
4. Compare item counts across pages against a single unpaged query

## Escalation

If clients have already consumed incorrect data (e.g. exports, billing), notify the owning product team.
