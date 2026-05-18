---
id: 049
title: Expose Arbitrary Message Headers in mail read --json
status: idea
effort: S
value: Agents need RFC 5322 headers (List-Unsubscribe, Auto-Submitted, Authentication-Results, etc.) for tasks like unsubscribe automation, DMARC inspection, mailing-list workflows
created: 2026-05-16
updated: 2026-05-16
adr: null
---

# Idea 049: Expose Arbitrary Message Headers in mail read --json

## Problem

`desk mail read --json` returns a curated set of headers (`from`, `to`, `cc`, `subject`, `date`, `deliveredTo`, `messageId`, `references`, `replyTo`) but not arbitrary RFC 5322 headers. Several agent workflows require headers desk doesn't expose:

- **`List-Unsubscribe` / `List-Unsubscribe-Post`** — required to programmatically unsubscribe from marketing mail (RFC 2369, RFC 8058 one-click). Without this, an agent doing bulk inbox cleanup must either parse the message body for unsubscribe links (unreliable, often gated behind tracking redirects) or shell out past desk and call the Gmail API directly.
- **`Authentication-Results`** — DMARC/SPF/DKIM results, useful for triaging suspicious mail.
- **`Auto-Submitted`** — distinguish auto-replies from human responses.
- **`In-Reply-To`** beyond `References` — accurate thread reconstruction.
- **`X-*` custom headers** — sender-specific metadata (e.g., `X-Mailer`, mailing list IDs).

Real-world example (today's session): cleaning up promotional mail required fetching `List-Unsubscribe` for 20 senders. Workaround was a side-channel Python script that imported `desk.auth.get_credentials` and built a Gmail client directly — bypassing desk entirely.

## Sketch

### Option A: `--headers` flag accepts a list

```bash
desk mail read MSG_ID --json --headers List-Unsubscribe,List-Unsubscribe-Post
```

Returns the named headers in a `headers` field alongside existing curated fields. Cheap and targeted — only fetches what's asked for.

### Option B: `--all-headers` flag

```bash
desk mail read MSG_ID --json --all-headers
```

Returns every header. Larger payload, but no need to know names upfront.

### Option C: Always include in `--json`

Always populate a `headers: {name: value}` dict in JSON output. Heaviest payload but matches "JSON output should be machine-complete" intuition.

Option A is most aligned with ADR-style minimalism. B is convenient for exploration. C is most agent-friendly but most expensive.

## Open Questions

- [ ] Does Gmail API's `format=metadata` with `metadataHeaders` save bandwidth vs `format=full` when only headers are needed? (Yes — confirmed in usage today.)
- [ ] Should multi-valued headers (e.g. `Received` appears N times) return a list or be joined?
- [ ] Should this also affect `desk mail search --json` so headers can be retrieved in bulk without N round-trips?

## Value Signal

- Hit in real usage 2026-05-16 during a bulk unsubscribe task — had to write a workaround script.
- Unsubscribe automation is a common agent-driven inbox cleanup pattern; this gap pushes that work outside the CLI.
- Cheap to add (Gmail API already exposes headers via `metadataHeaders` query parameter).

## Effort Guess

S — Plumbing change in `services/gmail.py` to accept a header list, pass through `metadataHeaders`, and surface the result in the read command's JSON output. No new dependencies, no schema migrations.

## Notes

- Pairs with [[037-surface-linked-docs-and-urls]] — both close gaps where the CLI hides information agents need.
- The bulk-search variant (search returning headers) would also reduce the N+1 problem when a workflow needs to filter messages by header value (e.g., "all mail with `List-Unsubscribe`").
