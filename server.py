from fastapi import FastAPI, Request, HTTPException, Header
import uvicorn
import os
from sync import TaskSync
from dotenv import load_dotenv
from pathlib import Path
import logging
import asyncio
from datetime import datetime, timezone

# Set up logging with more detail
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI()

# Load environment variables and initialize TaskSync
load_dotenv()
config_path = str(Path(__file__).parent / "config.json")
logger.info(f"Initializing TaskSync with config from {config_path}")
sync = TaskSync(config_path)

async def poll_notion_changes():
    """Poll Notion for changes every minute"""
    while True:
        try:
            logger.info("=== Starting Notion poll cycle ===")
            sync.sync_all()
            logger.info("=== Completed Notion poll cycle ===")
        except Exception as e:
            logger.error(f"Error during sync: {str(e)}", exc_info=True)
        
        # Wait for 60 seconds before next poll
        logger.debug("Waiting 60 seconds before next poll...")
        await asyncio.sleep(60)

@app.on_event("startup")
async def startup_event():
    """Start the polling task when the server starts"""
    logger.info("Starting polling task...")
    asyncio.create_task(poll_notion_changes())

@app.get("/")
def root():
    return {
        "status": "running",
        "last_sync": datetime.now(timezone.utc).isoformat(),
        "polling_interval": "60 seconds"
    }

@app.get("/test")
def test():
    return {"status": "ok", "message": "Server is running"}

@app.post("/sync")
async def manual_sync():
    """Endpoint to manually trigger a sync"""
    try:
        logger.info("Manual sync triggered")
        sync.sync_all()
        return {"status": "success", "message": "Manual sync completed"}
    except Exception as e:
        logger.error(f"Error during manual sync: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    logger.info("Starting server...")
    uvicorn.run("server:app", host="0.0.0.0", port=5001, reload=True)
