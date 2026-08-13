---
id: 079
title: Scope-Aware Commands
status: adr-created
effort: M
value: Build features behind scopes users haven't granted yet, without a forced re-auth flag day
created: 2026-07-31
updated: 2026-07-31
adr: docs/decisions/034-scope-aware-commands.md
---

# Idea 079: Scope-Aware Commands

## Problem

Desk is about to need OAuth scopes that existing users have not consented to. Issues #80
and #81 (Calendar/Meet gaps) both land on the Meet REST API, which needs
`meetings.space.settings` — not in `config.SCOPES` today. Every future service will hit
the same wall.

Adding a scope doesn't invalidate an existing token: refresh keeps working on the old
grant, and only calls needing the new scope fail. But today Desk can't tell the difference
between "you have this" and "you don't", so the failure surfaces as a mid-task 403. That
makes shipping a scope-dependent feature feel like it requires re-authenticating the whole
user base at once, which is the actual blocker on #81.

Idea 060 addressed the *reactive* half (a scope 403 now says "run `desk auth login`"
instead of "request access from the owner"). The proactive half it claimed —
`auth status` scope-diff — never worked: issue #82 found the granted set was never
persisted, so `missing_scopes` was always `[]`.

## Sketch

Port the pattern Cafe landed in its ADR-006 + ADR-024, adapted to Desk:

1. An `enforce_scopes()` check resolving scopes **at invocation only**, emitting the
   existing `INSUFFICIENT_SCOPES` structured error before any API call, naming the scope
   and the affected commands. Called from a service's `_get_client()` for service-wide
   scopes. (A `@requires_scope` decorator for partial-coverage scopes shipped and was then
   removed in ADR-036 — Meet became its own service, so nothing needed it.)
2. A `SCOPE_COMMANDS` map in `config.py` keyed by scope, whose targets are either a service
   name or a `"service command"` pair.
3. `--capabilities` gains a per-command `scope` list and a tri-state `enabled` flag
   derived from the map and the granted set at runtime.

Commands stay **visible but disabled** rather than hidden, so `--help` doesn't vary
between users.

## Open Questions

- [x] Is the granted scope set reliably available? — No. Issue #82; fixed as step 1.
- [x] Can the Meet API patch a Calendar-created conference? — Yes,
      `meetings.space.settings` is documented for "spaces created by other apps" and is
      non-sensitive.
- [x] Hide unscoped commands or show them disabled? — Show disabled (see ADR).
- [ ] Should `desk auth login` request new scopes by default, or opt in per feature
      (`--with meet`)? ADR-034 picks default-request; revisit if a sensitive or
      restricted scope ever lands.
- [ ] Does the gcloud ADC path (`GCLOUD_SCOPES`) ever yield a knowable grant set? It
      reports unknown today, so the gate fails open there.

## Value Signal

Directly unblocks #80/#81, which are real user-reported gaps found while scripting
training invites. Generalizes: every scope addition after this one gets discoverability
for free instead of re-litigating the re-auth question.

Agent-facing value (ADR-004): an agent can read `--capabilities` and know a command won't
work *before* trying it, and tell the user exactly why.

## Effort Guess

M — the decorator and map are small. `--capabilities` is a hand-maintained static dict in
`cli.py` (not Click introspection like Cafe's), so threading `scope` through every entry
is the bulk of the work.

## Notes

- Prior art read directly: `~/git/yahoo-orion/cafe/docs/decisions/006-scope-aware-commands.md`
  and `024-lazy-scope-resolution.md`.
- Cafe's hard-won lesson: resolving scopes at *decoration* time crashed every invocation
  on hosts with no keyring backend, because the CLI imports all command modules at
  startup. Desk has the same structure and a keyring path — gate at invocation only.
- Cafe's gate fails open when the granted set is unknown. Desk must do the same, since
  pre-#82 tokens have no record.
- Cafe's `SCOPE_COMMANDS` lists scopes for unbuilt features (`"search:read.files":
  ["file search (idea 032)"]`) — pre-declaring is fine.
- Related: [[slides-phased-rollout]] (the `presentations` scope addition that first
  exposed this), idea 060.
