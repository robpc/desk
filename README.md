# Desk

Google Workspace from the command line — Gmail, Drive, Sheets, Docs, Calendar, and Forms. Unix philosophy: simple commands that compose with pipes.

## Quick Start

```bash
uv tool install git+https://github.com/robpc/desk
desk setup
desk mail search "is:unread"
```

## Installation

### Recommended: uv (fastest)

```bash
uv tool install git+https://github.com/robpc/desk
```

### Alternative: pipx

```bash
pipx install git+https://github.com/robpc/desk
```

### Alternative: pip + venv

```bash
python3 -m venv ~/.local/share/desk-venv
~/.local/share/desk-venv/bin/pip install git+https://github.com/robpc/desk
mkdir -p ~/.local/bin
ln -sf ~/.local/share/desk-venv/bin/desk ~/.local/bin/desk
```

### Don't have Python?

Install [uv](https://docs.astral.sh/uv/) — it manages Python for you:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv tool install git+https://github.com/robpc/desk
```

### Troubleshooting

**`externally-managed-environment` error**: Your system Python is managed by Homebrew (or similar). Use uv or pipx instead of `pip install` directly.

**`desk: command not found` after install**: `~/.local/bin` may not be on your PATH. Add it:

```bash
# zsh (macOS default)
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc && source ~/.zshrc

# bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc && source ~/.bashrc
```

## Setup

### Quick (gcloud users)

If you have `gcloud` installed and authenticated:

```bash
desk setup --gcloud
```

### Standard (team credentials)

Get `credentials.json` from your team (e.g., 1Password vault):

```bash
desk setup --credentials ~/Downloads/credentials.json
```

### From scratch (create your own)

This takes about 10 minutes the first time.

1. Go to [Google Cloud Console](https://console.cloud.google.com/) and create a project
2. Go to **APIs & Services** → **Library** and enable: **Gmail API**, **Google Drive API**, **Google Sheets API**, **Google Docs API**, **Google Calendar API**, **Google Forms API**
3. Go to **APIs & Services** → **Credentials** → **Create Credentials** → **OAuth client ID**
4. If prompted, configure the OAuth consent screen (User type: External, App name: "Desk")
5. Application type: **Desktop app**, Name: "Desk", click **Create**
6. Download the JSON file, then:

```bash
mkdir -p ~/.desk
mv ~/Downloads/client_secret_*.json ~/.desk/credentials.json
desk auth login
```

## Usage

### Discovering commands

```bash
desk --help                    # All command groups
desk mail --help               # All mail commands
desk mail search --help        # Detailed help for a command
```

### Mail (Gmail)

```bash
desk mail search "from:boss" --max 10    # Search messages
desk mail unread                         # Unread messages
desk mail read <id>                      # Read a message
desk mail threads "from:boss"            # Search by thread
desk mail thread <thread-id>             # Read entire conversation
desk mail send --to "user@example.com" --subject "Hello" --body "Message"
desk mail reply <id> --body "Thanks!"
desk mail forward <id> --to "colleague@example.com" --body "FYI"
desk mail drafts                         # List drafts
desk mail labels                         # List labels
desk mail archive <id>...                # Archive messages
desk mail trash <id>...                  # Move to trash
desk mail star <id>...                   # Star messages
desk mail label <label> <id>...          # Add a label
desk mail attachments <id>               # List attachments
desk mail download-attachments <id> --output-dir ./files/
```

### Drive

```bash
desk drive search "name contains 'report'"   # Search files
desk drive recent --max 10                    # Recently modified files
desk drive read <file-id>                     # Read file content
desk drive info <file-id>                     # File metadata
desk drive upload report.pdf                  # Upload a file
desk drive download <file-id>                 # Download a file
desk drive mkdir "Project Files"              # Create a folder
desk drive move <file-id> <folder-id>         # Move file to folder
desk drive trash <file-id>                    # Move to trash
desk drive share <file-id> bob@co.com         # Share with someone
```

### Sheets

```bash
desk sheets read <spreadsheet-id>                    # Read entire first sheet
desk sheets read <id> --range "Sheet1!A1:C10"        # Read specific range
desk sheets update-cell <id> "Sheet1!A1" "New value" # Update a cell
desk sheets create "Q1 Budget"                       # Create spreadsheet
desk sheets write <id> "Sheet1!A1:B2" '[["A","B"],["1","2"]]'
desk sheets append <id> "Sheet1!A:Z" '[["Alice","30"]]'
desk sheets clear <id> "Sheet1!A1:C10"               # Clear a range
```

### Docs

```bash
desk docs create "Meeting Notes"                 # Create a doc
desk docs read <document-id>                     # Read document
desk docs update <id> "Appended text"            # Append text
desk docs update <id> "New" --mode replace       # Replace all content
desk docs export <id> report.pdf                 # Export as PDF
desk docs export <id> notes.txt --format txt     # Export as text
```

### Calendar

```bash
desk cal today                    # Today's events
desk cal week                     # This week's events
desk cal next --max 5             # Upcoming events
desk cal list                     # List calendars
desk cal find "standup"           # Search events
desk cal create "Meeting" --start 2024-01-15T10:00:00 --end 2024-01-15T11:00:00
desk cal update <event-id> --summary "New Title"
desk cal delete <event-id>
```

### Forms

```bash
desk forms create "Survey"                       # Create a form
desk forms read <form-id>                        # Read form structure
desk forms responses <form-id>                   # List responses
desk forms add-question <form-id> "Your name?" --type short-answer
desk forms add-section <form-id> "Part 2"        # Add a section
```

### Batch Operations

```bash
desk mail archive ID1 ID2 ID3                                                    # Multiple IDs
desk mail search "from:notifications" --json | jq -r '.[].id' | desk mail archive --stdin  # Pipe
desk mail modify ID1 ID2 --remove-label INBOX --remove-label UNREAD              # Combine
```

### Output Formats

All commands support `--json` for machine-readable output:

```bash
desk mail search "is:unread" --json
desk drive recent --json
desk cal today --json
```

## Migrating from gmail-cli

If you previously used `gmail`, Desk will auto-migrate your config from `~/.gmail-cli/` to `~/.desk/` on first run. You'll need to re-authenticate to grant the expanded scopes (Drive, Sheets, Docs, Calendar).

## Development

```bash
git clone https://github.com/robpc/desk
cd desk
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Run tests
pytest

# Lint
ruff check src/
```

## License

Copyright 2026 Robert Cannon

Licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE) for the full text.
