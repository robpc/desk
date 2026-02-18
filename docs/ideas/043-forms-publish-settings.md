---
id: 043
title: Forms — Publish and Close Responses
status: idea
effort: S
value: Agents can open/close forms and control whether they accept responses
created: 2026-02-18
updated: 2026-02-18
adr: null
---

# Idea 043: Forms — Publish and Close Responses

## Problem

Agents can create and modify forms but can't control their lifecycle. No way to close a survey when it's done, reopen it later, or unpublish it entirely. Common for time-boxed workflows (event RSVPs, weekly polls, feedback rounds).

## Sketch

The Forms API exposes `forms.setPublishSettings` (separate from `batchUpdate`) with two flags:

- `isPublished` — whether the form is accessible at its URL
- `isAcceptingResponses` — whether it accepts new submissions (can close while staying visible)

Possible commands:

- `desk forms publish <form-id>` / `desk forms unpublish <form-id>`
- `desk forms close <form-id>` / `desk forms open <form-id>` (toggle accepting responses)

Or flags on `desk forms update`:

- `--published / --unpublished`
- `--accepting / --closed`

The flag approach is simpler but mixes `batchUpdate` (title/description) with `setPublishSettings` (lifecycle) in the same command — two different API calls under the hood.

## Open Questions

- [ ] Separate commands vs flags on update?
- [ ] Forms created after March 31 2026 start unpublished — should `desk forms create` auto-publish?
- [ ] Should `desk forms read` show publish/accepting status?

## Value Signal

Any agent running a time-boxed survey hits this. Discovered while implementing idea 040.

## Effort Guess

S — One new service method, one or two CLI commands. The API is straightforward.
