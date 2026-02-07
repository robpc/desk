---
id: 012
title: Watch/Poll Mode
status: idea
effort: L
value: Continuous email processing for automation
created: 2025-02-06
updated: 2025-02-06
adr: null
---

# Idea 012: Watch/Poll Mode

## Problem

For automation, you often want to continuously process new emails matching a query. Currently requires external cron/loop.

## Sketch

```bash
# Watch for new emails and print them
gmail watch "is:unread from:alerts"

# Watch and execute command for each
gmail watch "is:unread label:tickets" --exec "process-ticket.sh {id}"

# Watch with polling interval
gmail watch "is:unread" --interval 60  # check every 60 seconds

# Watch and pipe to processor
gmail watch "from:reports" --json | while read -r msg; do process "$msg"; done
```

## Technical Approaches

### Option A: Polling
Simple: query every N seconds, track seen message IDs, emit new ones.
- Pro: Simple, works everywhere
- Con: Delay up to polling interval, API quota usage

### Option B: Gmail Push Notifications
Gmail API supports push notifications via Cloud Pub/Sub.
- Pro: Real-time, no polling
- Con: Requires Pub/Sub setup, more complex, needs webhook endpoint

### Option C: History API
Use `users.history.list` to get changes since last check.
- Pro: More efficient than re-searching
- Con: Still requires polling, more complex than search

## Open Questions

- [ ] Polling vs push vs history API?
- [ ] How to handle `--exec` failures? (retry? skip? stop?)
- [ ] State persistence (track last seen message across restarts)?
- [ ] Daemonize option?

## Value Signal

Enables event-driven email automation without external tooling.

## Effort Guess

L - State management, error handling, possibly Pub/Sub integration. Significant new functionality.

## Notes

Could start simple (polling + track seen IDs) and evolve to push notifications later. MVP might just be a loop around search.
