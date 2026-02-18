---
id: 040
title: Forms — Mutations and Pagination
status: implemented
effort: M
value: Agents can modify forms after creation and paginate through responses
created: 2026-02-18
updated: 2026-02-18
adr: docs/decisions/007-google-forms-support.md
---

# Idea 040: Forms — Mutations and Pagination

## Problem

The initial Forms implementation (PR #8, ADR-007) covers the create-and-read workflow: create a form, add questions and sections, read structure, and list responses. This is enough for agents to build new forms, but not enough to manage them over time — can't fix a typo, remove a question, update a section title, or change form metadata. Response pagination was also missing, truncating results silently.

## What Was Implemented

### Mutation commands

- `desk forms update <form-id>` — Update form title/description
- `desk forms update-question <form-id> <item-id>` — Change question text, options, required flag, branching
- `desk forms update-section <form-id> <item-id>` — Change section title/description
- `desk forms delete-item <form-id> <item-id>` — Delete any item (question or section)

Design decisions:
- CLI uses **item IDs** (stable), not positional indices (shift on add/remove). Service layer handles ID→index lookup.
- Single `delete-item` command for both questions and sections (API operation is identical).
- Separate `update-question`/`update-section` because they have meaningfully different flag sets.
- `update-question` does **not** support changing question type (too destructive — use delete + re-add).

### Responses pagination

- `desk forms responses` now accepts `--page-token` for manual pagination
- JSON output includes `nextPageToken` when more results are available
- Human output shows a hint with the token value

## Notes

- Quiz mode was split into its own idea (042) — it has separate design questions around grading
- Form settings (open/close, confirmation message) remain uncaptured — low demand signal so far
