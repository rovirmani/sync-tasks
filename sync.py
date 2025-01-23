import os
from typing import Dict, List, Optional
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from notion_client import Client
import json
import logging
import pickle
from datetime import datetime, timezone, timedelta
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class TaskSync:
    SCOPES = ['https://www.googleapis.com/auth/tasks']
    TOKEN_FILE = 'token.pickle'
    
    def __init__(self, config_path: str):
        """Initialize TaskSync with configuration file path."""
        self.config = self._load_config(config_path)
        self.google_tasks = self._setup_google()
        self.notion = Client(auth=os.getenv("NOTION_TOKEN"))
        self.task_list_mapping = {}
        
        # Create task list mapping
        for task_list in self.config["google_tasks"]["lists"]:
            list_id = os.getenv(task_list["env_list_id"])
            notion_db_id = os.getenv(task_list["env_notion_db_id"])
            self.task_list_mapping[list_id] = notion_db_id
        
    def _load_config(self, config_path: str) -> Dict:
        """Load configuration from JSON file."""
        try:
            with open(config_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            logger.error(f"Configuration file not found: {config_path}")
            raise
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON in configuration file: {config_path}")
            raise

    def _setup_google(self) -> any:
        """Set up Google Tasks API client."""
        creds = None
        if os.path.exists(self.TOKEN_FILE):
            with open(self.TOKEN_FILE, 'rb') as token:
                creds = pickle.load(token)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    'client_secrets.json', self.SCOPES)
                creds = flow.run_local_server(port=0)
                
            with open(self.TOKEN_FILE, 'wb') as token:
                pickle.dump(creds, token)

        return build('tasks', 'v1', credentials=creds)

    def _get_google_tasks(self, list_id: str) -> List[Dict]:
        """Fetch tasks from Google Tasks."""
        try:
            results = self.google_tasks.tasks().list(
                tasklist=list_id,
                showCompleted=True
            ).execute()
            tasks = results.get("items", [])
            
            # Filter out completed tasks older than 7 days
            filtered_tasks = []
            current_time = datetime.utcnow()
            
            for task in tasks:
                # Include task if:
                # 1. It's not completed, or
                # 2. It was completed within the last 7 days
                if not task.get("completed"):
                    filtered_tasks.append(task)
                else:
                    completed_time = datetime.strptime(task["completed"], "%Y-%m-%dT%H:%M:%S.%fZ")
                    days_since_completion = (current_time - completed_time).days
                    if days_since_completion <= 7:
                        filtered_tasks.append(task)
            
            # Get task IDs for cleanup
            active_task_ids = set(task['id'] for task in filtered_tasks)
            
            return filtered_tasks
        except Exception as e:
            logger.error(f"Error fetching Google Tasks: {str(e)}")
            raise

    def _find_existing_task(self, task_id: str, database_id: str) -> Optional[Dict]:
        """Find existing task in Notion by Google Tasks ID."""
        try:
            response = self.notion.databases.query(
                database_id=database_id,
                filter={
                    "property": self.config["notion"]["task_id_column"],
                    "rich_text": {
                        "equals": task_id
                    }
                }
            )
            return response["results"][0] if response["results"] else None
        except Exception as e:
            logger.error(f"Error finding task in Notion: {str(e)}")
            raise

    def _sync_task_to_notion(self, task: Dict, database_id: str) -> None:
        """Sync a single task from Google Tasks to Notion."""
        try:
            # Get task details
            task_id = task.get("id")
            title = task.get("title", "Untitled")
            status = task.get("status", "needsAction")  # Default to needsAction if no status
            
            # Convert Google Tasks status to Notion status
            # Keep existing "Doing" status if present
            notion_status = "Completed" if status == "completed" else (
                "Active" if status == "needsAction" else "Active"
            )
            
            # Find existing task in Notion
            existing = self._find_existing_task(task_id, database_id)
            
            if existing:
                # Don't override "Doing" status with "Active"
                current_status = existing["properties"][self.config["notion"]["status_column"]]["select"]["name"]
                if current_status == "Doing" and notion_status == "Active":
                    notion_status = "Doing"
                    
                # Update existing task
                self.notion.pages.update(
                    page_id=existing["id"],
                    properties={
                        "Title": {"title": [{"text": {"content": title}}]},
                        self.config["notion"]["status_column"]: {"select": {"name": notion_status}}
                    }
                )
                logger.info(f"Updated task in Notion: {title}")
            else:
                # Create new task
                self.notion.pages.create(
                    parent={"database_id": database_id},
                    properties={
                        "Title": {"title": [{"text": {"content": title}}]},
                        self.config["notion"]["status_column"]: {"select": {"name": notion_status}},
                        self.config["notion"]["task_id_column"]: {"rich_text": [{"text": {"content": task_id}}]}
                    }
                )
                logger.info(f"Created new task in Notion: {title}")
                
        except Exception as e:
            logger.error(f"Error updating task in Notion: {str(e)}")
            raise

    def _create_task(self, task: Dict, database_id: str) -> None:
        """Create a new task in Notion."""
        try:
            properties = {
                "Title": {"title": [{"text": {"content": task["title"]}}]},
                self.config["notion"]["task_id_column"]: {"rich_text": [{"text": {"content": task["id"]}}]},
                self.config["notion"]["status_column"]: {
                    "select": {
                        "name": "Completed" if task.get("status") == "completed" else (
                            "Active" if task.get("status") == "needsAction" else "Active"
                        )
                    }
                }
            }

            if "due" in task:
                properties[self.config["notion"]["due_date_column"]] = {
                    "date": {"start": task["due"]}
                }

            self.notion.pages.create(
                parent={"database_id": database_id},
                properties=properties
            )
            logger.info(f"Created task in Notion: {task['title']}")
        except Exception as e:
            logger.error(f"Error creating task in Notion: {str(e)}")
            raise

    def _update_task(self, notion_page: Dict, task: Dict, database_id: str) -> None:
        """Update existing task in Notion."""
        try:
            properties = {
                "Title": {"title": [{"text": {"content": task["title"]}}]},
                self.config["notion"]["status_column"]: {
                    "select": {
                        "name": "Completed" if task.get("status") == "completed" else (
                        "Active" if task.get("status") == "needsAction" else "Active"
                    )
                    }
                }
            }

            if "due" in task:
                properties[self.config["notion"]["due_date_column"]] = {
                    "date": {"start": task["due"]}
                }

            self.notion.pages.update(
                page_id=notion_page["id"],
                properties=properties
            )
            logger.info(f"Updated task in Notion: {task['title']}")
        except Exception as e:
            logger.error(f"Error updating task in Notion: {str(e)}")
            raise

    def _cleanup_old_tasks(self, database_id: str, active_task_ids: set) -> None:
        """Delete tasks from Notion that are no longer in Google Tasks or are old completed tasks."""
        try:
            logger.info(f"Starting cleanup for database {database_id}")
            logger.info(f"Active task IDs: {active_task_ids}")
            
            # Query for all tasks in the database
            response = self.notion.databases.query(
                database_id=database_id
            )
            
            notion_tasks = response.get("results", [])
            logger.info(f"Found {len(notion_tasks)} total tasks in Notion")

            # Check each task
            for page in notion_tasks:
                task_id_prop = page["properties"][self.config["notion"]["task_id_column"]]["rich_text"]
                title = page["properties"]["Title"]["title"][0]["text"]["content"] if page["properties"]["Title"]["title"] else "Untitled"
                status = page["properties"][self.config["notion"]["status_column"]]["select"]["name"] if page["properties"][self.config["notion"]["status_column"]]["select"] else "Unknown"
                
                if not task_id_prop:
                    logger.info(f"Skipping task '{title}' - no Google Task ID found")
                    continue
                    
                task_id = task_id_prop[0]["text"]["content"]
                
                # Convert last_edited_time to UTC datetime
                last_edited_str = page["last_edited_time"]  # Format: "2024-01-22T02:47:33.719Z"
                last_edited = datetime.strptime(last_edited_str, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=None)
                current_time = datetime.utcnow()
                days_since_edit = (current_time - last_edited).days
                
                logger.info(f"Checking task '{title}' (ID: {task_id}):")
                logger.info(f"  - Status: {status}")
                logger.info(f"  - Days since last edit: {days_since_edit}")
                logger.info(f"  - Present in Google Tasks: {task_id in active_task_ids}")
                
                # Delete if:
                # 1. Task is not in Google Tasks anymore, OR
                # 2. Task is completed AND older than 7 days
                should_delete = (
                    task_id not in active_task_ids or 
                    (status == "Completed" and days_since_edit > 7)
                )
                
                if should_delete:
                    reason = "not in Google Tasks" if task_id not in active_task_ids else "completed and old"
                    logger.info(f"Archiving task '{title}' - {reason}")
                    self.notion.pages.update(
                        page_id=page["id"],
                        archived=True
                    )
                else:
                    logger.info(f"Keeping task '{title}' - still in Google Tasks and either active or recently completed")
                    
        except Exception as e:
            logger.error(f"Error cleaning up old tasks: {str(e)}")
            # Don't raise the error - we don't want cleanup failure to stop the sync

    def list_task_lists(self) -> None:
        """List all Google Task lists and their IDs."""
        try:
            results = self.google_tasks.tasklists().list().execute()
            lists = results.get('items', [])
            if not lists:
                print('No task lists found.')
            else:
                print('Task lists:')
                for task_list in lists:
                    print(f"Title: {task_list['title']}")
                    print(f"ID: {task_list['id']}")
                    print('---')
        except Exception as e:
            logger.error(f"Error listing task lists: {str(e)}")
            raise

    def sync(self) -> None:
        """Main sync function to synchronize Google Tasks to Notion."""
        logger.info("Starting sync process...")
        try:
            for task_list in self.config["google_tasks"]["lists"]:
                list_id = os.getenv(task_list["env_list_id"])
                notion_db_id = os.getenv(task_list["env_notion_db_id"])
                
                if not list_id or not notion_db_id:
                    logger.error(f"Missing environment variables for task list {task_list['name']}")
                    continue
                    
                logger.info(f"Syncing task list {task_list['name']} to Notion database")
                tasks = self._get_google_tasks(list_id)
                logger.info(f"Found {len(tasks)} tasks in Google Tasks list")

                # Keep track of active task IDs for cleanup
                active_task_ids = set(task["id"] for task in tasks)

                for task in tasks:
                    existing = self._find_existing_task(task["id"], notion_db_id)
                    if existing:
                        self._update_task(existing, task, notion_db_id)
                    else:
                        self._create_task(task, notion_db_id)

                # Clean up old completed tasks
                self._cleanup_old_tasks(notion_db_id, active_task_ids)

            logger.info("Sync completed successfully")
        except Exception as e:
            logger.error(f"Sync failed: {str(e)}")
            raise

    def _is_task_recently_completed(self, task, days=7):
        """Check if a task was completed within the last N days."""
        try:
            # Get last edited time, defaulting to current time if not found
            last_edited_str = task.get('last_edited_time')
            if not last_edited_str:
                logger.warning(f"Task {task.get('id', 'unknown')} missing last_edited_time, using current time")
                return True  # Assume it's recent if we can't determine
                
            # Convert task's last edited time to UTC
            last_edited = datetime.fromisoformat(last_edited_str.rstrip('Z')).replace(tzinfo=timezone.utc)
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
            
            # Both dates are now in UTC, safe to compare
            return last_edited >= cutoff_date
        except Exception as e:
            logger.error(f"Error checking task completion time: {str(e)}")
            # If we can't determine completion time, assume it's recent to be safe
            return True

    def _filter_notion_tasks(self, tasks, days=7):
        """Filter Notion tasks based on completion status and date."""
        filtered_tasks = []
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
        
        for task in tasks:
            try:
                # Get last edited time, defaulting to current time if not found
                last_edited_str = task.get('last_edited_time')
                if last_edited_str:
                    # Convert to UTC for comparison
                    last_edited = datetime.fromisoformat(last_edited_str.rstrip('Z')).replace(tzinfo=timezone.utc)
                else:
                    logger.warning(f"Task {task.get('id')} missing last_edited_time, using current time")
                    last_edited = datetime.now(timezone.utc)
                
                # Safely get properties
                properties = task.get('properties', {})
                status_prop = properties.get(self.config['notion']['status_column'])
                
                if status_prop is None:
                    logger.warning(f"Task {task.get('id')} missing status column {self.config['notion']['status_column']}")
                    status = None
                else:
                    status = status_prop.get('select', {}).get('name')
                
                # Keep task if:
                # 1. No status (treat as not completed), or
                # 2. Not completed, or
                # 3. Completed but edited in last 7 days
                if status is None or status != "Completed" or last_edited >= cutoff_date:
                    filtered_tasks.append(task)
                    
            except Exception as e:
                logger.warning(f"Error processing task {task.get('id', 'unknown')}: {str(e)}")
                # If we can't process the task properly, include it to be safe
                filtered_tasks.append(task)
                continue
        
        logger.info(f"Filtered to {len(filtered_tasks)} tasks within 7-day completion window")
        return filtered_tasks

    def sync_all(self):
        """Sync all configured task lists between Notion and Google Tasks."""
        try:
            logger.info("Starting full sync")
            
            # Get all task list mappings from config
            task_lists = self.config.get("google_tasks", {}).get("lists", [])
            logger.info(f"Found {len(task_lists)} task list(s) to sync")
            
            for task_list in task_lists:
                list_name = task_list.get("name", "Unknown List")
                google_list_id = os.getenv(task_list["env_list_id"])
                notion_db_id = os.getenv(task_list["env_notion_db_id"])
                
                if not google_list_id or not notion_db_id:
                    logger.error(f"Missing environment variables for list {list_name}")
                    logger.error(f"GOOGLE_LIST_ID: {google_list_id}")
                    logger.error(f"NOTION_DB_ID: {notion_db_id}")
                    continue
                
                logger.info(f"\nSyncing list: {list_name}")
                logger.info(f"Google Tasks ID: {google_list_id}")
                logger.info(f"Notion DB ID: {notion_db_id}")
                
                # Get all tasks from Google Tasks
                logger.info("Fetching tasks from Google Tasks...")
                all_google_tasks = self.google_tasks.tasks().list(
                    tasklist=google_list_id,
                    showCompleted=True
                ).execute().get('items', [])
                
                # Filter out tasks completed more than 7 days ago
                google_tasks = [
                    task for task in all_google_tasks 
                    if self._is_task_recently_completed(task)
                ]
                logger.info(f"Found {len(all_google_tasks)} tasks in Google Tasks")
                logger.info(f"Filtered to {len(google_tasks)} tasks within 7-day completion window")
                
                # Get all tasks from Notion
                logger.info("Fetching tasks from Notion...")
                notion_response = self.notion.databases.query(database_id=notion_db_id)
                notion_tasks = notion_response.get('results', [])
                logger.info(f"Found {len(notion_tasks)} total tasks in Notion")

                # Filter tasks in Python
                notion_tasks = self._filter_notion_tasks(notion_tasks)
                
                # Sync Google Tasks to Notion
                logger.info("\nSyncing Google Tasks → Notion")
                for task in google_tasks:
                    title = task.get('title', 'Untitled')
                    logger.info(f"Processing Google task: {title}")
                    try:
                        self._sync_task_to_notion(task, notion_db_id)
                    except Exception as e:
                        logger.error(f"Error syncing task {title} to Notion: {str(e)}", exc_info=True)
                
                # Sync Notion to Google Tasks
                logger.info("\nSyncing Notion → Google Tasks")
                for task in notion_tasks:
                    try:
                        props = task.get('properties', {})
                        title_array = props.get('Title', {}).get('title', [])
                        if not title_array:
                            logger.warning(f"Task has no title, skipping: {task.get('id', 'unknown id')}")
                            continue
                        title = title_array[0].get('text', {}).get('content', 'Untitled')
                        status = props.get(self.config['notion']['status_column'], {}).get('select', {}).get('name', 'Unknown')
                        logger.info(f"Processing Notion task: {title} (Status: {status})")
                        self._sync_notion_to_google(task, google_list_id)
                    except Exception as e:
                        logger.error(f"Error syncing task {title} to Google Tasks: {str(e)}", exc_info=True)
                
                logger.info(f"Completed sync for list: {list_name}")
            
            logger.info("\nFull sync completed successfully")
            
        except Exception as e:
            logger.error(f"Error during sync_all: {str(e)}", exc_info=True)
            raise

    def _sync_notion_to_google(self, notion_page: dict, task_list_id: str) -> None:
        """Sync a Notion task to Google Tasks."""
        try:
            # Get properties safely
            properties = notion_page.get("properties", {})
            if not properties:
                logger.error(f"Task {notion_page.get('id', 'unknown')} has no properties")
                return
                
            # Get task details from Notion safely
            title_array = properties.get('Title', {}).get('title', [])
            if not title_array:
                logger.warning(f"Task has no title, skipping: {notion_page.get('id', 'unknown id')}")
                return
            title = title_array[0].get('text', {}).get('content', 'Untitled')
            
            status_prop = properties.get(self.config["notion"]["status_column"], {}).get("select")
            status = status_prop.get("name") if status_prop else "Active"
            
            task_id_prop = properties.get(self.config["notion"]["task_id_column"], {}).get("rich_text", [])
            
            logger.info(f"Syncing Notion → Google: '{title}' (Status: {status})")
            
            # Convert Notion status to Google Tasks status
            # Only sync if status is "Active" or "Completed", ignore "Doing"
            google_status = {
                "Active": "needsAction",
                "Completed": "completed",
                "Doing": None  # Don't update Google Tasks for "Doing" status
            }.get(status)
            
            logger.info(f"  - Converted status '{status}' → '{google_status}'")
            
            # Skip sync if status is "Doing"
            if google_status is None:
                logger.info(f"  - Skipping sync - status is 'Doing'")
                return
            
            if not task_id_prop:
                logger.info(f"  - No Google Tasks ID found, creating new task")
                # This is a new task in Notion, create it in Google Tasks
                task = {
                    'title': title,
                    'status': google_status
                }
                result = self.google_tasks.tasks().insert(tasklist=task_list_id, body=task).execute()
                task_id = result['id']
                logger.info(f"  - Created new task with ID: {task_id}")
                
                # Update Notion with the Google Task ID
                self.notion.pages.update(
                    page_id=notion_page["id"],
                    properties={
                        self.config["notion"]["task_id_column"]: {
                            "rich_text": [{"text": {"content": task_id}}]
                        }
                    }
                )
                logger.info(f"  - Updated Notion with new task ID")
            else:
                # Get the task ID from the rich_text property
                task_id = task_id_prop[0]["text"]["content"]
                logger.info(f"  - Found existing Google Tasks ID: {task_id}")
                
                # Update existing task in Google Tasks
                try:
                    task = {
                        'id': task_id,
                        'title': title,
                        'status': google_status
                    }
                    logger.info(f"  - Updating task with new status: {google_status}")
                    self.google_tasks.tasks().update(tasklist=task_list_id, task=task_id, body=task).execute()
                    logger.info(f"  - Successfully updated task")
                except Exception as e:
                    if "Resource has been deleted" in str(e):
                        logger.info(f"  - Task was deleted in Google Tasks, creating new one")
                        # Task was deleted in Google Tasks, create a new one
                        task = {
                            'title': title,
                            'status': google_status
                        }
                        result = self.google_tasks.tasks().insert(tasklist=task_list_id, body=task).execute()
                        new_task_id = result['id']
                        logger.info(f"  - Created new task with ID: {new_task_id}")
                        
                        # Update Notion with the new Google Task ID
                        self.notion.pages.update(
                            page_id=notion_page["id"],
                            properties={
                                self.config["notion"]["task_id_column"]: {
                                    "rich_text": [{"text": {"content": new_task_id}}]
                                }
                            }
                        )
                        logger.info(f"  - Updated Notion with new task ID")
                    else:
                        raise
                        
        except Exception as e:
            logger.error(f"Error syncing task to Google Tasks: {str(e)}")
            raise

    def handle_notion_webhook(self, event_data: dict) -> None:
        """Handle webhook events from Notion."""
        try:
            # Extract relevant information from the webhook event
            page_id = event_data.get('page', {}).get('id')
            if not page_id:
                logger.warning("No page ID in webhook event")
                return
            
            # Get the page details from Notion
            page = self.notion.pages.retrieve(page_id=page_id)
            
            # Find which task list this page belongs to
            database_id = page.get('parent', {}).get('database_id')
            if not database_id:
                logger.warning(f"Page {page_id} is not in a database")
                return
            
            # Find the corresponding Google Tasks list
            task_list = next(
                (tl for tl in self.config.get("task_lists", [])
                 if tl["notion_database_id"] == database_id),
                None
            )
            
            if not task_list:
                logger.warning(f"No task list mapping found for database {database_id}")
                return
            
            # Sync this specific task to Google Tasks
            self._sync_notion_to_google(page, task_list["google_tasks_list_id"])
            logger.info(f"Successfully synced page {page_id} to Google Tasks")
            
        except Exception as e:
            logger.error(f"Error handling webhook: {str(e)}")
            raise

def main():
    """Main entry point for the script."""
    try:
        # If --list-tasks argument is provided, we don't need Notion token
        import sys
        if len(sys.argv) > 1 and sys.argv[1] == '--list-tasks':
            sync = TaskSync("config.json")
            sync.list_task_lists()
            return
            
        # For actual sync, we need Notion token
        if not os.getenv("NOTION_TOKEN"):
            raise ValueError("NOTION_TOKEN environment variable not set")

        sync = TaskSync("config.json")
        sync.sync()
    except Exception as e:
        logger.error(f"Application error: {str(e)}")
        raise

if __name__ == "__main__":
    main()
