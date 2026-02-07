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
| 003 | [Label Management](003-label-management.md) | partial | S | Complete label workflow without leaving CLI |
| 005 | [Send Command](005-send-command.md) | implemented | M | Complete read/write cycle |
| 006 | [Reply and Forward](006-reply-forward.md) | implemented | M | Respond to emails without leaving CLI |
| 007 | [Drafts Management](007-drafts.md) | implemented | M | Compose now, review/send later |
| 008 | [Attachment Handling](008-attachments.md) | implemented | M | Download and process attachments |
| 009 | [Mark Unread Command](009-mark-unread.md) | implemented | S | Complete symmetry with mark-read |
| 011 | [Dry Run Mode](011-dry-run.md) | implemented | S | Preview actions without executing |

## Adding an Idea

1. Copy `_template.md` to `NNN-short-title.md`
2. Fill in Problem and Sketch at minimum
3. Update this README's index
4. Don't over-plan - it's just an idea
