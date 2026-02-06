# Gmail CLI (`gm`)

A command-line tool for managing Gmail. Unix philosophy: simple commands that compose.

## Quick Start

```bash
# Install
pip install -e .

# First-time setup (see Setup section below)
gmail auth login

# Use it
gmail search "from:boss is:unread"
gmail read <message-id>
gmail labels
```

## Setup

This tool requires you to bring your own Google Cloud credentials. This takes about 10 minutes the first time.

### 1. Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or use an existing one)
3. Note: You can share a project with teammates - add them as Editors

### 2. Enable Gmail API

1. Go to **APIs & Services** → **Library**
2. Search for "Gmail API"
3. Click **Enable**

### 3. Create OAuth Credentials

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

### 4. Install Credentials

```bash
mkdir -p ~/.gmail-cli
mv ~/Downloads/client_secret_*.json ~/.gmail-cli/credentials.json
```

### 5. Authenticate

```bash
gmail auth login
```

This opens your browser. Log in with your Google account and approve access. Done!

## Commands

```bash
gmail auth login          # Authenticate with Gmail
gmail auth status         # Check authentication status

gmail search "query"      # Search messages (Gmail search syntax)
gmail read <id>           # Read a message
gmail send                # Send a message
gmail label <id> <label>  # Add label to message
gmail archive <id>        # Archive message
gmail labels              # List available labels
```

### Output Formats

```bash
gmail search "is:unread" --json    # JSON output for piping
gmail search "is:unread" | jq .    # Compose with other tools
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
