---
id: 003
title: Unified Workspace CLI ("Desk") over Separate Tools
status: accepted
date: 2026-02-06
supersedes: []
superseded_by: null
tags: [cli, architecture, naming]
---

# ADR-003: Unified Workspace CLI ("Desk") over Separate Tools

## Context

Idea 004 identified that the patterns from gmail-cli (OAuth, Click CLI, Unix philosophy) could extend to other Google Workspace APIs. The question was whether to build a single unified CLI or keep separate tools with shared auth.

Once we started adding Drive, Sheets, Docs, and Calendar, the scope made the `gmail-cli` name misleading. We needed both a new architecture (how commands are organized) and a new name.

Forces at play:
- Shared OAuth credentials — users authenticate once for all Google APIs
- Shared patterns — every service uses the same `--json`, `--max`, pipes model
- CLI discoverability — `desk --help` shows everything available
- Some commands cross service boundaries (e.g., `brief` uses both Calendar and Gmail)
- Name should be short, typeable, and not collide with existing tools

## Decision

We will use a **unified CLI with service subgroups**, named `desk`.

Structure:
```
desk brief              → Cross-service (calendar + gmail)
desk mail search ...    → Gmail
desk drive search ...   → Google Drive
desk sheets read ...    → Google Sheets
desk docs read ...      → Google Docs
desk cal today          → Google Calendar
```

The name "desk" was chosen because:
- Short (4 chars) and easy to type
- Evokes "the stuff on your desk" — email, calendar, files, docs
- Generic enough to grow into (could add Slack, Jira, etc. later)
- Doesn't collide with common CLI tools or shell aliases

## Alternatives Considered

### Alternative 1: Separate CLIs with Shared Auth (`gmail`, `gdocs`, `gdrive`)

**Description**: Keep each service as its own CLI tool, sharing `~/.desk/` for auth.

**Pros**:
- Each tool is small and focused
- Install only what you need
- Follows Unix "one tool, one job" more literally

**Cons**:
- Cross-service commands (like `brief`) don't have a natural home
- More binaries to manage and install
- Harder to discover what's available
- Shared auth config is an invisible coupling

**Why rejected**: The shared auth already couples them. Making it explicit with one CLI is cleaner than pretending they're independent.

### Alternative 2: Name it `gw` (Google Workspace)

**Description**: Use `gw` as the command name.

**Pros**:
- Only 2 chars
- Clear what it stands for

**Cons**:
- Could collide with other tools (Go workspace, git-worktree aliases)
- Feels very "Google" — limits future expansion
- Not immediately obvious what it means

**Why rejected**: Collision risk and too tied to Google branding.

### Alternative 3: Name it `workspace` or `work`

**Description**: Use a longer, more descriptive name.

**Pros**:
- Self-documenting

**Cons**:
- `workspace` is 9 chars — too long to type constantly
- `work` is aggressive as a name for what's really a utility tool
- Both are common words that could conflict

**Why rejected**: Too long or too generic for a command you type dozens of times a day.

## Consequences

### Positive

- Single entry point for all Google Workspace operations
- Cross-service commands (`brief`) have a natural home at the top level
- One auth setup covers everything
- `desk --help` is a complete reference
- Name has room to grow beyond Google services

### Negative

- Larger CLI surface area — more to learn
  - *Mitigation*: Service groups scope discovery (`desk mail --help` vs `desk cal --help`)
- Package rename from `gmail-cli` requires reinstall
  - *Mitigation*: One-time migration, documented in README
- "desk" isn't immediately self-explanatory
  - *Mitigation*: Subcommand names (`mail`, `cal`, `drive`) provide context

### Neutral

- Old `gmail` command no longer exists — users must switch to `desk mail`
- Config directory stays at `~/.desk/` (already migrated from `~/.gmail-cli/`)

## Implementation Notes

**Key files**:
- `src/desk/cli.py` — Root CLI group, registers all subcommands
- `src/desk/commands/*.py` — One file per service group, plus `brief.py` for cross-service
- `src/desk/services/*.py` — API client wrappers

**Migration from gmail-cli**:
- `gmail search` → `desk mail search`
- `gmail auth status` → `desk auth status`
- Config auto-migrates from `~/.gmail-cli/` to `~/.desk/`

**Cross-service pattern**:
`brief` is the first command that uses multiple service clients. It establishes the pattern: top-level commands (not in a group) can import from multiple services.

## References

- Idea 004: Google Workspace CLI Expansion
- Original gmail-cli conversation (Rob + Claude, 2026-02-06)
