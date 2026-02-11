# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## Project Overview

A one-way synchronization tool that syncs tasks from Google Tasks to a Notion database. Can run manually, on a cron schedule, or triggered via webhook. Includes a FastAPI webhook server for automated triggers. Deployable via Docker and Render.

## Tech Stack

- **Language**: Python 3.7+
- **Framework**: FastAPI (webhook server)
- **APIs**: Google Tasks API, Notion API
- **Auth**: Google OAuth 2.0
- **Deployment**: Docker, Render.sh
- **Server**: Uvicorn

## Project Structure

```
sync-tasks/
├── sync.py                      # Main sync logic (19KB)
├── server.py                    # FastAPI webhook server
├── create_webhook.py            # Webhook setup script
├── requirements.txt             # Python dependencies
├── config.json                  # Sync configuration (list/DB mappings)
├── .env.template                # Environment variable template
├── Dockerfile                   # Docker containerization
├── render.yaml                  # Render.sh deployment config
├── client_secrets.json          # Google OAuth credentials (gitignored)
├── token.pickle                 # Cached auth token (gitignored)
└── .github/workflows/
    └── claude.yml               # Claude Code Actions workflow
```

## Development Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run sync manually
python sync.py

# Start webhook server
python server.py
# or
uvicorn server:app --reload

# Create Google Tasks webhook
python create_webhook.py

# Cron job (hourly sync)
# 0 * * * * cd /path/to/sync-tasks && python sync.py

# Docker
docker build -t sync-tasks .
docker run sync-tasks
```

## Environment & Config

### .env Variables
```bash
# Google OAuth
GOOGLE_TOKEN=<serialized-oauth-token>

# Notion
NOTION_TOKEN=<your-notion-integration-token>

# Webhook server
PORT=8000
```

### config.json
Maps Google Tasks lists to Notion databases:
```json
{
  "syncs": [
    {
      "google_list_id": "...",
      "notion_database_id": "...",
      "column_mappings": { ... }
    }
  ]
}
```

### Google OAuth Setup
1. Create project in Google Cloud Console
2. Enable Google Tasks API
3. Create OAuth credentials, download as `client_secrets.json`
4. First run will open browser for OAuth flow, saves `token.pickle`

## Code Style & Standards

- Python standard conventions
- Comprehensive error handling in `sync.py`
- No linter configured
- Configuration-driven sync (config.json)

## Architecture Notes

- **One-way sync**: Google Tasks -> Notion (not bidirectional)
- `sync.py` reads Google Tasks via API, transforms data, writes to Notion via API
- `server.py` provides a FastAPI webhook endpoint that triggers sync on incoming requests
- `create_webhook.py` registers a Google Tasks push notification webhook
- Token management: OAuth token cached in `token.pickle`, refreshed automatically
- Render.yaml configures the webhook server as a web service
- Docker support for containerized deployment

## Troubleshooting

- OAuth expired: Delete `token.pickle` and re-run to trigger new OAuth flow
- Notion API errors: Verify integration has access to the target database
- Google Tasks API errors: Check `client_secrets.json` is valid
- Webhook not firing: Verify webhook URL is publicly accessible (use ngrok for local dev)
- Config errors: Validate `config.json` structure matches expected schema
