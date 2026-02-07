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

### Mail (Gmail)

```bash
# Search and read
desk mail search "query"                # Search messages (Gmail search syntax)
desk mail search "from:boss" --max 10
desk mail unread                        # Shortcut for search "is:unread"
desk mail read <id>                     # Read a message

# Threads (conversations)
desk mail threads "from:boss"           # Search by thread
desk mail thread <thread-id>            # Read entire conversation
desk mail thread-archive <thread-id>    # Archive entire thread
desk mail thread-label Work <thread-id> # Label entire thread
desk mail thread-trash <thread-id>      # Trash entire thread

# Send email
desk mail send --to "user@example.com" --subject "Hello" --body "Message"
desk mail send --to "a@b.com" --cc "c@d.com" --subject "Update" --body-file notes.txt
echo "Report" | desk mail send --to "boss@example.com" --subject "Report" --stdin

# Reply and forward
desk mail reply <id> --body "Thanks!"
desk mail reply <id> --all --body "Sounds good"  # Reply all
desk mail forward <id> --to "colleague@example.com" --body "FYI"

# Drafts
desk mail drafts                        # List drafts
desk mail draft create --to "..." --subject "..." --body "..."
desk mail draft read <draft-id>
desk mail draft send <draft-id>
desk mail draft delete <draft-id>
desk mail draft update <draft-id> --body "Updated"

# Attachments
desk mail attachments <id>              # List attachments
desk mail attachment <id> "file.pdf" --output file.pdf
desk mail attachment <id> "data.csv" | head -5   # Pipe to stdout
desk mail download-attachments <id> --output-dir ./files/

# Labels
desk mail labels                        # List available labels
desk mail create-label "Projects/Work"  # Create label (/ for nesting)
desk mail create-label "Urgent" --color red  # Create with color
desk mail delete-label "Old Label"      # Delete a label (removes from messages)
desk mail rename-label "Old" "New"      # Rename a label
desk mail label <label> <id>...         # Add a label
desk mail remove-label <label> <id>...  # Remove a label

# Actions
desk mail archive <id>...               # Archive messages
desk mail trash <id>...                 # Move to trash
desk mail mark-read <id>...             # Mark as read
desk mail mark-unread <id>...           # Mark as unread
desk mail star <id>...                  # Star messages
desk mail unstar <id>...                # Unstar messages
desk mail modify <id>... -a Work -r INBOX  # Generic label changes

# Dry run (preview without executing)
desk mail archive <id> --dry-run
desk mail send --to "..." --subject "..." --body "..." --dry-run
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
