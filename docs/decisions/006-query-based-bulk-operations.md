---
id: 006
title: Query-Based Bulk Operations
status: accepted
date: 2026-02-10
supersedes: []
superseded_by: null
tags: [cli, gmail, batch, agents, performance]
---

# ADR-006: Query-Based Bulk Operations

## Context

Desk's batch operations (Idea 002) allow agents to operate on multiple messages by passing IDs as arguments or via `--stdin`. This works well for small batches but breaks down at scale.

A real-world scenario exposed the problem: an agent needed to mark-read and archive ~15,000 messages matching `label:Github is:unread`. The workflow required:

1. Search page 1 (200 results) → extract IDs → pipe to `desk mail mark-read --stdin`
2. Get next page token → search page 2 → pipe to mark-read
3. Repeat ~75 times (200 messages per page × 75 pages = 15,000 messages)

Each iteration requires the agent to orchestrate pagination, manage page tokens, and handle errors—work the CLI should do internally. Gmail's `batchModify` API accepts up to 1,000 IDs per call, so 15,000 messages should be ~15 API calls, not 75+ agent round-trips.

A secondary problem: deleting a Gmail label attached to 15,000+ messages causes the Gmail API to timeout with `OPERATION_FAILED`. The API attempts to remove the label from all messages atomically, which exceeds server-side timeouts.

## Decision

### 1. Add `--query` flag to all bulk operation commands

All commands that currently accept message IDs will also accept a `--query` flag:

```bash
desk mail mark-read --query 'label:Github is:unread' --yes
desk mail archive --query 'label:Github' --yes
desk mail label Important --query 'from:ceo@company.com' --yes
desk mail trash --query 'older_than:1y label:Promotions' --yes
```

When `--query` is provided:
- The CLI internally paginates through all matching messages
- Calls `batchModify` in chunks of up to 1,000 IDs per API call
- Requires `--yes` flag to execute (safety gate for potentially large operations)
- Without `--yes`: returns the match count and exits with an error suggesting `--yes`

### 2. Confirmation via `--yes`, not interactive prompts

Consistent with Idea 013 (Safety Confirmations) and ADR-004 (Agent-First CLI):
- No interactive prompts — agents can't answer them
- `--yes` is the explicit confirmation flag
- Without `--yes`, the command reports the count and fails with a clear error
- Non-interactive environments (pipes) require `--yes` or fail

### 3. Progress and receipts via `--json`

With `--json`, emit a receipt per batch chunk for programmatic progress tracking:

```json
{"batch": 1, "processed": 1000, "total_so_far": 1000, "failed": 0}
{"batch": 2, "processed": 1000, "total_so_far": 2000, "failed": 0}
...
{"complete": true, "total_processed": 15234, "total_failed": 0, "elapsed_ms": 42000}
```

Without `--json`, human-readable output shows a final summary only.

### 4. `--dry-run` shows count and preview

```bash
desk mail mark-read --query 'label:Github is:unread' --dry-run
```

Returns the count of matching messages and a preview of the first few, without executing anything.

### 5. Smart label deletion

`desk mail delete-label` will detect large labels and handle them in two steps:
1. Batch-remove the label from all messages (in chunks of 1,000)
2. Delete the now-empty label

This avoids the Gmail API timeout on atomic label deletion. Requires `--yes` for labels with messages attached.

## Alternatives Considered

### Alternative 1: External pagination orchestration

**Description**: Leave pagination to the calling agent. Provide documentation and examples for the search → pipe → next-page loop.

**Pros**:
- No CLI changes needed
- Agents can customize batch size and error handling

**Cons**:
- 75+ agent round-trips vs. 15 API calls — massive overhead
- Every agent must reimplement the same pagination loop
- Error recovery is fragile — lost page tokens, partial progress
- Violates the "CLI handles complexity" principle

**Why rejected**: The CLI has all the building blocks. Making agents reimagine pagination is unnecessary work.

### Alternative 2: `--all` flag instead of `--yes`

**Description**: Use `--all` to mean "process all matching messages" rather than `--yes`.

**Pros**:
- More semantically descriptive ("process all")

**Cons**:
- Inconsistent with established `--yes` pattern from Idea 013
- `--all` could be confused with "all messages" rather than "all matching"
- Two confirmation patterns (`--yes` for destructive, `--all` for bulk) adds cognitive load

**Why rejected**: `--yes` already means "I confirm this potentially large operation." Adding a second confirmation flag creates inconsistency.

### Alternative 3: Separate `bulk` subcommand

**Description**: `desk mail bulk mark-read --query '...'` as a separate command group.

**Pros**:
- Clear separation between single-message and bulk operations
- Easier to discover via `desk mail bulk --help`

**Cons**:
- Doubles the number of commands to maintain
- Agents must choose between two command paths
- The existing commands already handle multiple IDs

**Why rejected**: The commands already support batch via multiple IDs and `--stdin`. Adding `--query` is a natural extension, not a new paradigm.

## Consequences

### Positive

- 15,000-message operations go from 75+ agent round-trips to 1 CLI invocation with ~15 API calls
- Consistent with existing patterns (`--yes`, `--dry-run`, `--json`)
- Label deletion works reliably at scale
- Agents write less orchestration code

### Negative

- Commands become more complex internally (pagination loop, chunking, progress tracking)
  - *Mitigation*: Shared `_query_bulk_operate()` helper handles all the complexity once
- `--query` + `--yes` is required even for small result sets
  - *Mitigation*: Without `--yes`, the count is shown — agents can decide whether to proceed
- Long-running operations may timeout in some agent frameworks
  - *Mitigation*: Per-batch `--json` output allows frameworks to detect activity

### Neutral

- `--query` and positional message IDs are mutually exclusive — attempting both is an error
- Search query syntax is Gmail's native syntax, not invented vocabulary (per ADR-002)

## Implementation Notes

**Key files**:
- `src/desk/commands/mail.py` — Add `--query` and `--yes` to bulk commands, shared helper
- `src/desk/services/gmail.py` — Add `search_all_ids()` method for full pagination
- `docs/ideas/002-batch-operations.md` — Update status to note query-based extension

**Gmail API constraints**:
- `batchModify` accepts max 1,000 IDs per call
- `messages.list` returns max 500 per page (configurable via `maxResults`)
- Rate limits: ~250 quota units/second for batch operations

**Affected commands**: `archive`, `trash`, `mark-read`, `mark-unread`, `star`, `unstar`, `label`, `remove-label`, `modify`, `spam`, `not-spam`, `important`, `not-important`

## References

- [Idea 002: Batch Operations](../ideas/002-batch-operations.md)
- [Idea 013: Safety Confirmations](../ideas/013-safety-confirmations.md)
- [ADR-004: Agent-First CLI Design](004-agent-first-cli.md)
- [Gmail batchModify API](https://developers.google.com/gmail/api/reference/rest/v1/users.messages/batchModify)
