---
id: "081"
title: Resolve Person-Calendar Names via Contacts
status: idea
effort: M
value: A calendar shared by a person would read as their name, not their email address
created: 2026-09-03
updated: 2026-09-03
adr: null
---

# Idea 081: Resolve Person-Calendar Names via Contacts

## Problem

A calendar shared from another person's account, with no
`summaryOverride` set, has a `summary` that is just their email address.
desk shows `gvc.wdc@gmail.com` where a name belongs.

[ADR-035](../decisions/035-calendar-display-name.md) covers the case
where the Name field *has* been edited: that writes `summaryOverride`,
which desk now honors. That resolved the case reported in
[issue #92](https://github.com/robpc/desk/issues/92).

What is left is the never-renamed calendar. Investigation for #92
established that within the `calendar` scope there is no human name for
one anywhere:

- no `summaryOverride` on the `calendarList` entry,
- `calendars.get` returns the email as `summary`,
- no event's `organizer`, `creator` or `attendees` entry carries a
  `displayName` for that address.

Any name would have to come from Google Contacts.

## Sketch

Look the calendar ID up via the People API (`people.searchContacts` or
`otherContacts.search`) and use the contact's display name when the
calendar has no better name of its own.

Precedence would extend ADR-035's: `summaryOverride` → contact name →
`summary`.

Almost certainly gated behind a flag or config setting rather than on by
default, so the scope is only requested by users who want the behavior.

## Open Questions

- [ ] Which scope: `contacts.readonly` covers saved contacts;
      `directory.readonly` covers a Workspace directory. A personal Gmail
      account sharing a calendar is likely in "other contacts," which has
      its own endpoint and scope semantics.
- [ ] Is a scope expansion acceptable at all for a naming convenience?
      Under [ADR-001](../decisions/001-oauth-credential-strategy.md) every
      user brings their own credentials, so a new scope means every
      existing user re-consents. That is a real cost for cosmetics.
- [ ] One extra API call per `cal list`, or a cached lookup? The list is
      small and changes rarely, so a local cache with a TTL is plausible.
- [ ] What if the address is not in contacts at all? Falls back to the
      email, so the feature is best-effort and the output shape must not
      depend on it.
- [ ] Privacy: reading a user's contacts to render a calendar list is a
      meaningful widening of what desk touches. Worth an explicit
      opt-in and a line in the README about what is read and why.

## Value Signal

**Weak, and weaker than it first looked.** #92 was filed against exactly
this symptom, but the calendar acquired a `summaryOverride` on its own
once its settings page was opened — no rename, no new scope — and
ADR-035 now surfaces it.

If Google materializes these display names on view, the population this
idea serves may be small and shrinking: calendars nobody has ever looked
at. It would earn its keep for an agent meeting a fresh account with many
untouched person-calendars, which has not been observed.

The agent-facing argument is the part that might still justify it: an
assistant that reads these names also says them back, so "I'll put it on
gvc.wdc@gmail.com" is both worse writing and an address surfacing where a
name belongs.

## Effort Guess

M. The lookup is straightforward; the cost is the scope decision, the
re-consent story, caching, and the opt-in surface.

## Notes

- [ADR-035](../decisions/035-calendar-display-name.md) — the
  `summaryOverride` half, and why this half was split out
- [Issue #92](https://github.com/robpc/desk/issues/92)
- [People API `otherContacts.search`](https://developers.google.com/people/api/rest/v1/otherContacts/search)
