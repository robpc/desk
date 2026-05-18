---
id: "021"
title: Chunked HTTP Batch Fan-Out for Gmail Read Paths
status: accepted
date: 2026-05-18
supersedes: []
superseded_by: null
tags: [gmail, performance, batch, agent-first]
---

# ADR-021: Chunked HTTP Batch Fan-Out for Gmail Read Paths

## Context

`GmailClient._batch_get()` in `src/desk/services/gmail.py` constructs a single
Gmail HTTP batch request via `service.new_batch_http_request()` and adds one
inner `.get()` per message ID. The Gmail API rejects any HTTP batch with more
than 100 inner requests:

```
HttpError 400 ... "Inner request count exceeds the limit. Received: 500, Limit: 100"
```

This means `desk mail search --max 500` hard-fails. Anything > 100 hits the
same wall. The user-visible symptom is an unstructured Python traceback,
violating the agent-friendly contract of [ADR-004](004-agent-first-cli.md) and
the stream discipline of [ADR-019](019-errors-to-stderr.md).

Hit in real usage 2026-05-16 during a bulk inbox survey
(see [Idea 050](../ideas/050-chunk-gmail-batch-get.md)).

### Why this is distinct from ADR-006

[ADR-006](006-query-based-bulk-operations.md) already chunks **`batchModify`**
calls at 1,000 IDs per request for bulk-mutation commands (archive/trash/
mark-read/etc.) when invoked via `--query`. That chunking lives in the
command layer (`mail.py:_BATCH_MODIFY_CHUNK = 1000`) and addresses Gmail's
`batchModify` API limit.

The `batchModify` endpoint and HTTP batch are **different mechanisms with
different limits**:

| Mechanism | Limit | Used by | Chunking lives |
|---|---|---|---|
| `users.messages.batchModify` | 1,000 IDs/call | Bulk mutations (archive, trash, label, ...) | Command layer (ADR-006) |
| `new_batch_http_request` (HTTP batch) | 100 inner requests | Fan-out reads (search, threads, drafts) | **This ADR** |

ADR-006 is unaffected; we are filling a separate gap.

## Decision

`_batch_get` will chunk its inputs into sequential batches of ≤100 inner
requests. Successes from chunks that complete are returned; the helper does
not abort the overall call when an individual chunk fails.

Concretely:

1. **Add module-level constant** `_HTTP_BATCH_MAX = 100` in
   `src/desk/services/gmail.py`, with a comment pointing at the Gmail API
   documented limit.
2. **Split** the request list into consecutive slices of size
   `_HTTP_BATCH_MAX`. For each chunk, build a fresh
   `new_batch_http_request(callback=...)`, add every request, and call
   `.execute()`.
3. **Sequential** execution. Parallel execution (e.g. via
   `concurrent.futures`) is an open question deferred to a follow-up idea —
   sequential covers the bug, parallel needs benchmarking against Gmail's
   per-user rate limit.
4. **Per-request failures inside a chunk** continue to be silently omitted
   from the returned dict, preserving the existing contract.
5. **Whole-chunk failures** (e.g. `execute()` raises) do **not** abort the
   call. The failure is recorded against every request_id in that chunk, and
   the helper proceeds to the next chunk. This matches the user-facing intent
   of "partial success — don't drop 499 results because one chunk had a bad
   ID".
6. **Return signature changes** from `dict[str, dict]` to
   `tuple[dict[str, dict], list[str]]` — a `(results, failed_request_ids)`
   pair. `_batch_get` is private (leading underscore), so this is an internal
   refactor; the three callers (`search`, `search_threads`, `list_drafts`)
   are updated in the same change.
7. **`RuntimeError` semantics preserved**: if every request across every
   chunk fails, the helper still raises `RuntimeError("All N batch requests
   failed")`. The bar for "all failed" is global, not per-chunk.
8. **Surfacing failures (the "error indicator")** at the command layer:
   `search` / `search_threads` / `list_drafts` add an optional
   `"failed_to_fetch": N` key to their returned dict when N > 0. This shows
   up in `desk mail search --json` output so agents can detect partial
   results without changing exit-code semantics. Human (non-JSON) output is
   unchanged for this PR.

The contract is now: **HTTP batch fan-outs of any size succeed as far as
Gmail allows, surface partial-failure counts to JSON consumers, and never
emit a raw traceback for the >100 case.**

## Alternatives Considered

### Alternative 1: Keep silent-drop semantics with no failure surface

**Description**: Chunk to 100, return the existing `dict[str, dict]`
unchanged, drop individual + whole-chunk failures silently.

**Pros**:
- Smallest change. Three callers untouched.
- Backward-compatible signature.

**Cons**:
- Violates the user-facing intent of [Idea 050](../ideas/050-chunk-gmail-batch-get.md):
  agents need a signal when a 500-message survey returned 497.
- Contradicts [ADR-004](004-agent-first-cli.md) — "agents don't know what
  to do next" when results disappear without trace.

**Why rejected**: Fixes the traceback, but loses the agent-actionable signal
the user explicitly asked for.

### Alternative 2: Parallel chunk execution via `concurrent.futures`

**Description**: Execute all chunks in parallel.

**Pros**:
- Lower wall-clock latency for very large batches.

**Cons**:
- Gmail's per-user read quota is the binding constraint; parallel may push
  into 429s for accounts already running heavy loads.
- Adds threading/futures complexity to a service-layer helper that today is
  a simple function.
- No measurement of the actual win. Premature optimization.

**Why rejected**: Sequential is enough to fix the bug and is the
defensible default. Parallel can be a future ADR backed by benchmarks.

### Alternative 3: Push the chunk loop into every caller

**Description**: Leave `_batch_get` capped at 100 inputs (raise on >100),
push chunking into `search`, `search_threads`, `list_drafts` independently.

**Pros**:
- Each caller controls its own batching policy.

**Cons**:
- Three copies of the same loop. Adding a fourth fan-out site means a fourth
  copy. Violates DRY for no real benefit.

**Why rejected**: The chunking logic is universal to `_batch_get`'s contract
(HTTP batch limit), not caller-specific.

## Consequences

### Positive

- **`desk mail search --max N` works for any N**, bounded only by Gmail's
  search-list page size and rate limits.
- **Failure visibility**: agents reading `--json` can see
  `"failed_to_fetch": N` and decide whether to retry, page again, or surface
  the gap to a human.
- **No raw traceback regression** for the canonical >100 case — aligned with
  [ADR-019](019-errors-to-stderr.md) stream discipline.
- **No new flags, no new commands.** Behavior is corrective, not additive.

### Negative

- **`_batch_get` signature changes**.
  - *Mitigation*: It's a private helper (`_` prefix). Three callers, all in
    the same file, updated in this PR.
- **JSON output schema gains an optional `failed_to_fetch` key**.
  - *Mitigation*: Optional, present only when N > 0. Agents that don't read
    it continue to work.

### Neutral

- The `RuntimeError("All N failed")` global-failure escape hatch is kept.
  Callers that currently catch this continue to behave identically when
  Gmail is fully broken.

## Implementation Notes

### Files affected

- `src/desk/services/gmail.py` — `_batch_get` chunking and signature change.
- `src/desk/services/gmail.py` — `search`, `search_threads`, `list_drafts`
  unpack the tuple, propagate `failed_to_fetch` into their return dicts.
- `tests/test_services/test_gmail.py` — update existing `TestBatchGet`
  tests to unpack the tuple, add new tests for >100-request chunking and
  whole-chunk failure.

### Out of scope

- Changes to `batch_modify` chunking — [ADR-006](006-query-based-bulk-operations.md)
  already handles it at the command layer.
- Per-failure structured-error emission to stderr for read paths. The
  existing silent-drop-per-request behavior is preserved; the
  `failed_to_fetch` count is the indicator. A follow-up idea can extend this
  to per-failure detail if real usage demands it.
- Human-readable output changes for `search` / `search_threads` /
  `list_drafts`. Today they don't surface fetch failures; this ADR doesn't
  change that. The `--json` consumer is the audience.

### Open questions

- **Parallel chunks**: worth measuring on a 5,000-message survey vs Gmail
  per-user read quotas. Defer to a follow-up ADR if real workloads warrant.
- **Per-failure detail**: do agents need failed request_ids to retry just
  those, or is a count enough? Today: count. If retry workflows emerge,
  promote to list.

## References

- [Idea 050](../ideas/050-chunk-gmail-batch-get.md) — bug report and sketch
- [ADR-004](004-agent-first-cli.md) — agent-friendly contracts
- [ADR-006](006-query-based-bulk-operations.md) — bulk-mutation chunking
  (different mechanism, different limit)
- [ADR-019](019-errors-to-stderr.md) — stream discipline for failures
- [Gmail batch HTTP requests](https://developers.google.com/gmail/api/guides/batch)
