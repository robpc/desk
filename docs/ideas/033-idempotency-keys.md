---
id: 033
title: Idempotency Keys for Critical Operations
status: planned
effort: S
value: Agents can safely retry without duplicate sends
created: 2025-02-07
updated: 2025-02-07
adr: 004-agent-first-cli.md
---

# Idea 033: Idempotency Keys for Critical Operations

## Problem

Agents sometimes don't know if an operation succeeded. Network timeout, process killed, unclear output — the agent isn't sure if the email was sent. The safe choice is to retry, but retrying `send` could send duplicate emails.

This is especially bad for:
- `desk mail send` — duplicate emails are embarrassing
- `desk cal create` — duplicate calendar events confuse everyone
- Any operation where "doing it twice" has visible consequences

## Sketch

Add `--idempotency-key` to critical operations:

```bash
desk mail send --to "bob@x.com" --subject "Update" --body "..." \
  --idempotency-key "agent-task-abc123"
```

Behavior:
1. First call: executes normally, stores key → result mapping
2. Second call with same key: returns cached result, does NOT re-execute

```json
{
  "success": true,
  "operation": "send",
  "idempotency": {
    "key": "agent-task-abc123",
    "status": "executed",  // or "cached" on replay
    "original_timestamp": "2025-02-07T10:30:00Z"
  },
  "result": {
    "message_id": "sent123",
    "thread_id": "thread456"
  }
}
```

On replay:
```json
{
  "success": true,
  "operation": "send",
  "idempotency": {
    "key": "agent-task-abc123",
    "status": "cached",
    "original_timestamp": "2025-02-07T10:30:00Z",
    "note": "Operation was already executed; returning cached result"
  },
  "result": {
    "message_id": "sent123",
    "thread_id": "thread456"
  }
}
```

### Storage

Store idempotency records in `~/.desk/idempotency.json`:

```json
{
  "agent-task-abc123": {
    "operation": "mail.send",
    "timestamp": "2025-02-07T10:30:00Z",
    "expires": "2025-02-14T10:30:00Z",
    "result": { ... }
  }
}
```

Keys expire after 7 days (configurable).

### Commands That Need This

| Command | Why |
|---------|-----|
| `desk mail send` | Duplicate emails |
| `desk mail reply` | Duplicate replies |
| `desk mail forward` | Duplicate forwards |
| `desk cal create` | Duplicate events |
| `desk drive upload` | Duplicate files (less critical but still messy) |

## Open Questions

- [ ] How long should keys be valid? (7 days default?)
- [ ] Max storage size for idempotency cache? (Rotate old entries?)
- [ ] Should the key be auto-generated if not provided? (Hash of arguments?)
- [ ] What if the cached result was an error — replay the error or retry?

## Value Signal

This is table stakes for reliable agent automation. Stripe, AWS, and every serious API has idempotency keys for exactly this reason. Without them, agents have to be overly cautious about retries.

## Effort Guess

S - Simple key-value storage, check-before-execute pattern. The main work is deciding which commands get it and handling edge cases (what if args change but key is same?).

## Notes

Depends on: Idea 028 (Agent-First Framework) — for consistent response formatting

Design principle: Idempotency is opt-in. If an agent doesn't provide a key, operations work as before (no caching). This avoids breaking existing workflows.

Related: ADR-004
