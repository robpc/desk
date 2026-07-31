---
id: 036
title: Google Meet Support — Space Artifact Settings
status: accepted
date: 2026-07-31
supersedes: []
superseded_by: null
tags: [meet, auth, api, agent-first]
---

# ADR-036: Google Meet Support — Space Artifact Settings

## Context

Issue #81: Desk has no Google Meet API support, so the settings that govern *how a meeting
runs* — auto-recording, auto-transcription, auto smart notes, co-hosts — can only be clicked
in by hand. Hit while scripting training invites: after ADR-035 everything about the *event*
was scriptable, but recording had to be set in the UI, which for a session published to
people who can't attend is the difference between a working artifact and a forgotten one.

The issue correctly flagged that its own premises needed checking before building. Verified
against current docs:

- **Auto-artifacts are reachable.** `meetings.space.settings` is documented for "auto
  artifact generation for **spaces created by other apps**" and is a **non-sensitive** scope,
  so no Google verification review. `artifactConfig` carries no preview label.
- **A Calendar conference is addressable.** `spaces.get` accepts `spaces/{meetingCode}`, so
  the `conferenceId` that ADR-035 now surfaces on every event read resolves a space directly.
  `meetings.space.created` — which only covers spaces the *app* created — is not needed.
- **Co-hosts are not shippable.** `spaces.members.create` with `role: COHOST` is labeled
  **Developer Preview Program** (enrollment-gated), and moderation must be `on` for co-host
  management. The issue's ordering trap (co-hosts are chosen from invited guests, so a staged
  event shows an empty picker) is real but moot while the API is gated.

So the issue's own fallback — "if it can't, this whole issue is a docs note instead of a
feature" — applies to co-hosts only. The artifact settings are a feature.

The re-consent cost that #81 identified as "the real cost of the feature" is handled by
ADR-034: the scope gate and `--capabilities` make an ungranted scope legible instead of a
mid-task 403, so the scope can be added without coordinating a re-auth.

## Decision

### 1. A `meet` service group, not flags on `desk cal`

```
desk meet read <space>      → space config and artifact settings
desk meet update <space>    → set auto-record / transcript / smart notes
```

Issue #81 suggested `desk cal create --meet --auto-record --cohost alice@…`. We reject that:
it makes a Calendar command call the Meet API, which is exactly the cross-service composition
ADR-003 forbids. It would also bundle two failure modes — event created, artifact config
rejected has no clean receipt — and would gate `cal create` on a scope most of its uses don't
need.

The agent writes the two-step instead, which `conferenceId` on read (ADR-035) makes cheap:

```
desk cal create "Training" --start … --end … --meet --json   # → conferenceId
desk meet update <conferenceId> --auto-record on
```

`<space>` accepts either a server-assigned space ID or a meeting code, because `spaces.get`
and `spaces.patch` both do.

### 2. `on` / `off` / `default` values, not bare flags

```
desk meet update abc-defg-hij --auto-record on --auto-transcript on
```

Each of `--auto-record`, `--auto-transcript`, `--auto-smart-notes` takes an explicit value
mapping to the API's `AutoGenerationType`: `on` → `ON`, `off` → `OFF`, `default` →
`AUTO_GENERATION_TYPE_UNSPECIFIED` ("defer to user policy").

A bare `--auto-record` flag could only ever turn things on, and the third state — "stop
overriding, defer to policy" — would be unreachable. Only the fields actually passed go into
the `updateMask`, so an unmentioned setting is untouched.

### 3. The `meetings.space.settings` scope, gated at the service

Added to `config.SCOPES`, and registered in `SCOPE_COMMANDS` against the whole `meet`
service. Existing tokens keep working for every other service; `desk meet` reports itself
disabled in `--capabilities` and fails fast with `INSUFFICIENT_SCOPES` naming
`desk auth login`, per ADR-034.

`meetings.space.created` and `.readonly` are deliberately **not** requested. `.created` only
covers app-created spaces, which isn't our case, and `.settings` already permits
`spaces.get`.

### 4. Co-hosts are documented as UI-only, not implemented

`desk meet --help` states that co-hosts must be set in the Calendar/Meet UI, that this is a
Google Developer Preview limitation rather than a Desk gap, and notes the ordering trap
(add guests first — the co-host picker only offers invited guests). Shipping a command that
fails for anyone not enrolled in a preview program would be worse than not shipping one.

### 5. `requires_scope` is removed from `agent.py`

ADR-034 shipped `enforce_scopes()` plus a `@requires_scope` decorator, the latter justified
by an anticipated Meet feature that would cover only *part* of the `cal` service. Decision 1
makes Meet its own service, so the scope is service-wide and the decorator has no user and
no reader — nothing consumes the `_required_scopes` attribute it set, since
`--capabilities` derives everything from `SCOPE_COMMANDS`.

Rather than ship a tested-but-unused extension point, we delete it. A genuine
partial-coverage scope can reintroduce a per-command variant in ~15 lines when one actually
arrives. This amends ADR-034 §2.

## Alternatives Considered

### Alternative 1: `desk cal create --auto-record` (as issue #81 suggests)

**Pros**:
- One command for the whole flow; fewest round trips
- Matches how the user thinks about the task

**Cons**:
- Cross-service composition, forbidden by ADR-003
- Partial-failure states with no clean receipt
- Gates `cal create` on a scope most of its callers don't need

**Why rejected**: ADR-003. Two primitives compose fine now that `conferenceId` is on reads.

### Alternative 2: Ship co-hosts anyway, behind a `--preview` flag

**Pros**:
- Fully answers #81
- Enrolled users get the feature immediately

**Cons**:
- Fails for anyone not in the Developer Preview Program, with an error that looks like a Desk
  bug
- Preview APIs change without notice; we'd own the churn
- `--preview` is invented vocabulary for "might not work"

**Why rejected**: a documented limitation is more honest than a command that usually fails.
Revisit when `spaces.members` reaches GA.

### Alternative 3: Request `meetings.space.created` as well

**Pros**:
- Covers spaces Desk itself might create later

**Cons**:
- Desk doesn't create spaces — Calendar does, via `conferenceData`
- A second scope for no present capability, paid for in consent-screen surface

**Why rejected**: `.settings` is sufficient and documented for exactly our case.

### Alternative 4: Bare boolean flags (`--auto-record` / `--no-auto-record`)

**Pros**:
- Terser for the common "turn it on" case

**Cons**:
- Two flags per setting, and the third state (defer to policy) still needs a third spelling
- Doesn't match the API's tri-state enum

**Why rejected**: one flag with three values maps cleanly to `AutoGenerationType`.

## Consequences

### Positive

- A recorded, transcribed training session is fully scriptable end to end
- The scope addition costs no forced re-auth, thanks to ADR-034
- `meet read` gives an agent a way to verify settings took effect — self-verification rather
  than asking the user to check the UI

### Negative

- First scope added since `presentations`, so every user sees `meetings.space.settings` in
  `auth status` as missing until they re-auth. Intended: that's the honest report, and only
  `desk meet` is affected.
- Two commands instead of one for "create a recorded meeting". Accepted cost of ADR-003.
- Co-hosts remain UI-only, so #81 is only partly closed. Tracked in idea 081.
- Artifact settings apply to the *space*, so on a recurring event they affect every
  occurrence — there's no per-occurrence override in the API. Documented in `--help`.

### Neutral

- `desk meet` is the first service group with no read-only capability beyond its own config.

## Implementation Notes

- `src/desk/config.py` — scope + `SCOPE_COMMANDS` entry for `meet`
- `src/desk/services/meet.py` — `MeetClient.get_space()`, `configure_artifacts()`
- `src/desk/commands/meet.py` — `read`, `update`
- `src/desk/cli.py` — register the group, add to `--capabilities`
- `src/desk/agent.py` — remove `requires_scope`

Rollback: removing the `SCOPES` entry and the group leaves no trace; tokens that granted the
scope simply carry an unused grant.

## References

- Issue #81, issue #80
- [Meet spaces.patch](https://developers.google.com/workspace/meet/api/reference/rest/v2/spaces/patch)
- [Meet spaces.get](https://developers.google.com/workspace/meet/api/reference/rest/v2/spaces/get)
- [Configure meeting spaces and members](https://developers.google.com/workspace/meet/api/guides/meeting-spaces-configuration)
- ADR-003 (no cross-service commands), ADR-034 (scope-aware commands), ADR-035 (Calendar fields)
