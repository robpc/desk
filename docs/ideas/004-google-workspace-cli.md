---
id: 004
title: Google Workspace CLI Expansion
status: implemented
effort: L
value: Leverage shared auth/patterns for Docs, Drive, and other Google APIs
created: 2025-02-06
updated: 2026-02-06
adr: docs/decisions/003-unified-workspace-cli.md
---

# Idea 004: Google Workspace CLI Expansion

## Problem

The patterns established in gmail-cli (OAuth flow, user-owned credentials, Unix philosophy, Click-based CLI) could apply to other Google Workspace APIs. Users who already have gmail-cli configured could easily add Docs, Drive, or other services with minimal setup friction.

## Sketch

Two possible approaches:

### Option A: Unified Workspace CLI
Evolve into `gw` (Google Workspace CLI) with subcommands:
```bash
gw gmail search "is:unread"
gw docs read <doc-id>
gw drive list
gw auth add-scope docs  # Add new API access to existing auth
```

### Option B: Separate CLIs with Shared Auth
Keep separate tools that share the auth/config layer:
```bash
gmail search "is:unread"
gdocs read <doc-id>
gdrive list
# All share ~/.google-cli/token.json
```

### Google Docs CLI - Rough Commands
```bash
gdocs list                    # List recent docs
gdocs read <doc-id>           # Output doc as markdown/text
gdocs create "Title"          # Create new doc
gdocs append <doc-id> "text"  # Append content
gdocs export <doc-id> pdf     # Export to format
```

## Open Questions

- [x] Same repo or separate repos? **Same repo — unified CLI.**
- [x] Unified CLI (`gw`) vs separate tools with shared auth? **Unified, named `desk` (see ADR-003).**
- [x] How to render rich doc content to terminal? **Plain text via Docs API export.**
- [x] Docs API uses batch requests for edits - how to expose this simply? **append/prepend/replace modes.**
- [x] Which Workspace APIs have enough CLI utility? **All of them: Mail, Drive, Sheets, Docs, Calendar.**

## Resolution

**Implemented in PR #2** (`feature/desk-workspace-cli`). Went with Option A (unified CLI) but named it `desk` instead of `gw` — see ADR-003 for the naming rationale. All five services are live with full CRUD commands plus a cross-service `desk brief` command.

## Value Signal

Natural extension of existing work. Shared OAuth setup is compelling - authenticate once, use multiple tools.

## Effort Guess

L - Docs API is more complex than Gmail. Document structure (paragraphs, tables, images) requires thoughtful output formatting. Batch request model for writes is different from Gmail's simpler approach. However, significant code can be reused from gmail-cli.

## Notes

- Could start with read-only Docs CLI to validate patterns before tackling writes
- Drive CLI might be simpler starting point than Docs (file operations vs document structure)
- Calendar CLI could be high-value for automation use cases
- `google-api-python-client` supports all these APIs with same auth flow
