---
id: 035
title: Performance Optimization - Batch Fetch
status: implemented
effort: M
value: 5-10x speedup for listing commands (search, threads, drafts)
created: 2026-02-09
updated: 2026-02-09
adr: null
---

# Idea 035: Performance Optimization - Batch Fetch

## Problem

`desk mail unread` takes ~5.5 seconds due to an N+1 query pattern: `messages().list()` returns 20 IDs (1 API call), then `messages().get()` is called sequentially for each one (20 more API calls). With ~200ms network round-trip per call, that's ~4 seconds of avoidable latency.

Three methods in `GmailClient` have this pattern:
- `search()` — sequential `messages().get()` per message
- `search_threads()` — sequential `threads().get()` per thread
- `list_drafts()` — sequential `drafts().get()` per draft

## Sketch

Use `service.new_batch_http_request()` to combine N individual GET calls into a single HTTP request. This reduces 21 round-trips to 2.

- Add `_batch_get()` private helper to `GmailClient`
- Refactor all three methods to build request objects, batch them, then parse results
- Preserve ordering by iterating over original ID list
- Handle partial failures gracefully (skip failed items)

**Important**: Must use `self.service.new_batch_http_request()` — NOT raw `BatchHttpRequest()`. The raw constructor defaults to a legacy batch endpoint that Google deprecated in 2020.

Expected result: **~5.5s down to ~0.5-1.5s**.

## Open Questions

- [x] Which methods are affected? → `search()`, `search_threads()`, `list_drafts()`
- [x] Correct batch API to use? → `service.new_batch_http_request(callback=cb)`

## Value Signal

Direct user-facing latency improvement. Every `desk mail` listing command benefits.

## Effort Guess

M — Three methods to refactor with a shared helper, plus test updates. Straightforward pattern replacement.

## Notes

- Google Batch API docs: https://developers.google.com/gmail/api/guides/batch
- Max 100 requests per batch (we default to 20, well within limits)
