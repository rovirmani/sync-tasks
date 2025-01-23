# Google Tasks to Notion Sync

A Python script that synchronizes tasks between Google Tasks and Notion. The script can be run manually or scheduled via cron/scheduler.

## Features

- One-way sync from Google Tasks to Notion
- Supports task title, completion status, and due dates
- Tracks sync status to avoid duplicates
- Comprehensive error handling and logging
- Easy configuration via JSON file

## Prerequisites

- Python 3.7+
- Google Tasks API credentials
- Notion API token
- Notion database with appropriate columns

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd google-tasks-notion
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up authentication:

   a. Google Tasks:
   - Create a project in Google Cloud Console
   - Enable the Tasks API
   - Create OAuth 2.0 credentials
   - Download the credentials as `client_secrets.json` and place in project root

   b. Notion:
   - Create an integration at https://www.notion.so/my-integrations
   - Get the integration token
   - Share your Notion database with the integration

4. Set environment variables:
```bash
export NOTION_TOKEN='your_notion_integration_token'
```

5. Configure the sync:
   - Copy `config.json` and update with your settings:
     - `google_tasks.list_id`: Your Google Tasks list ID
     - `notion.database_id`: Your Notion database ID
     - `notion.status_column`: Name of status column in Notion
     - `notion.due_date_column`: Name of due date column in Notion

## Usage

Run the sync manually:
```bash
python sync.py
```

### Scheduling

To run the sync automatically, add it to your crontab:
```bash
# Run every hour
0 * * * * cd /path/to/script && python sync.py
```

## Error Handling

The script includes comprehensive error handling for:
- Network connectivity issues
- Authentication failures
- Invalid configuration
- API rate limits

Errors are logged with timestamps and details for debugging.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.
