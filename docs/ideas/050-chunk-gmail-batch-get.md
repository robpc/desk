---
id: 050
title: Chunk Gmail batch.get to Respect 100-Request Limit
status: adr-created
effort: S
value: desk mail search --max N>100 currently fails with HTTP 400; bulk operations are broken at exactly the scale where they matter
created: 2026-05-16
updated: 2026-05-18
adr: docs/decisions/021-chunked-http-batch-fanout.md
---

# Idea 050: Chunk Gmail batch.get to Respect 100-Request Limit

## Problem

`GmailClient._batch_get()` in `src/desk/services/gmail.py` constructs a single Gmail batch request containing one inner request per message ID, then executes it. The Gmail API rejects batches with more than 100 inner requests:

```
HttpError 400 ... "Inner request count exceeds the limit. Received: 500, Limit: 100"
```

This means `desk mail search --max 500` hard-fails. Anything > 100 hits the same wall. The user-visible symptom is a full Python traceback dumped to stdout/stderr — not a graceful degradation.

Encountered in real usage 2026-05-16 during a bulk inbox survey (sample 500 messages to rank senders by volume). Workaround: paginate `--max 100` calls manually with `--page-token`.

## Sketch

In `_batch_get`, split the request list into chunks of ≤100 and execute them sequentially (or in parallel — Gmail's per-user write quota is the binding constraint, not batch count):

```python
def _batch_get(self, requests):
    MAX_BATCH = 100
    results = []
    for i in range(0, len(requests), MAX_BATCH):
        chunk = requests[i:i + MAX_BATCH]
        batch = self.service.new_batch_http_request(callback=...)
        for r in chunk:
            batch.add(r)
        batch.execute()
        results.extend(chunk_results)
    return results
```

Sequential is simplest. Parallel via `concurrent.futures` could help latency at the cost of complexity — probably worth measuring before adding.

## Open Questions

- [ ] Should there be a `--max` ceiling enforced by the CLI as a sanity check, or do we let users specify arbitrary numbers and trust pagination?
- [ ] Are there other Gmail batch endpoints with the same limit that desk uses elsewhere (e.g. `modify`, `trash`)? Probably — bulk label operations may need the same treatment.
- [ ] Should errors in one chunk fail the whole batch, or return partial results with an error indicator?

## Value Signal

- Bulk operations (large surveys, "show me everything from sender X across all time") are exactly where a CLI beats clicking around in Gmail.
- The current failure mode is the worst kind: silent until you cross 100, then a stacktrace.
- Cheap to fix.

## Effort Guess

S — One function in one file. Test cases: 50 (one chunk), 100 (boundary), 150 (two chunks), 1000 (many chunks). Need to verify the callback aggregation semantics work across multiple batch.execute() calls.

## Notes

- Likely affects every desk mail command that fans out per-message details (search, threads, possibly attachments).
- Related: [[041-performance-optimization]] for any chunking-vs-parallelism tradeoff discussion.
- Related: [[029-structured-errors]] — when this fails, the user sees a raw Python traceback rather than a structured error.
