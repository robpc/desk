---
id: 029
title: Structured Errors with Suggestions
status: planned
effort: M
value: Agents can recover from errors without human intervention
created: 2025-02-07
updated: 2025-02-07
adr: 004-agent-first-cli.md
---

# Idea 029: Structured Errors with Suggestions

## Problem

Current errors are human-readable strings:
```
Error: Message not found
```

An agent seeing this doesn't know:
- What exactly failed (which message?)
- Why it failed (deleted? wrong account? typo?)
- What to do next (search again? check trash?)
- Whether retrying might work

## Sketch

All errors return structured JSON with actionable suggestions:

```json
{
  "success": false,
  "error": {
    "code": "MESSAGE_NOT_FOUND",
    "message": "Message with ID abc123 not found",
    "details": {
      "requested_id": "abc123",
      "account": "user@gmail.com"
    },
    "suggestions": [
      "Run `desk mail search` to find valid message IDs",
      "The message may have been deleted",
      "Check `desk mail search in:trash` if recently deleted"
    ],
    "retryable": false,
    "docs_url": null
  }
}
```

### Error Code Catalog

| Code | When | Suggestions |
|------|------|-------------|
| `MESSAGE_NOT_FOUND` | Invalid message ID | Search for valid IDs, check trash |
| `LABEL_NOT_FOUND` | Invalid label name | List labels, check spelling |
| `FILE_NOT_FOUND` | Invalid Drive file ID | Search Drive, check permissions |
| `PERMISSION_DENIED` | No access | Request access, check sharing |
| `RATE_LIMITED` | Too many requests | Wait and retry |
| `INVALID_QUERY` | Bad search syntax | Check query format, escape special chars |
| `AUTH_EXPIRED` | Token needs refresh | Run `desk auth login` |

### Human-Readable Mode

When not using `--json`, errors still show as readable text but with suggestions:

```
Error: Message not found (MESSAGE_NOT_FOUND)

The message with ID abc123 was not found.

Suggestions:
  • Run `desk mail search` to find valid message IDs
  • The message may have been deleted
  • Check `desk mail search in:trash` if recently deleted
```

## Open Questions

- [ ] Should suggestions be commands only, or also prose explanations?
- [ ] How many suggestions is too many? (Cap at 3?)
- [ ] Should we include confidence levels on suggestions?

## Value Signal

This is the core of agent-first design. An agent that can self-recover from errors is dramatically more useful than one that fails and waits for human help.

## Effort Guess

M - Need to audit all error paths, create error catalog, update exception handling throughout. The framework (Idea 028) does the heavy lifting; this is about applying it comprehensively.

## Notes

Depends on: Idea 028 (Agent-First Framework)

Related: ADR-004
