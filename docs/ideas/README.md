# Ideas Log

Lightweight captures of potential future work. Not commitments - just a place to capture context so good ideas don't get lost.

## Purpose

- Prevent scope creep by parking "while we're at it" ideas
- Preserve context for future implementation
- Help prioritize by seeing all options in one place

## Idea Lifecycle

```
idea → exploring → planned → adr-created → (implemented)
       ↓
     parked / rejected
```

- **idea**: Just captured, not evaluated
- **exploring**: Actively researching feasibility
- **planned**: Will implement, needs ADR
- **adr-created**: ADR written, ready for implementation
- **parked**: Good idea, not now
- **rejected**: Evaluated and decided against

## Index

| ID | Title | Status | Effort | Value |
|----|-------|--------|--------|-------|
| 001 | [Convenience Commands](001-convenience-commands.md) | implemented | S | QoL shortcuts |
| 002 | [Batch Operations](002-batch-operations.md) | implemented | M | Bulk efficiency |
| 003 | [Label Management](003-label-management.md) | implemented | S | Complete label workflow without leaving CLI |
| 005 | [Send Command](005-send-command.md) | implemented | M | Complete read/write cycle |
| 006 | [Reply and Forward](006-reply-forward.md) | implemented | M | Respond to emails without leaving CLI |
| 007 | [Drafts Management](007-drafts.md) | implemented | M | Compose now, review/send later |
| 008 | [Attachment Handling](008-attachments.md) | implemented | M | Download and process attachments |
| 009 | [Mark Unread Command](009-mark-unread.md) | implemented | S | Complete symmetry with mark-read |
| 010 | [Thread Support](010-threads.md) | implemented | M | Work with email conversations |
| 011 | [Dry Run Mode](011-dry-run.md) | implemented | S | Preview actions without executing |
| 013 | [Safety Confirmations](013-safety-confirmations.md) | implemented | M | Prevent accidental destructive actions |
| 014 | [Test Suite](014-test-suite.md) | implemented | L | Confidence in changes, prevent regressions |
| 035 | [Performance Optimization - Batch Fetch](035-performance-optimization.md) | implemented | M | 5-10x speedup for listing commands |
| 054 | [Slides Phase 1 — Content CRUD](054-slides-content-crud.md) | adr-created | M | Read, draft, and edit Slides decks |
| 055 | [Slides Phase 2 — Visual Elements](055-slides-visual-elements.md) | adr-created | M | Images, tables, shapes on slides |
| 056 | [Slides Phase 3 — Styling & Layout](056-slides-styling-layout.md) | adr-created | L | Text/element styling, backgrounds, layouts |
| 057 | [Slides Phase 4 — Outline-First Authoring](057-slides-outline-authoring.md) | questioned | L | Generate a deck from a markdown outline (ADR-003 concern) |
| 058 | [Bug — docs export supportsAllDrives](058-docs-export-supportsalldrives-bug.md) | idea | S | Fix probable latent crash in docs export |
| 059 | [Slides Speaker Notes](059-slides-speaker-notes.md) | idea | S | Set per-slide speaker notes (core deck gap) |
| 060 | [Scope-Mismatch Re-Auth UX](060-scope-mismatch-reauth-ux.md) | idea | S | Tell users to re-auth on new-scope 403s, not "request access" |
| 061 | [Slides Authoring Ergonomics](061-slides-authoring-ergonomics.md) | idea | M | Fewer round-trips per slide (11-slide build = ~30+ calls) |
| 062 | [add-slide emit placeholder ids](062-slides-add-slide-emit-placeholder-ids.md) | idea | S | Remove the mandatory inspect between add-slide and insert-text |
| 063 | [SECTION_HEADER tagline coverage](063-slides-section-header-placeholders.md) | idea | S | Likely docs: point to SECTION_TITLE_AND_DESCRIPTION |

## Adding an Idea

1. Copy `_template.md` to `NNN-short-title.md`
2. Fill in Problem and Sketch at minimum
3. Update this README's index
4. Don't over-plan - it's just an idea
