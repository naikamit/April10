# main.py
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
from error_handler import ErrorHandler
from logging_config import setup_logging

# Set up logging
setup_logging()

import logging
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Trading Signal Webhook Service",
    description="A webhook service for processing trading signals and executing trades via Signal Stack API",
    version="1.0.0"
)

# Configure error handlers
ErrorHandler.configure(app)

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

# Create required directories
os.makedirs("static", exist_ok=True)
os.makedirs("templates", exist_ok=True)
os.makedirs("logs", exist_ok=True)

# Serve static files
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
    logger.info("=== Starting Trading Signal Webhook Service ===")
    
    # Initialize configuration and state
    config = Config()
    state_manager = StateManager()
    
    logger.info(f"Environment: Long symbol: {config.get('LONG_SYMBOL')}")
    logger.info(f"Environment: Short symbol: {config.get('SHORT_SYMBOL')}")
    logger.info(f"Environment: Cooldown period: {config.get('COOLDOWN_PERIOD_HOURS')} hours")
    logger.info(f"Environment: Initial cash balance: ${config.get('INITIAL_CASH_BALANCE'):.2f}")
    logger.info(f"Environment: Signal Stack API URL: {config.get('SIGNAL_STACK_API_URL')}")
    
    # Log cooldown status
    cooldown_info = state_manager.get_cooldown_info()
    if cooldown_info["active"]:
        logger.info(f"Cooldown status: Active with {cooldown_info['remaining_formatted']} remaining")
    else:
        logger.info("Cooldown status: Not active")
    
    # Log cash balance
    cash_info = state_manager.get_cash_balance_info()
    logger.info(f"Cash balance: {cash_info['formatted']} (source: {cash_info['source']})")
    
    logger.info("Service started successfully and ready to receive webhook requests")

@app.on_event("shutdown")
async def shutdown_event() -> None:
    """Perform cleanup operations on shutdown."""
    logger.info("Shutting down webhook service")

if __name__ == "__main__":
    # Get configuration
    config = Config()
    host = config.get("HOST")
    port = int(config.get("PORT"))
    
    # Start server
    logger.info(f"Starting server on {host}:{port}")
    uvicorn.run("main:app", host=host, port=port, reload=False)
