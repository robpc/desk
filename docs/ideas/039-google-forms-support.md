---
id: 039
title: Google Forms Support
status: implemented
effort: M
value: Agents can create surveys, collect responses, and build multi-path forms
created: 2026-02-17
updated: 2026-02-18
adr: docs/decisions/007-google-forms-support.md
---

# Idea 039: Google Forms Support

## Problem

Desk covers Gmail, Drive, Sheets, Docs, and Calendar but not Forms. Agents building workflows around surveys, feedback collection, or data gathering have no way to create or read forms through Desk.

## Sketch

Add `desk forms` command group with: `create`, `read`, `responses`, `add-question`, `add-section`. Include branching support (`--goto`, `--id`) for multi-path forms.

## Open Questions

- [x] Does the Forms API honor description in create? → No, requires two-step flow (ADR-007)
- [x] Does the Forms API honor client-supplied itemId? → Yes
- [ ] Should we add pagination to responses?
- [ ] Should quiz features (grading, correct answers) be added later?

## Value Signal

Completes Desk's coverage of the six core Google Workspace services.

## Effort Guess

M — New service client, 5 commands, branching logic, tests. Straightforward API.

## Notes

- Graduated to ADR-007
- PR #8 implements this
