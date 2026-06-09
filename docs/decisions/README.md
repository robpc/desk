# Architecture Decision Records

This directory contains Architecture Decision Records (ADRs) for the Gmail CLI project.

## What is an ADR?

An ADR documents a significant architectural decision along with its context and consequences. They provide a record of what was decided, why, and what alternatives were considered.

## When to Create an ADR

- Adding a major feature or command
- Choosing between frameworks or libraries
- Changing authentication or security approach
- Any decision that would be hard to reverse
- When you find yourself explaining "why we did it this way" repeatedly

## ADR Lifecycle

```
proposed → accepted → [deprecated | superseded]
```

- **proposed**: Under discussion, not yet implemented
- **accepted**: Implemented and in use
- **deprecated**: No longer recommended, but still in code
- **superseded**: Replaced by a newer ADR

## Index

| ID | Title | Status | Date |
|----|-------|--------|------|
| 001 | [OAuth and Credential Strategy](001-oauth-credential-strategy.md) | accepted | 2025-02-06 |
| 002 | [Command Composability via Generic Modify](002-command-composability.md) | accepted | 2025-02-06 |
| 019 | [Errors to stderr](019-errors-to-stderr.md) | accepted | 2026-05-06 |
| 026 | [Google Slides Support](026-google-slides-support.md) | proposed | 2026-06-09 |
| 027 | [Slides Visual Elements (Phase 2)](027-slides-visual-elements.md) | proposed | 2026-06-09 |

## Creating a New ADR

1. Copy `_template.md` to `NNN-short-title.md`
2. Fill in all sections (don't skip Alternatives Considered)
3. Update this README's index
4. Get feedback before marking as accepted
