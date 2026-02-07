# Desk

Google Workspace from the command line — Gmail, Drive, Sheets, Docs, Calendar. Unix philosophy: simple commands that compose with pipes.

## Quick Start

```bash
# Install
pip install -e .

# Setup (choose one)
desk setup --gcloud                    # Easiest: use gcloud credentials
desk setup --credentials creds.json    # Team: use shared OAuth credentials

# Use it
desk mail search "from:boss is:unread"
desk mail read <message-id>
desk drive recent
desk cal today
```

## Setup

### Option A: gcloud (Simplest)

If you have `gcloud` installed and authenticated:

```bash
desk setup --gcloud
```

That's it. Uses your existing gcloud Application Default Credentials.

### Option B: Team Credentials

For teams sharing a Google Cloud project, get the `credentials.json` from your team (e.g., 1Password vault):

```bash
desk setup --credentials ~/Downloads/credentials.json
```

### Option C: Create Your Own Credentials

This takes about 10 minutes the first time.

#### 1. Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or use an existing one)

#### 2. Enable APIs

1. Go to **APIs & Services** → **Library**
2. Enable: **Gmail API**, **Google Drive API**, **Google Sheets API**, **Google Docs API**, **Google Calendar API**

#### 3. Create OAuth Credentials

1. Go to **APIs & Services** → **Credentials**
2. Click **Create Credentials** → **OAuth client ID**
3. If prompted, configure the OAuth consent screen:
   - User type: External (or Internal for Workspace)
   - App name: "Desk" (or whatever you like)
   - Scopes: Add Gmail, Drive, Sheets, Docs, Calendar scopes
4. Application type: **Desktop app**
5. Name: "Desk"
6. Click **Create**
7. Download the JSON file

#### 4. Install Credentials

```bash
mkdir -p ~/.desk
mv ~/Downloads/client_secret_*.json ~/.desk/credentials.json
```

#### 5. Authenticate

```bash
desk auth login
```

This opens your browser. Log in with your Google account and approve access. Done!

## Commands

### Brief

```bash
desk brief                   # Morning brief: today's calendar + unread emails
desk brief --json            # JSON output for piping to other tools
desk brief --max 10          # Limit unread messages shown
```

### Mail (Gmail)

```bash
desk mail search "query"                # Search messages (Gmail search syntax)
desk mail search "from:boss" --max 10
desk mail unread                        # Shortcut for search "is:unread"
desk mail read <id>                     # Read a message
desk mail labels                        # List available labels
desk mail archive <id>...               # Archive messages
desk mail trash <id>...                 # Move to trash
desk mail mark-read <id>...             # Mark as read
desk mail star <id>...                  # Star messages
desk mail label <label> <id>...         # Add a label
desk mail remove-label <label> <id>...  # Remove a label
desk mail modify <id>... -a Work -r INBOX  # Generic label changes
```

### Drive

```bash
desk drive search "name contains 'report'"   # Search files
desk drive recent --max 10                    # Recently modified files
desk drive read <file-id>                     # Read file content
desk drive info <file-id>                     # File metadata
desk drive upload report.pdf                  # Upload a file
desk drive upload data.csv --folder <id>      # Upload to specific folder
desk drive download <file-id>                 # Download to current dir
desk drive download <file-id> ~/Downloads/    # Download to path
desk drive mkdir "Project Files"              # Create a folder
desk drive move <file-id> <folder-id>         # Move file to folder
desk drive trash <file-id>                    # Move to trash
desk drive share <file-id> bob@co.com         # Share as writer
desk drive share <id> bob@co.com --role reader # Share as reader
desk drive star <file-id>                     # Star a file
desk drive unstar <file-id>                   # Unstar a file
```

### Sheets

```bash
desk sheets read <spreadsheet-id>                    # Read entire first sheet
desk sheets read <id> --range "Sheet1!A1:C10"        # Read specific range
desk sheets update-cell <id> "Sheet1!A1" "New value" # Update a cell
desk sheets create "Q1 Budget"                       # Create spreadsheet
desk sheets write <id> "Sheet1!A1:B2" '[["A","B"],["1","2"]]'  # Write range
desk sheets append <id> "Sheet1!A:Z" '[["Alice","30"]]'        # Append rows
desk sheets clear <id> "Sheet1!A1:C10"               # Clear a range
```

### Docs

```bash
desk docs create "Meeting Notes"                       # Create a doc
desk docs create "Draft" --body "Hello world"          # Create with content
desk docs read <document-id>                           # Read document
desk docs update <id> "Appended text"                  # Append text
desk docs update <id> "New text" --mode prepend        # Prepend text
desk docs update <id> "Replacement" --mode replace     # Replace all content
desk docs export <id> report.pdf                       # Export as PDF
desk docs export <id> notes.txt --format txt           # Export as text
```

### Calendar

```bash
desk cal today                    # Today's events
desk cal week                     # This week's events
desk cal next --max 5             # Next upcoming events
desk cal list                     # List all calendars
desk cal find "standup"           # Search events by text
desk cal create "Meeting" --start 2024-01-15T10:00:00 --end 2024-01-15T11:00:00
desk cal create "Sync" --start ... --end ... -a bob@co.com -a alice@co.com
desk cal update <event-id> --summary "New Title"
desk cal update <id> -a newperson@co.com
desk cal delete <event-id>
```

### Batch Operations (Mail)

```bash
# Multiple IDs
desk mail archive ID1 ID2 ID3

# Pipe from search
desk mail search "from:notifications" --json | jq -r '.[].id' | desk mail archive --stdin

# Combine operations with modify
desk mail modify ID1 ID2 --remove-label INBOX --remove-label UNREAD
```

### Auth

```bash
desk setup               # Interactive setup guide
desk setup --gcloud      # Use gcloud ADC (simplest)
desk setup --credentials ~/path/to/credentials.json

desk auth login          # Re-authenticate
desk auth status         # Check authentication status
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
# Install in dev mode
pip install -e ".[dev]"

# Run tests
pytest

# Lint
ruff check src/
```

## License

MIT
