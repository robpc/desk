---
id: 028
title: Agent-First Framework
status: implemented
effort: M
value: Foundation for all agent-first features - decorators and utilities
created: 2025-02-07
updated: 2025-02-07
adr: 004-agent-first-cli.md
---

# Idea 028: Agent-First Framework

## Problem

ADR-004 defines several agent-first features (structured errors, receipts, dry-run enhancements, etc.). Without a shared framework, each command will implement these inconsistently.

## Sketch

Create `src/desk/agent.py` with reusable utilities:

```python
# Decorators
@with_receipt          # Wraps mutating commands to return operation receipts
@with_structured_error # Catches exceptions and formats as structured JSON
@batch_enabled         # Adds --stdin support and multiple ID handling

# Utilities
def structured_error(code, message, suggestions, retryable=False) -> dict
def operation_receipt(operation, target, undo_command=None, undo_expires=None) -> dict
def dry_run_preview(operation, targets, reversible=True) -> dict

# Error codes (enum)
class ErrorCode(str, Enum):
    MESSAGE_NOT_FOUND = "MESSAGE_NOT_FOUND"
    LABEL_NOT_FOUND = "LABEL_NOT_FOUND"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    RATE_LIMITED = "RATE_LIMITED"
    # etc.
```

## Open Questions

- [ ] Should decorators be composable? (e.g., `@with_receipt @with_structured_error`)
- [ ] How to handle non-JSON output mode? (Human-readable should still work)
- [ ] Should there be a global `--agent` flag that enables all agent-first behaviors?

## Value Signal

This is the foundation for ADR-004. All other agent-first features depend on having consistent patterns.

## Effort Guess

M - Need to design the API carefully, but implementation is straightforward. The challenge is getting the abstraction right so it works across all command types.

## Notes

This should be implemented first, before the other agent-first ideas. Other ideas (029-032) depend on this framework.

Related: ADR-004, Ideas 029-032
