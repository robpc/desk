---
id: 032
title: Context Flag and Capabilities Endpoint
status: implemented
effort: M
value: Agents know what actions are available and can plan accordingly
created: 2025-02-07
updated: 2025-02-07
adr: 004-agent-first-cli.md
---

# Idea 032: Context Flag and Capabilities Endpoint

## Problem

After running a command, agents don't know what they can do next. After a search, the agent has to guess that it can `read`, `archive`, or `trash` the results. This leads to hallucinated commands or missed opportunities.

Also, agents have no way to introspect Desk's capabilities — what commands exist, which support batch, which are destructive.

## Sketch

### Part 1: `--context` Flag

Add `--context` to all commands. It includes metadata about available next actions:

```bash
$ desk mail search "from:boss" --json --context
```

```json
{
  "results": [
    {"id": "abc123", "subject": "Q4 Report", ...},
    {"id": "def456", "subject": "Budget Review", ...}
  ],
  "context": {
    "result_type": "messages",
    "total_matching": 47,
    "returned": 10,
    "has_more": true,
    "pagination": {
      "next_page_token": "xyz789",
      "next_command": "desk mail search \"from:boss\" --page-token xyz789"
    },
    "available_actions": [
      {
        "action": "read",
        "command": "desk mail read <id>",
        "description": "Read full message content"
      },
      {
        "action": "archive",
        "command": "desk mail archive <id> [<id>...]",
        "description": "Remove from inbox",
        "batch_supported": true
      },
      {
        "action": "reply",
        "command": "desk mail reply <id> --body \"...\"",
        "description": "Reply to message"
      }
    ]
  }
}
```

### Part 2: `--capabilities` Endpoint

A schema of everything Desk can do:

```bash
$ desk --capabilities
```

```json
{
  "version": "0.2.0",
  "services": {
    "mail": {
      "description": "Gmail operations",
      "commands": {
        "search": {
          "description": "Search messages",
          "arguments": ["query"],
          "flags": ["--max", "--json", "--context", "--page-token"],
          "returns": "messages"
        },
        "archive": {
          "description": "Archive messages (remove from inbox)",
          "arguments": ["message_ids"],
          "flags": ["--stdin", "--dry-run", "--json"],
          "batch_supported": true,
          "destructive": false,
          "reversible": true,
          "undo_command": "unarchive"
        },
        "send": {
          "description": "Send an email",
          "flags": ["--to", "--subject", "--body", "--cc", "--bcc", "--dry-run"],
          "destructive": true,
          "reversible": false
        }
      }
    },
    "drive": { ... },
    "cal": { ... }
  }
}
```

### Human-Readable Capabilities

```bash
$ desk --capabilities --human
```

```
Desk v0.2.0 — Google Workspace CLI

Services:
  mail   Gmail operations
  drive  Google Drive operations
  cal    Google Calendar operations
  ...

Mail Commands:
  search    Search messages               [batch: no]  [reversible: n/a]
  read      Read message content          [batch: no]  [reversible: n/a]
  archive   Archive messages              [batch: yes] [reversible: yes]
  trash     Move to trash                 [batch: yes] [reversible: 30d]
  send      Send email                    [batch: no]  [reversible: no] ⚠️

Use `desk <service> <command> --help` for details.
```

## Open Questions

- [ ] Should `--context` be opt-in (explicit flag) or opt-out (always included with `--json`)?
- [ ] How detailed should capabilities be? (Full argument schemas vs. high-level)
- [ ] Should capabilities include examples?
- [ ] Cache capabilities or generate dynamically?

## Value Signal

This is how agents move from "guess and check" to "plan and execute." An agent with capabilities can:
- Know what Desk can do without documentation
- Plan multi-step workflows
- Avoid commands that don't exist
- Prefer batch operations when available

## Effort Guess

M - Need to define schema, annotate all commands with metadata, build the introspection system. Not technically hard but touches every command.

## Notes

Depends on: Idea 028 (Agent-First Framework)

The capabilities endpoint is inspired by OpenAPI/JSON Schema — a machine-readable contract for what's available.

Related: ADR-004
