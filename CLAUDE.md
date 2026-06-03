# CLAUDE.md

Guidance for Claude Code when working on Desk.

## First-Run Check

Before doing anything else, verify desk is installed and working:

```bash
desk --version
```

If `desk` is not found or the command fails:
1. Check if `uv` is available: `uv --version`
2. Install desk: `uv tool install git+https://github.com/robpc/desk`
3. If `uv` is not available, install it first: `curl -LsSf https://astral.sh/uv/install.sh | sh`
4. Verify: `desk --version`

Do not proceed with any desk-related work until `desk --version` succeeds.

## Before You Write Any Code

Do these first. Not after. Not during. Before.

1. **Read `docs/ideas/`** — does an idea already exist for this work? It may have context, open questions, or prior decisions that affect your approach.
2. **Read `docs/decisions/`** — are there ADRs that constrain or inform what you're about to do? Never contradict an existing ADR without explicitly superseding it.
3. **If this involves a significant choice** (new command, new service, architecture change, naming, approach with multiple valid options) — **write an ADR before implementing**. Document what you chose, what you rejected, and why.
4. **If this graduates an idea** — update the idea's status to `adr-created` and link the ADR.

Skip this and you will ship incomplete work. The documentation is part of the deliverable.

## Project Overview

**Desk** (`desk`) is a command-line tool for Google Workspace — Gmail, Drive, Sheets, Docs, Calendar, and Forms. Unix philosophy: simple commands that compose with pipes. Each user brings their own Google Cloud OAuth credentials.

## Quick Start

```bash
# Install (one-time)
uv tool install git+https://github.com/robpc/desk

# Setup (one-time)
desk setup

# Usage
desk mail search "from:boss is:unread"
desk mail read <message-id>
desk drive recent --max 5
desk sheets read <spreadsheet-id>
desk docs read <document-id>
desk cal today
```

## Architecture

```
desk (CLI entry point)
├── setup              → Interactive auth setup
├── auth login         → OAuth flow, stores tokens
├── auth status        → Show current auth state
├── mail               → Gmail operations
│   ├── search         → List messages matching query
│   ├── threads        → Search for threads (conversations)
│   ├── thread         → Read entire thread
│   ├── thread-archive → Archive entire thread
│   ├── thread-label   → Add label to entire thread
│   ├── thread-trash   → Move entire thread to trash
│   ├── read           → Display message content
│   ├── send           → Send an email
│   ├── reply          → Reply to a message
│   ├── forward        → Forward a message
│   ├── drafts         → List drafts
│   ├── draft create   → Create a draft
│   ├── draft read     → Read a draft
│   ├── draft send     → Send a draft
│   ├── draft delete   → Delete a draft
│   ├── draft update   → Update a draft
│   ├── attachments    → List attachments
│   ├── attachment     → Download single attachment
│   ├── download-attachments → Download all attachments
│   ├── unread         → List unread messages
│   ├── labels         → List available labels
│   ├── create-label   → Create a new label (with optional color)
│   ├── delete-label   → Delete a label
│   ├── rename-label   → Rename a label
│   ├── label          → Add label to messages
│   ├── remove-label   → Remove label from messages
│   ├── archive        → Archive messages
│   ├── mark-read      → Mark messages as read
│   ├── mark-unread    → Mark messages as unread
│   ├── trash          → Move to trash
│   ├── star / unstar  → Star/unstar messages
│   └── modify         → Generic label changes
├── drive              → Google Drive operations
│   ├── search         → Search files
│   ├── read           → Read file content
│   ├── info           → File metadata
│   ├── recent         → Recently modified files
│   ├── upload         → Upload a local file
│   ├── download       → Download a file
│   ├── mkdir          → Create a folder
│   ├── move           → Move file to folder
│   ├── trash          → Move to trash
│   ├── share          → Share with someone
│   └── star / unstar  → Star/unstar files
├── sheets             → Google Sheets operations
│   ├── read           → Read spreadsheet data
│   ├── update-cell    → Update a cell value
│   ├── create         → Create a new spreadsheet
│   ├── write          → Write values to a range
│   ├── append         → Append rows
│   └── clear          → Clear a range
├── docs               → Google Docs operations
│   ├── create         → Create a new document
│   ├── read           → Read document content
│   ├── update         → Insert/replace text (includes find-and-replace)
│   ├── inspect        → Show document structure with indices
│   ├── insert         → Insert text at a specific index
│   ├── delete-range   → Delete content between indices
│   ├── style          → Apply text styling (bold, italic, code, etc.)
│   ├── paragraph-style → Apply paragraph styling (headings, alignment, spacing, indent)
│   ├── write-markdown → Write markdown with native Docs formatting
│   ├── insert-table   → Insert a table
│   ├── insert-image   → Insert an inline image
│   └── export         → Export as PDF/TXT/DOCX/HTML
├── forms              → Google Forms operations
│   ├── create         → Create a new form
│   ├── read           → Read form structure and questions
│   ├── responses      → List form responses (with pagination)
│   ├── add-question   → Add a question to a form
│   ├── add-section    → Add a section break to a form
│   ├── update         → Update form title/description
│   ├── update-question → Update a question's text, options, or required flag
│   ├── update-section → Update a section's title or description
│   ├── delete-item    → Delete a question or section
│   ├── publish        → Publish form and accept responses
│   └── unpublish      → Unpublish form (stops accepting)
├── cal                → Google Calendar operations
│   ├── today          → Today's events
│   ├── week           → This week's events
│   ├── next           → Upcoming events
│   ├── list           → List calendars
│   ├── create         → Create an event
│   ├── delete         → Delete an event
│   ├── update         → Update an event
│   └── find           → Search events by text
└── groups             → Google Groups / distribution list operations (read-only)
    ├── members        → List members of a group / distribution list
    ├── find           → Search/list groups
    └── get            → Group metadata

Config/Tokens: ~/.desk/
├── credentials.json  ← User provides (from their Google Cloud project)
└── token.json        ← Generated during auth, contains refresh token
```

## Key Files

- `src/desk/cli.py` - Root CLI group, setup, auth commands
- `src/desk/auth.py` - OAuth flow and token management
- `src/desk/config.py` - Configuration, paths, scopes
- `src/desk/commands/mail.py` - Gmail commands
- `src/desk/commands/drive.py` - Drive commands
- `src/desk/commands/sheets.py` - Sheets commands
- `src/desk/commands/docs.py` - Docs commands
- `src/desk/commands/cal.py` - Calendar commands
- `src/desk/commands/forms.py` - Forms commands
- `src/desk/services/gmail.py` - GmailClient API wrapper
- `src/desk/services/drive.py` - DriveClient API wrapper
- `src/desk/services/sheets.py` - SheetsClient API wrapper
- `src/desk/services/docs.py` - DocsClient API wrapper
- `src/desk/services/calendar.py` - CalendarClient API wrapper
- `src/desk/services/forms.py` - FormsClient API wrapper
- `src/desk/commands/groups.py` - Groups / distribution list commands (read-only)
- `src/desk/services/groups.py` - GroupsClient API wrapper (Admin SDK Directory)

## Adding a New Service

1. Create `src/desk/services/<name>.py` with a client class
2. Create `src/desk/commands/<name>.py` with Click commands in a group
3. Register the group in `src/desk/cli.py` via `main.add_command()`
4. Add scopes to `src/desk/config.py` if needed
5. Update this architecture diagram

## Documentation System (ADRs + Ideas)

This project uses ADRs and an Ideas Log. The pre-implementation checklist is at the top of this file. Below is reference for when to create new entries.

### ADRs — `docs/decisions/`

Decisions that have been made and why. Use the template at `docs/decisions/_template.md`.

**Create an ADR when**: adding a major feature or command, changing auth approach, choosing between libraries/frameworks, reversing a previous decision.

### Ideas Log — `docs/ideas/`

Lightweight captures of future work. Use the template at `docs/ideas/_template.md`.

**Lifecycle**: `idea → exploring → planned → adr-created → implement`

**Capture an idea when**: user mentions future work, scope creeps ("we should also..."), or you discover adjacent improvements during implementation. Stay focused on the current task.

### Quick Reference

| Situation | Action |
|-----------|--------|
| User asks for new command | Check Ideas Log first, then implement or create idea |
| Significant design choice | Write ADR before implementing |
| "We should also do X" | Capture in Ideas Log, stay focused |
| Confused why something works this way | Read ADRs |
| Feature request that's out of scope | Add to Ideas Log, explain it's captured |

## Agent Verification Infrastructure

**Core principle**: Build verification capabilities into the tool so agents can self-verify before asking users to test.

### Verification tools to build/use:
- **`--verbose` flag**: Show API calls, token refreshes, etc.
- **`--json` output**: Machine-readable output for chaining
- **`desk auth status`**: Verify authentication state
- **Debug logging**: `DESK_DEBUG=1 desk mail search ...`

### Agent workflow:
1. **Before asking user to test**: Check if there's a verification tool available
2. **If no tool exists**: Consider whether building one is worthwhile
3. **When building new commands**: Include `--json` as standard
4. **Use the tool yourself**: Run commands to verify behavior before declaring done

## Design Principles

### Toolkit, Not Productivity App

Desk is a toolkit for agents, not a pre-built productivity app. See ADR-003.

**Do NOT add**:
- Commands that compose multiple services (e.g., "morning brief" combining calendar + email)
- Commands that encode opinions about user workflows
- Commands with invented vocabulary not from the underlying services

**Why**: Agents should compose their own workflows from primitives, tailored to each user's needs. If we pre-build workflows, agents will use them instead of thoughtfully composing better, personalized solutions.

**The principle**: Desk provides the vocabulary (service operations). Agents write the sentences (workflows).

### No Invented Vocabulary (ADR-002)

Commands should map to concepts the services themselves expose:
- `desk cal today` → Calendar's "Day" view (Google's vocabulary)
- `desk mail unread` → Gmail's "is:unread" (Google's vocabulary)
- ~~`desk brief`~~ → "Brief" is our invention, not Google's

### Unix Philosophy
- Each command does one thing well
- Text streams for input/output
- Commands compose with pipes
- `--json` for structured output when needed

### Self-Documenting CLI
- `desk --help` shows all command groups
- `desk <group> --help` shows group commands
- `desk <group> <command> --help` shows command details
- Error messages include suggested fixes

### User-Owned Credentials
- Users create their own Google Cloud project
- Credentials stored in `~/.desk/credentials.json`
- Tokens stored in `~/.desk/token.json`
- No shared secrets, no server component

## Code Style

- Python 3.10+
- Type hints throughout
- `click` for CLI framework
- `google-api-python-client` for Google APIs
- `rich` for terminal output
- Minimal dependencies

## Development

```bash
# Install in dev mode
pip install -e ".[dev]"

# Run tests
pytest

# Run linter
ruff check src/

# Format
ruff format src/
```
