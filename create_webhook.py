import os
import requests
from dotenv import load_dotenv
import json

load_dotenv()

NOTION_TOKEN = os.getenv('NOTION_TOKEN')
DATABASE_ID = os.getenv('NOTION_CAREER_DB_ID')  # or NOTION_GOALS_DB_ID

print("\nUsing:")
print(f"Database ID: {DATABASE_ID}")
print(f"Token: {NOTION_TOKEN[:4]}...{NOTION_TOKEN[-4:]}")

TUNNEL_URL = input("\nEnter your localtunnel URL (e.g., https://something.loca.lt): ").strip()

headers = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

print("\nChecking existing webhooks...")
list_response = requests.get(
    "https://api.notion.com/v1/webhooks",
    headers=headers
)

print(f"List webhooks response: {list_response.status_code}")
print(json.dumps(list_response.json(), indent=2))

webhook_data = {
    "parent": {
        "type": "database_id",
        "database_id": DATABASE_ID
    },
    "url": f"{TUNNEL_URL}/webhook",
    "events": ["page_properties_edited", "pages_created"]
}

print("\nCreating webhook with data:")
print(json.dumps(webhook_data, indent=2))

response = requests.post(
    "https://api.notion.com/v1/webhooks",
    headers=headers,
    json=webhook_data
)

print(f"\nCreate webhook response: {response.status_code}")
print(json.dumps(response.json(), indent=2))

# Test the webhook URL
print("\nTesting webhook URL...")
test_response = requests.get(f"{TUNNEL_URL}/test")
print(f"Test endpoint response: {test_response.status_code}")
if test_response.status_code == 200:
    print(json.dumps(test_response.json(), indent=2))
else:
    print(f"Error: {test_response.text}")
