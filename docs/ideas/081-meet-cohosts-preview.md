---
id: 081
title: Meet Co-Hosts (blocked on Developer Preview)
status: parked
effort: S
value: Name co-hosts from the CLI instead of clicking through the Meet UI
created: 2026-07-31
updated: 2026-07-31
adr: docs/decisions/036-google-meet-support.md
---

# Idea 081: Meet Co-Hosts

## Problem

The remaining half of issue #81. ADR-036 shipped auto-recording, auto-transcription, and auto
smart notes via `desk meet update`, but co-hosts are still UI-only.

## Sketch

```
desk meet cohost add <space> alice@example.com
desk meet cohost list <space>
desk meet cohost remove <space> alice@example.com
```

Maps to `spaces.members.create` / `.list` / `.delete` with `role: COHOST`.

## Open Questions

- [ ] **Blocker:** `spaces.members` is restricted to Google's Developer Preview Program. Check
      GA status before building — shipping it earlier means it fails for anyone not enrolled,
      and the error looks like a Desk bug.
- [ ] Moderation must be `on` for co-host management. Should `desk meet update` gain a
      `--moderation on|off`, or should the cohost command turn it on implicitly? Implicit
      state changes are usually the wrong call, so probably an explicit flag first.
- [ ] Does adding a member require the person to already be an invited guest of the Calendar
      event? The UI picker only offers invited guests, but that may be a UI constraint rather
      than an API one. Untested.
- [ ] Would this need `meetings.space.created` in addition to `.settings`? Unverified.

## Value Signal

Named in issue #81 as one of three things that had to be clicked in by hand. Lower value than
the artifact settings, which are the ones that determine whether a recording exists at all.

## Effort Guess

S once unblocked — three thin commands over one endpoint. The cost is entirely in the preview
gating, not the code.

## Notes

- Ordering trap worth documenting whenever this ships (and already in `desk meet --help` for
  the manual path): co-hosts are picked from the event's *invited guests*, so a staged event
  with no attendees shows an empty picker. Add guests, then set co-hosts, then add any
  remaining lists.
- ADR-036 alternative 2 records why we didn't ship this behind a `--preview` flag.
