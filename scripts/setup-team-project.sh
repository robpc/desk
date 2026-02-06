#!/bin/bash
#
# Setup script for Gmail CLI team project
#
# This script helps a team admin create a shared Google Cloud project
# for the Gmail CLI. Run this once, then share the credentials.json
# with your team via 1Password or similar.
#
# Prerequisites:
#   - gcloud CLI installed and authenticated
#   - Billing account (required for API enablement)
#
# Usage:
#   ./scripts/setup-team-project.sh [project-name]
#
# Example:
#   ./scripts/setup-team-project.sh gmail-cli-myteam

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Default project name
PROJECT_NAME="${1:-gmail-cli-$(whoami)}"

echo -e "${CYAN}Gmail CLI Team Project Setup${NC}"
echo "================================"
echo ""

# Check for gcloud
if ! command -v gcloud &> /dev/null; then
    echo -e "${RED}Error: gcloud CLI not found${NC}"
    echo "Install from: https://cloud.google.com/sdk/docs/install"
    exit 1
fi

# Check gcloud auth
if ! gcloud auth list --filter="status:ACTIVE" --format="value(account)" &> /dev/null; then
    echo -e "${RED}Error: Not authenticated with gcloud${NC}"
    echo "Run: gcloud auth login"
    exit 1
fi

ACTIVE_ACCOUNT=$(gcloud auth list --filter="status:ACTIVE" --format="value(account)" 2>/dev/null | head -1)
echo -e "Authenticated as: ${GREEN}${ACTIVE_ACCOUNT}${NC}"
echo ""

# Step 1: Create project
echo -e "${YELLOW}Step 1: Creating project '${PROJECT_NAME}'...${NC}"

if gcloud projects describe "$PROJECT_NAME" &> /dev/null; then
    echo -e "Project ${GREEN}${PROJECT_NAME}${NC} already exists, using it."
else
    gcloud projects create "$PROJECT_NAME" --name="Gmail CLI" 2>/dev/null || {
        echo -e "${RED}Failed to create project. The name might be taken globally.${NC}"
        echo "Try a more unique name: ./scripts/setup-team-project.sh gmail-cli-${RANDOM}"
        exit 1
    }
    echo -e "${GREEN}Project created!${NC}"
fi
echo ""

# Step 2: Set as active project
echo -e "${YELLOW}Step 2: Setting active project...${NC}"
gcloud config set project "$PROJECT_NAME"
echo -e "${GREEN}Done${NC}"
echo ""

# Step 3: Enable Gmail API
echo -e "${YELLOW}Step 3: Enabling Gmail API...${NC}"
gcloud services enable gmail.googleapis.com 2>/dev/null || {
    echo -e "${RED}Failed to enable Gmail API.${NC}"
    echo "This usually means billing is not set up for the project."
    echo ""
    echo "To fix:"
    echo "  1. Go to: https://console.cloud.google.com/billing/linkedaccount?project=${PROJECT_NAME}"
    echo "  2. Link a billing account"
    echo "  3. Re-run this script"
    exit 1
}
echo -e "${GREEN}Gmail API enabled!${NC}"
echo ""

# Step 4: Configure OAuth consent screen
echo -e "${YELLOW}Step 4: OAuth Consent Screen${NC}"
echo ""
echo "You need to configure the OAuth consent screen manually."
echo ""
echo -e "Opening: ${CYAN}https://console.cloud.google.com/apis/credentials/consent?project=${PROJECT_NAME}${NC}"
echo ""
echo "Configure with:"
echo "  - User Type: External (or Internal for Workspace)"
echo "  - App name: Gmail CLI"
echo "  - User support email: your email"
echo "  - Developer contact: your email"
echo "  - Scopes: Add 'https://www.googleapis.com/auth/gmail.modify'"
echo ""
read -p "Press Enter when OAuth consent screen is configured..."

# Try to open the URL
if command -v open &> /dev/null; then
    open "https://console.cloud.google.com/apis/credentials/consent?project=${PROJECT_NAME}"
elif command -v xdg-open &> /dev/null; then
    xdg-open "https://console.cloud.google.com/apis/credentials/consent?project=${PROJECT_NAME}"
fi

echo ""

# Step 5: Create OAuth credentials
echo -e "${YELLOW}Step 5: Create OAuth Credentials${NC}"
echo ""
echo "Now create the OAuth client ID."
echo ""
echo -e "Opening: ${CYAN}https://console.cloud.google.com/apis/credentials/oauthclient?project=${PROJECT_NAME}${NC}"
echo ""
echo "Configure with:"
echo "  - Application type: Desktop app"
echo "  - Name: Gmail CLI"
echo ""
echo "After creating, download the JSON file."
echo ""
read -p "Press Enter when you've downloaded credentials.json..."

# Try to open the URL
if command -v open &> /dev/null; then
    open "https://console.cloud.google.com/apis/credentials/oauthclient?project=${PROJECT_NAME}"
elif command -v xdg-open &> /dev/null; then
    xdg-open "https://console.cloud.google.com/apis/credentials/oauthclient?project=${PROJECT_NAME}"
fi

echo ""

# Step 6: Add test users
echo -e "${YELLOW}Step 6: Add Test Users${NC}"
echo ""
echo "Since the app is unverified, you need to add team members as test users."
echo ""
echo -e "Go to: ${CYAN}https://console.cloud.google.com/apis/credentials/consent?project=${PROJECT_NAME}${NC}"
echo ""
echo "Scroll to 'Test users' and add each team member's email."
echo "(Up to 100 test users allowed)"
echo ""
read -p "Press Enter when test users are added..."

echo ""
echo -e "${GREEN}================================${NC}"
echo -e "${GREEN}Setup complete!${NC}"
echo -e "${GREEN}================================${NC}"
echo ""
echo "Next steps:"
echo ""
echo "  1. Upload credentials.json to your team's 1Password vault"
echo "     (or other secure sharing method)"
echo ""
echo "  2. Share these instructions with your team:"
echo ""
echo "     # Install Gmail CLI"
echo "     pip install gmail-cli  # or: pip install -e /path/to/gmail-cli"
echo ""
echo "     # Download credentials.json from 1Password, then:"
echo "     gmail setup --credentials ~/Downloads/credentials.json"
echo ""
echo "  3. Project ID for reference: ${PROJECT_NAME}"
echo ""
