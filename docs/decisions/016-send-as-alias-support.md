---
id: "016"
title: Send-as Alias Support
status: accepted
date: 2026-03-03
supersedes: []
superseded_by: null
tags: [mail, api]
---

# ADR-016: Send-as Alias Support

## Context

Gmail users often have multiple send-as aliases (e.g., personal address, team alias, role-based address). When replying via Desk, the From address was always the account's primary address — even if the original email was sent to an alias. Gmail's web UI auto-detects the correct alias; Desk should too.

## Decision

1. **`--from` flag** on `send`, `reply`, and `forward` commands to explicitly send from an alias.
2. **Auto-detect on reply**: Match the original message's Delivered-To, To, then CC headers against the user's configured send-as aliases. Set From to the matched alias. `--from` overrides auto-detect.
3. **`desk mail aliases` command** to list configured send-as addresses.
4. **Service layer**: `list_send_as_aliases()` and `detect_send_as_alias()` in GmailClient.
5. **No new scopes needed** — `gmail.modify` and `gmail.settings.basic` already cover `sendAs.list`.

Implementation detail: Gmail API's `users.messages.send` has no `sendAs` field. Setting the `From` MIME header to a verified alias is sufficient.

## Alternatives Considered

### Alternative 1: Auto-detect only (no `--from` flag)

**Why rejected**: Users need explicit control when an alias can't be auto-detected (e.g., BCC'd messages, new compose).

### Alternative 2: Require `--from` always (no auto-detect)

**Why rejected**: Adds friction to every reply. Gmail's web UI auto-detects — we should match that UX.

## Consequences

### Positive

- Replies go out from the correct alias automatically
- Agents composing from aliases can use `--from` explicitly
- `desk mail aliases` enables discovery

### Negative

- Auto-detect adds one extra API call (`sendAs.list`) per reply (mitigated: fast, small payload)

## Implementation Notes

- Auto-detect priority: Delivered-To → To → CC → fallback to default
- Only verified/accepted aliases can be used as From (Gmail API rejects unverified)
- Key files: `src/desk/services/gmail.py`, `src/desk/commands/mail.py`
