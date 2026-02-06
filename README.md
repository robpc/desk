# Gmail CLI

A command-line tool for managing Gmail. Unix philosophy: simple commands that compose with pipes.

## Quick Start

```bash
# Install
pip install -e .

# Setup (choose one)
gmail setup --gcloud                    # Easiest: use gcloud credentials
gmail setup --credentials creds.json    # Team: use shared OAuth credentials

# Use it
gmail search "from:boss is:unread"
gmail read <message-id>
gmail archive <message-id>
gmail unread                            # List unread messages
```

## Setup

### Option A: gcloud (Simplest)

If you have `gcloud` installed and authenticated:

```bash
gmail setup --gcloud
```

That's it. Uses your existing gcloud Application Default Credentials.

### Option B: Team Credentials

For teams sharing a Google Cloud project, get the `credentials.json` from your team (e.g., 1Password vault):

```bash
gmail setup --credentials ~/Downloads/credentials.json
```

### Option C: Create Your Own Credentials

This takes about 10 minutes the first time.

#### 1. Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or use an existing one)
3. Note: You can share a project with teammates - add them as Editors

#### 2. Enable Gmail API

1. Go to **APIs & Services** → **Library**
2. Search for "Gmail API"
3. Click **Enable**

#### 3. Create OAuth Credentials

1. Go to **APIs & Services** → **Credentials**
2. Click **Create Credentials** → **OAuth client ID**
3. If prompted, configure the OAuth consent screen:
   - User type: External (or Internal for Workspace)
   - App name: "Gmail CLI" (or whatever you like)
   - Scopes: Add `https://www.googleapis.com/auth/gmail.modify`
4. Application type: **Desktop app**
5. Name: "Gmail CLI"
6. Click **Create**
7. Download the JSON file

#### 4. Install Credentials

```bash
mkdir -p ~/.gmail-cli
mv ~/Downloads/client_secret_*.json ~/.gmail-cli/credentials.json
```

#### 5. Authenticate

```bash
gmail auth login
```

This opens your browser. Log in with your Google account and approve access. Done!

## Commands

### Reading

```bash
gmail search "query"      # Search messages (Gmail search syntax)
gmail search "from:boss is:unread" --max 10
gmail unread              # Shortcut for search "is:unread"
gmail read <id>           # Read a message
gmail labels              # List available labels
```

### Actions

All action commands support **batch operations** - multiple IDs and stdin piping.

```bash
gmail archive <id>...             # Archive messages (remove from inbox)
gmail trash <id>...               # Move to trash
gmail mark-read <id>...           # Mark as read
gmail star <id>...                # Star messages
gmail unstar <id>...              # Remove star
gmail label <label> <id>...       # Add a label
gmail remove-label <label> <id>...  # Remove a label
gmail modify <id>... --add-label X --remove-label Y  # Generic label changes
```

### Batch Operations

```bash
# Multiple IDs
gmail archive ID1 ID2 ID3

# Pipe from search
gmail search "from:notifications" --json | jq -r '.[].id' | gmail archive --stdin

# Combine operations with modify
gmail modify ID1 ID2 --remove-label INBOX --remove-label UNREAD
```

### Auth

```bash
gmail setup               # Interactive setup guide
gmail setup --gcloud      # Use gcloud ADC (simplest)
gmail setup --credentials ~/path/to/credentials.json

gmail auth login          # Re-authenticate
gmail auth status         # Check authentication status
```

### Output Formats

```bash
gmail search "is:unread" --json    # JSON output for piping
gmail archive ID1 ID2 --json       # {"action": "archive", "count": 2, "ids": [...]}
```

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
