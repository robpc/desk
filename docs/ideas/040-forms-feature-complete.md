---
id: 040
title: Forms — Feature Complete
status: planned
effort: M
value: Forms v1 ships create-and-append only; full parity requires mutation, pagination, and quiz support
created: 2026-02-18
updated: 2026-02-18
adr: docs/decisions/007-google-forms-support.md
---

# Idea 040: Forms — Feature Complete

## Problem

The initial Forms implementation (PR #8, ADR-007) covers the create-and-read workflow: create a form, add questions and sections, read structure, and list responses. This is enough for agents to build new forms, but not enough to manage them over time. Several capabilities were deliberately deferred to ship a working v1.

## What's Missing

### Mutation commands

Agents can't modify forms after creation. Needed:

- `desk forms update-question <form-id> <item-id>` — Change question text, type, options, or required flag
- `desk forms delete-question <form-id> <item-id>` — Remove a question
- `desk forms update-section <form-id> <item-id>` — Change section title/description
- `desk forms delete-section <form-id> <item-id>` — Remove a section
- `desk forms update <form-id>` — Update form title/description

These map to the Forms API `batchUpdate` with `updateItem` and `deleteItem` requests.

### Responses pagination

`desk forms responses` returns a single page (up to `--limit`). Forms with many responses are truncated silently. Need to either:

- Follow `nextPageToken` internally to fetch all responses up to the limit, or
- Support `--page-token` for manual pagination (consistent with other Desk commands)

### Quiz mode

The Forms API supports quizzes natively. Missing:

- `desk forms create --quiz` — Create a form in quiz mode
- Setting correct answers and point values on questions
- Grading and score data in responses output

### Form settings

The Forms API exposes settings that aren't surfaced:

- Accepting responses (open/close a form)
- Confirmation message
- Response limits

## Open Questions

- [ ] Should mutation commands use item IDs or positional indexes?
- [ ] Should quiz features be a separate idea given their complexity?
- [ ] Is there demand for form duplication (`desk forms copy`)?

## Value Signal

Any agent workflow that creates a form and then needs to iterate on it (fix a typo, add a missed question, close responses) hits these gaps immediately.

## Effort Guess

M — Each mutation command is straightforward (`batchUpdate` with different request types). Pagination is a small change. Quiz mode is the largest item but can be incremental.

## Notes

- ADR-007 documents why these were deferred for v1
- The Forms API `batchUpdate` endpoint handles all mutations — no new API surface needed
- Mutation commands should follow the same patterns as existing Desk commands (structured errors, receipts, `--json`, `--dry-run`)
