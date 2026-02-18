---
id: 007
title: Google Forms Support
status: accepted
date: 2026-02-18
supersedes: []
superseded_by: null
tags: [forms, api, new-service]
---

# ADR-007: Google Forms Support

## Context

Desk supports Gmail, Drive, Sheets, Docs, and Calendar — five of the six core Google Workspace services that agents interact with regularly. Google Forms is the missing piece. Agents building workflows around surveys, feedback collection, and data gathering currently have no way to create or read forms through Desk.

The Google Forms API (v1) is relatively simple compared to other Workspace APIs, with a small surface area focused on form structure and response collection.

## Decision

Add Google Forms as a new Desk service with five commands:

- **`desk forms create`** — Create a new form (with optional description)
- **`desk forms read`** — Read form structure and questions
- **`desk forms responses`** — List form responses
- **`desk forms add-question`** — Add a question (text, paragraph, choice, checkbox, dropdown, scale)
- **`desk forms add-section`** — Add a section break (with optional custom ID for branching)

Branching support is included via `--goto` on `add-question` and `--id` on `add-section`, enabling agents to build multi-path forms.

All commands follow existing Desk patterns: structured errors, operation receipts, `--json` output, and `--quiet` flag.

### Scopes

Two new OAuth scopes are required:

- `https://www.googleapis.com/auth/forms.body` — Read/write form structure
- `https://www.googleapis.com/auth/forms.responses.readonly` — Read responses

Users must re-authenticate once (`desk auth login`) to pick up the new scopes.

### API quirks handled

- **`forms.create` ignores description**: The Forms API silently drops `info.description` from the create request body. We use a two-step flow: create the form, then set description via `batchUpdate` with `updateFormInfo`.
- **Custom `itemId` on sections**: The Forms API does honor client-supplied `itemId` in `createItem` requests, enabling stable section IDs for branching references.

## Alternatives Considered

### Alternative 1: Full CRUD on questions/sections

**Description**: Include `update-question`, `delete-question`, `update-section`, `delete-section` commands.

**Pros**:
- Complete control over form structure
- Closer to full API coverage

**Cons**:
- Doubles the command count for a v1 launch
- Updating questions requires knowing the item index and question structure
- Delete operations are rarely needed by agents building new forms

**Why rejected**: Start with create-and-append workflow. Add mutation commands if demand emerges.

### Alternative 2: Include quiz features

**Description**: Support quiz mode (auto-grading, correct answers, point values).

**Pros**:
- The Forms API supports quizzes natively
- Educational use cases

**Cons**:
- Significant additional complexity (grading, feedback per answer)
- Niche use case for agent workflows

**Why rejected**: Out of scope for v1. Can be added later without breaking changes.

### Alternative 3: Skip branching support

**Description**: Only support linear forms — no `--goto` or `--id` flags.

**Pros**:
- Simpler implementation and CLI surface

**Cons**:
- Branching is core to useful forms (e.g., "If yes, go to section X")
- Without it, agents would need raw API access for non-trivial forms

**Why rejected**: Branching is what makes forms useful beyond simple lists of questions. The implementation cost is modest.

## Consequences

### Positive

- Desk covers all six core Workspace services agents commonly need
- Agents can create surveys, collect responses, and build multi-path forms
- Follows all existing patterns — no new concepts for users to learn

### Negative

- Two new OAuth scopes require re-authentication for existing users
  - *Mitigation*: `desk auth login` handles this; clear messaging in release notes
- Responses command doesn't paginate (single page only)
  - *Mitigation*: Documented as a known limitation; adequate for most forms

### Neutral

- Form editing (update/delete questions) is not yet supported — agents must create forms from scratch

## Implementation Notes

- Service client: `src/desk/services/forms.py`
- Commands: `src/desk/commands/forms.py`
- Scopes added to `src/desk/config.py`
- Registered in `src/desk/cli.py`
- Error code `FORM_NOT_FOUND` added to `src/desk/agent.py`

## References

- [Google Forms API v1 documentation](https://developers.google.com/workspace/forms/api/reference/rest/v1)
- [Idea 039: Google Forms Support](../ideas/039-google-forms-support.md)
- ADR-004: Agent-First CLI Design (all commands follow agent-first patterns)
