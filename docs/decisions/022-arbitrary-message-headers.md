---
id: "022"
title: Expose Arbitrary Message Headers via `--headers`
status: accepted
date: 2026-05-18
supersedes: []
superseded_by: null
tags: [gmail, cli, agent-first, json]
---

# ADR-022: Expose Arbitrary Message Headers via `--headers`

## Context

`desk mail read --json` and `desk mail search --json` return a curated set of
headers (`from`, `to`, `cc`, `subject`, `date`, `deliveredTo`, `messageId`,
`references`, `replyTo`). Several agent workflows require headers Desk
doesn't currently expose:

- **`List-Unsubscribe` / `List-Unsubscribe-Post`** — RFC 2369 / RFC 8058
  one-click unsubscribe. Without it, bulk inbox cleanup must scrape body
  HTML for unsubscribe links (unreliable, often gated behind tracking
  redirects) or shell out past Desk entirely.
- **`Authentication-Results`** — DMARC/SPF/DKIM triage of suspicious mail.
- **`Auto-Submitted`** — distinguish auto-replies from human responses.
- **`In-Reply-To`** — accurate thread reconstruction.
- **`X-*` custom headers** — sender-specific metadata.

Hit in real usage 2026-05-16 during a bulk-unsubscribe task that fell back
to a side-channel Python script importing `desk.auth.get_credentials()` —
exactly the kind of escape hatch ADR-004 (Agent-First CLI) is meant to
prevent. See [Idea 049](../ideas/049-expose-message-headers.md).

Three options were considered: a list flag (Option A), a separate
`--all-headers` flag (Option B), and always-include in `--json` (Option C).
Option A was preferred by Idea 049's author. Option C is heaviest. Option B
adds a second flag for what is conceptually one knob: "tell me which
headers."

## Decision

Add a single `--headers` flag to both `desk mail read` and `desk mail
search`. It accepts a comma-separated list of RFC 5322 header names, or the
literal `*` for "every header on the message." Resolved headers are
surfaced in a `headers` field in the JSON output and printed below the
existing fields in human-readable output.

### Surface

```bash
# Targeted
desk mail read MSG_ID --json --headers List-Unsubscribe,List-Unsubscribe-Post

# Wildcard
desk mail read MSG_ID --json --headers '*'

# Same shape on search
desk mail search "category:promotions" --json --headers List-Unsubscribe
```

### Output shape

```json
{
  "id": "abc123",
  "from": "...",
  "subject": "...",
  "headers": {
    "List-Unsubscribe": ["<https://example.com/u?id=42>"],
    "Authentication-Results": ["mx.google.com; dkim=pass header.i=@example.com"]
  }
}
```

Every value in `headers` is a **list of strings**. Single-valued headers
appear as a one-element list. Multi-valued headers (`Received`,
`Authentication-Results`, etc.) preserve every occurrence in the order
returned by Gmail. This is predictable for agents — no `isinstance(v,
list)` branching — and lossless for headers RFC 5322 explicitly allows to
repeat.

### Name matching

- **Input names are case-insensitive.** `--headers list-unsubscribe` and
  `--headers LIST-UNSUBSCRIBE` both match `List-Unsubscribe`.
- **Output keys preserve Gmail's casing.** We return the name exactly as it
  appears on the message payload, not the user's input casing.
- **Unknown names are silently absent** from the output dict (not an
  error). Agents asking for `List-Unsubscribe` on a message that doesn't
  have one get a `headers` dict that omits the key, not a stub
  `{"List-Unsubscribe": []}`.

### API efficiency

- **`mail read`** already calls `messages.get(format="full")`, which
  returns every header. The flag is pure filtering at parse time — no
  extra API cost.
- **`mail search`** currently calls `messages.get(format="metadata",
  metadataHeaders=["From","Subject","Date"])` per result. The flag
  augments `metadataHeaders` with the requested names; for `*` it drops
  `metadataHeaders` entirely so Gmail returns every header in metadata
  mode. Body is never fetched on the search path, so payload stays small.

### Curated fields are unchanged

The existing top-level fields (`from`, `subject`, `messageId`, etc.) are
**not** affected by `--headers`. They continue to appear regardless of
flag value. `--headers` adds the `headers` dict on top.

### Scope

Read and search both. Other commands that surface message metadata
(threads detail, drafts) do not get `--headers` in this ADR — they have
their own response shapes and use cases. Easy to extend later if needed.

## Alternatives Considered

### Alternative 1: Two flags — `--headers LIST` and `--all-headers`

**Description**: Idea 049's Option A + Option B. One flag for explicit
lists, a second boolean for "everything."

**Pros**:
- Each flag is unambiguous about its intent.
- `--all-headers` is one fewer keystroke than `--headers '*'`.

**Cons**:
- Two knobs for one logical question ("which headers do you want?"). The
  user must choose which flag, and the flags can technically be combined
  in ways we'd then have to define (`--headers X --all-headers`).
- More surface area, more `--help` clutter, more test combinations.

**Why rejected**: One flag with a documented wildcard token is the minimal
surface that covers both cases. Aligns with [ADR-002](002-command-composability.md)
preference for primitives over compound knobs.

### Alternative 2: Always include all headers in `--json` output

**Description**: Idea 049's Option C. Drop the flag entirely; every `mail
read --json` and `mail search --json` returns every header.

**Pros**:
- Zero new flags.
- Agents never need to know what to ask for.

**Cons**:
- Payload bloat on every call. A search of 100 messages × every header is
  a non-trivial JSON blob, and most callers want only a couple of named
  fields.
- Changes the shape of every existing `--json` consumer in a non-additive
  way (new top-level field on every record, in a category — header
  spelunking — most callers don't use).

**Why rejected**: Heaviest default for a feature most callers won't use.
Opt-in via `--headers` is cheaper and matches ADR-004's principle that
agent affordances are explicit.

### Alternative 3: Repeatable `--header NAME` flag

**Description**: `--header List-Unsubscribe --header Auto-Submitted` in
the style of cURL.

**Pros**:
- Composes naturally with shell loops.

**Cons**:
- Verbose. The bulk-unsubscribe example would require 5+ flags.
- No clean wildcard ("`--header '*'`" doesn't read as "all").
- No precedent in Desk; existing repeatable flags (`-c/--calendar` in the
  draft for issue 27, `--add-label`) are for inherently set-valued
  vocabulary, not lists of opaque names.

**Why rejected**: Comma-separated list with wildcard token covers both
single and bulk cases with one flag. Idea 049's Option A.

## Consequences

### Positive

- **Unsubscribe automation works inside Desk.** No more side-channel
  Python scripts for the canonical bulk-cleanup workflow.
- **Predictable output shape** — `headers: {name: [values]}` is always a
  list-of-strings, never branching on cardinality.
- **No API cost on `read`**; minor extra metadata on `search` proportional
  to header count.
- **Aligns with [ADR-004](004-agent-first-cli.md)** — agents see exactly
  what they asked for, no more, no less.
- **One flag, one mental model.** Pairs naturally with
  [ADR-006](006-query-based-bulk-operations.md)'s bulk patterns.

### Negative

- **Header values returned as `list[str]` even for single-valued headers**
  is a deliberate ergonomic trade-off. Single-line awk-style consumers
  must `[0]` the list. Documented in the ADR and `--help`.
  - *Mitigation*: predictability beats convenience for agents, and humans
    rarely use `--headers` in non-JSON mode.
- **`*` wildcard parsing** must survive shells that glob `*` against the
  cwd. Tell users to quote it (and the `--help` example does so).

### Neutral

- Header name matching is case-insensitive on input, casing-preserving on
  output. RFC 5322 §3.6.5 says names are case-insensitive, so this is the
  correct semantic.
- No effect on `desk mail threads` or `desk mail drafts` — those have
  different output shapes and are out of scope.

## Implementation Notes

### Files affected

- `src/desk/services/gmail.py`:
  - `_parse_message_metadata(msg, extra_headers=None)` — new optional
    param. When non-None, builds the `headers` sub-dict from the parsed
    `payload.headers` list, applying case-insensitive matching and
    multi-value preservation.
  - `_parse_full_message(msg, extra_headers=None)` — pass-through to
    `_parse_message_metadata`.
  - `search(query, max_results, page_token, extra_headers=None)` — passes
    requested names into `metadataHeaders` (or drops the param when `*`
    is requested).
  - `read(message_id, extra_headers=None)` — pure parse-time filter, no
    API change.

- `src/desk/commands/mail.py`:
  - Add `--headers` Click option to `search` and `read`.
  - Helper `_parse_headers_spec(spec: str | None) -> list[str] | None`
    handles the `'*'` wildcard and CSV split.

- `tests/test_services/test_gmail.py`:
  - `_parse_message_metadata` returns expected `headers` dict for: empty
    `extra_headers`, list of names, `['*']` wildcard, multi-valued
    headers, case-insensitive matching, unknown name (silently absent).

- `tests/test_commands/test_mail.py`:
  - `desk mail read --headers List-Unsubscribe --json` returns expected
    shape.
  - `desk mail search --headers '*' --json` returns headers on every
    message.

### Out of scope

- `--headers` on `desk mail threads`, `desk mail drafts`. Add later if
  real usage shows demand.
- Human-mode rendering polish (table, color-coded values, etc.). Plain
  one-line-per-header is enough.
- Server-side filtering by header value (e.g., "all mail with
  `List-Unsubscribe`"). That's a Gmail search-query feature, not a
  client-side concern.

## References

- [Idea 049](../ideas/049-expose-message-headers.md) — problem statement
  and option sketch
- [ADR-002](002-command-composability.md) — primitives over compound knobs
- [ADR-004](004-agent-first-cli.md) — agent-first contracts
- [ADR-006](006-query-based-bulk-operations.md) — bulk operations pattern
  this feeds into
- [RFC 5322 §3.6](https://datatracker.ietf.org/doc/html/rfc5322#section-3.6) —
  header field definitions and case rules
- [Gmail API `users.messages.get`](https://developers.google.com/gmail/api/reference/rest/v1/users.messages/get) —
  `format` and `metadataHeaders` parameters
