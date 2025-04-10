# main.py
import logging
import os
from typing import Dict, Any

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

import uvicorn

from config import Config
from dashboard import router as dashboard_router
from webhook import router as webhook_router
from state_manager import StateManager

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("webhook_service.log")
    ]
)

logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(title="Trading Signal Webhook Service")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(webhook_router)
app.include_router(dashboard_router)

# Serve static files if directory exists
if not os.path.exists("static"):
    os.makedirs("static")
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def root() -> RedirectResponse:
    """Redirect root to dashboard."""
    return RedirectResponse(url="/")

@app.get("/health")
async def health_check() -> Dict[str, Any]:
    """Health check endpoint."""
    return {"status": "healthy"}

@app.on_event("startup")
async def startup_event() -> None:
    """Initialize application state on startup."""
    logger.info("Starting webhook service")
    
    # Initialize configuration and state
    config = Config()
    state_manager = StateManager()
    
    logger.info(f"Long symbol: {config.get('LONG_SYMBOL')}")
    logger.info(f"Short symbol: {config.get('SHORT_SYMBOL')}")
    logger.info(f"Cooldown period: {config.get('COOLDOWN_PERIOD_HOURS')} hours")
    logger.info(f"Initial cash balance: ${config.get('INITIAL_CASH_BALANCE'):.2f}")
    
    # Log cooldown status
    cooldown_info = state_manager.get_cooldown_info()
    if cooldown_info["active"]:
        logger.info(f"Cooldown active: {cooldown_info['remaining_formatted']} remaining")
    else:
        logger.info("No cooldown active")

@app.on_event("shutdown")
async def shutdown_event() -> None:
    """Perform cleanup operations on shutdown."""
    logger.info("Shutting down webhook service")

if __name__ == "__main__":
    # Get configuration
    config = Config()
    host = config.get("HOST")
    port = config.get("PORT")
    
    # Start server
    logger.info(f"Starting server on {host}:{port}")
    uvicorn.run("main:app", host=host, port=port, reload=False)
