---
id: 004
title: Agent-First CLI Design
status: accepted
date: 2025-02-07
supersedes: []
superseded_by: null
tags: [cli, agents, architecture, differentiation]
---

# ADR-004: Agent-First CLI Design

## Context

A competitive analysis revealed [gogcli](https://github.com/steipete/gogcli), a mature Go-based Google Workspace CLI with more services, better auth security, and enterprise features. Desk's stated design principles ("toolkit not app", "no invented vocabulary") don't create meaningful differentiation — gogcli follows the same principles implicitly.

The question became: **why should Desk exist?**

After analysis, we identified that while gogcli optimizes for human scripting, no major CLI tool optimizes specifically for **LLM agents as first-class users**. As agents increasingly become primary consumers of CLI tools, this is a meaningful gap.

Agents struggle with CLIs in specific ways:
- **Parsing output**: Human-readable text is ambiguous; agents guess at structure
- **Understanding errors**: "Message not found" doesn't tell an agent what to do next
- **Missing context**: After a command, what actions are available? Humans infer, agents don't
- **Round-trip cost**: Each CLI call = latency + tokens to process output
- **Destructive mistakes**: Agents can hallucinate IDs or misunderstand intent
- **Discoverability**: `--help` is prose for humans, not structured for LLMs

## Decision

Desk will be an **agent-first CLI**. Every feature will be designed with LLM agents as the primary user, while remaining usable by humans.

We will implement the following capabilities:

### 1. Structured Errors with Suggestions

All errors return JSON with:
- Machine-readable error code
- Human-readable message
- Actionable suggestions for recovery
- Whether the operation is retryable

```json
{
  "success": false,
  "error": {
    "code": "MESSAGE_NOT_FOUND",
    "message": "Message with ID abc123 not found",
    "suggestions": [
      "Run `desk mail search` to find valid message IDs",
      "The message may have been deleted or is in trash"
    ],
    "retryable": false
  }
}
```

### 2. Operation Receipts

Every mutating command returns a receipt confirming what happened:

```json
{
  "success": true,
  "operation": "archive",
  "target": {"id": "abc123", "subject": "Q4 Report"},
  "timestamp": "2025-02-07T10:30:00Z",
  "undo_command": "desk mail unarchive abc123",
  "undo_expires": "30 days"
}
```

### 3. Dry-Run Mode

Destructive and mutating commands support `--dry-run`:

```bash
$ desk mail trash abc123 --dry-run
```
```json
{
  "would_execute": "trash",
  "target": {
    "id": "abc123",
    "subject": "Quarterly Report",
    "from": "boss@company.com"
  },
  "reversible": true
}
```

### 4. Batch Operations

Commands that operate on items accept multiple IDs:

```bash
desk mail archive id1 id2 id3 id4 id5
```

And support stdin for large batches:

```bash
desk mail search "is:unread older_than:30d" --ids-only | desk mail archive --stdin
```

### 5. Context-Rich Output

The `--context` flag adds metadata about what actions are available next:

```json
{
  "results": [...],
  "context": {
    "total_matching": 47,
    "returned": 10,
    "has_more": true,
    "next_page_token": "xyz789",
    "available_actions": [
      {"command": "desk mail read <id>", "description": "Read message content"},
      {"command": "desk mail search --page-token xyz789", "description": "Get next page"}
    ]
  }
}
```

### 6. Capabilities Endpoint

A machine-readable schema of what Desk can do:

```bash
$ desk --capabilities
```
```json
{
  "version": "0.1.0",
  "services": {
    "mail": {
      "commands": ["search", "read", "send", "archive", "trash"],
      "batch_supported": ["archive", "trash", "label", "mark-read"],
      "dry_run_supported": ["send", "trash"],
      "destructive": ["send", "trash"]
    }
  }
}
```

### 7. Idempotency Keys

For operations agents might retry:

```bash
desk mail send --to bob@x.com --subject "Update" --body "..." \
  --idempotency-key "agent-task-abc123"
```

If retried, the second call is a safe no-op returning the original result.

## Alternatives Considered

### Alternative 1: Archive Desk, Recommend gogcli

**Description**: Stop development, document gogcli as the recommended tool.

**Pros**:
- No wasted effort on a redundant tool
- gogcli is mature and well-maintained
- Honest about competitive landscape

**Cons**:
- Abandons the Python ecosystem play
- Misses the agent-first opportunity
- No differentiated offering

**Why rejected**: There's a real gap in the market for agent-optimized CLI tools. This is worth pursuing.

### Alternative 2: Python Library Focus

**Description**: Pivot to being a Python library (`import desk`) rather than a CLI.

**Pros**:
- Clear differentiation from gogcli (Go can't serve Python devs)
- Useful for agent frameworks like LangChain
- Lower surface area to maintain

**Cons**:
- Different product entirely
- CLI is still valuable for ad-hoc use
- Would need to maintain both anyway

**Why rejected**: Not mutually exclusive. We can do both, but CLI agent-first features are the differentiator.

### Alternative 3: Feature Parity Race with gogcli

**Description**: Add all the services gogcli has (Chat, Tasks, Contacts, etc.).

**Pros**:
- Complete coverage
- No gaps for users

**Cons**:
- Permanent catch-up game
- gogcli has head start and more contributors
- Features without differentiation

**Why rejected**: Can't win on coverage. Differentiation must come from *how* we do things, not *what* we cover.

## Consequences

### Positive

- Clear product differentiation from gogcli and other Workspace CLIs
- Positioned for the agentic future — as agents become primary CLI users, Desk is ready
- Features benefit human users too (better errors, dry-run, receipts)
- Measurable — can track agent adoption and success rates
- Python ecosystem advantage preserved while adding unique value

### Negative

- More work per command — each must support structured errors, receipts, dry-run, batch
  - *Mitigation*: Build framework/decorators that make this easy
- `--json` output becomes more verbose
  - *Mitigation*: Human-readable output remains the default; JSON is opt-in
- May over-optimize for theoretical agent use cases
  - *Mitigation*: Validate with real agent usage; iterate based on feedback

### Neutral

- Still fewer services than gogcli — but now intentionally focused, not just behind
- Human users may not notice the difference (that's fine; they're not the primary audience)

## Implementation Notes

**Phased rollout**:

1. **Phase 1**: Add `--dry-run` to destructive commands (trash, send)
2. **Phase 2**: Implement structured error responses with suggestions
3. **Phase 3**: Add operation receipts to all mutating commands
4. **Phase 4**: Add batch support to high-frequency operations
5. **Phase 5**: Implement `--context` flag and `--capabilities` endpoint
6. **Phase 6**: Add idempotency keys for critical operations (send)

**Framework support**:

Create decorators/utilities that make agent-first patterns easy:
- `@with_dry_run` — adds dry-run support to a command
- `@with_receipt` — wraps output in operation receipt
- `@batch_enabled` — accepts multiple IDs or stdin
- `structured_error()` — consistent error formatting

**Key files to create/modify**:
- `src/desk/agent.py` — Agent-first utilities and decorators
- `src/desk/errors.py` — Structured error types
- `src/desk/receipts.py` — Operation receipt generation
- All command files — Apply decorators incrementally

## References

- [Idea 027: Competitive Analysis — gogcli](../ideas/027-competitive-analysis-gogcli.md)
- [gogcli GitHub](https://github.com/steipete/gogcli)
- ADR-003: Unified Workspace CLI (establishes "toolkit, not app" principle)
- ADR-002: No Invented Vocabulary (still applies — agent features use Google's vocabulary)
