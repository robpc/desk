# CLAUDE.md

Guidance for Claude Code when working on Gmail CLI.

## Project Overview

**Gmail CLI** (`gmail`) is a command-line tool for managing Gmail. Unix philosophy: simple commands that compose with pipes. Each user brings their own Google Cloud OAuth credentials.

## Quick Start

```bash
# Setup (one-time)
pip install -e .
gmail auth login

# Usage
gmail search "from:boss is:unread"
gmail read <message-id>
gmail send --to "user@example.com" --subject "Hello" --body "..."
gmail label <message-id> work
```

## Architecture

```
gmail (CLI entry point)
├── auth login     → OAuth flow, stores tokens
├── auth status    → Show current auth state
├── search         → List messages matching query
├── read           → Display message content
├── send           → Compose and send
├── label          → Add/remove labels
├── archive        → Archive messages
└── labels         → List available labels

Config/Tokens: ~/.gmail-cli/
├── credentials.json  ← User provides (from their Google Cloud project)
└── token.json        ← Generated during auth, contains refresh token
```

## Key Files

- `src/gm/cli.py` - CLI entry point and command routing
- `src/gm/auth.py` - OAuth flow and token management
- `src/gm/gmail.py` - Gmail API wrapper
- `src/gm/config.py` - Configuration and paths
- `src/gm/commands/` - Individual command implementations

## Documentation System (ADRs + Ideas)

This project uses two complementary documentation systems. **Agents MUST engage with these as part of their workflow.**

### ADRs (Architecture Decision Records) - `docs/decisions/`

**What**: Documents decisions that have been made and why.

**Agent workflow**:
1. **Before implementing**: Read relevant ADRs to understand existing decisions
2. **Before changing architecture**: Check if an ADR covers this area
3. **When making significant choices**: Create a new ADR documenting alternatives considered
4. **Never contradict an ADR** without explicitly superseding it

**Create an ADR when**:
- Adding a major feature or command
- Changing authentication approach
- Choosing between libraries/frameworks
- Reversing or modifying a previous decision

### Ideas Log - `docs/ideas/`

**What**: Lightweight captures of potential future work - not commitments.

**Agent workflow**:
1. **When user mentions a future idea**: Capture it in the Ideas Log
2. **Before implementing a feature**: Check if an idea exists (may have context)
3. **When discovering related work**: Update existing ideas with notes
4. **When scoping creeps**: Suggest capturing as an idea instead of implementing

**Idea → Implementation flow**:
```
idea → exploring → planned → create ADR → implement
```

### Quick Reference

| Situation | Action |
|-----------|--------|
| User asks for new command | Check Ideas Log, then implement or create idea |
| Significant design choice | Create ADR with alternatives |
| "We should also do X" | Capture in Ideas Log, stay focused |
| Confused why something works this way | Read ADRs |
| Feature request that's out of scope | Add to Ideas Log, explain it's captured |

## Agent Verification Infrastructure

**Core principle**: Build verification capabilities into the tool so agents can self-verify before asking users to test.

### Verification tools to build/use:
- **`--verbose` flag**: Show API calls, token refreshes, etc.
- **`--dry-run` flag**: Show what would happen without executing
- **`--json` output**: Machine-readable output for chaining
- **`gmail auth status`**: Verify authentication state
- **Debug logging**: `GM_DEBUG=1 gmail search ...`

### Agent workflow:
1. **Before asking user to test**: Check if there's a verification tool available
2. **If no tool exists**: Consider whether building one is worthwhile
3. **When building new commands**: Include `--verbose` and `--json` as standard
4. **Use the tool yourself**: Run commands to verify behavior before declaring done

### Examples:
- Auth issues → Check `gmail auth status` output
- API errors → Use `--verbose` to see request/response
- Output formatting → Use `--json` and pipe through `jq`

## Design Principles

### Unix Philosophy
- Each command does one thing well
- Text streams for input/output
- Commands compose with pipes
- `--json` for structured output when needed

### Self-Documenting CLI
- `gmail --help` shows all commands
- `gmail <command> --help` shows command details
- Error messages include suggested fixes
- Examples in help text

### User-Owned Credentials
- Users create their own Google Cloud project
- Credentials stored in `~/.gmail-cli/credentials.json`
- Tokens stored in `~/.gmail-cli/token.json`
- No shared secrets, no server component

## Code Style

- Python 3.11+
- Type hints throughout
- `click` for CLI framework (pending ADR)
- `google-api-python-client` for Gmail API
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
