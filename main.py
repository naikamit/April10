# main.py - Entry point, FastAPI setup - Headless API-only mode with multi-user support
import logging
import os
from datetime import datetime
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Form, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse
from typing import Optional, List, Dict

from config import DASHBOARD_PORT, get_valid_users, is_valid_user, get_all_webhook_urls
from strategy_repository import StrategyRepository
from signal_processor import SignalProcessor
from cash_manager import CashManager
from cooldown_manager import CooldownManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('webhook.log')
    ]
)

logger = logging.getLogger(__name__)

# Initialize services
strategy_repo = StrategyRepository()
signal_processor = SignalProcessor()
cash_manager = CashManager()
cooldown_manager = CooldownManager()

@asynccontextmanager
async def lifespan(app):
    # Startup event
    logger.info("🔥 SYSTEM STARTUP: Multi-User Trading Webhook Service (Headless Mode)")
    
    # Log configured users from environment variables
    valid_users = get_valid_users()
    webhook_urls = get_all_webhook_urls()
    
    logger.info(f"🔥 USER MANAGEMENT: found {len(valid_users)} users in environment variables")
    for user_id in valid_users:
        logger.info(f"🔥 USER MANAGEMENT: found user={user_id} with webhook URL")
    
    yield
    
    # Shutdown event
    logger.info("🔥 SYSTEM SHUTDOWN: Multi-User Trading Webhook Service")

# Initialize FastAPI in headless mode (no UI)
app = FastAPI(title="Multi-User Trading Webhook Service", lifespan=lifespan)

# Root path - simple status page instead of dashboard
@app.get("/", response_class=PlainTextResponse)
async def service_status():
    """Basic service status indicator"""
    valid_users = get_valid_users()
    all_strategies = strategy_repo.get_all_strategies()
    
    return f"Service Running\n\nUsers: {len(valid_users)}\nStrategies: {len(all_strategies)}\n\nWebhook Format: /<user_id>/<strategy_name>/<signal>"

# User-specific webhook endpoints
@app.post("/{user_id}/{strategy_name}/long")
async def user_webhook_long(user_id: str, strategy_name: str, request: Request, background_tasks: BackgroundTasks):
    """Webhook endpoint for long signals for a specific user"""
    return await _process_webhook(strategy_name, "long", request, background_tasks, user_id)

@app.post("/{user_id}/{strategy_name}/short")
async def user_webhook_short(user_id: str, strategy_name: str, request: Request, background_tasks: BackgroundTasks):
    """Webhook endpoint for short signals for a specific user"""
    return await _process_webhook(strategy_name, "short", request, background_tasks, user_id)

@app.post("/{user_id}/{strategy_name}/close")
async def user_webhook_close(user_id: str, strategy_name: str, request: Request, background_tasks: BackgroundTasks):
    """Webhook endpoint for close signals for a specific user"""
    return await _process_webhook(strategy_name, "close", request, background_tasks, user_id)

# Broadcast webhook endpoints
@app.post("/cast/{strategy_name}/long")
async def broadcast_webhook_long(strategy_name: str, request: Request, background_tasks: BackgroundTasks):
    """Broadcast webhook endpoint for long signals to all users with this strategy"""
    return await _process_broadcast(strategy_name, "long", request, background_tasks)

@app.post("/cast/{strategy_name}/short")
async def broadcast_webhook_short(strategy_name: str, request: Request, background_tasks: BackgroundTasks):
    """Broadcast webhook endpoint for short signals to all users with this strategy"""
    return await _process_broadcast(strategy_name, "short", request, background_tasks)

@app.post("/cast/{strategy_name}/close")
async def broadcast_webhook_close(strategy_name: str, request: Request, background_tasks: BackgroundTasks):
    """Broadcast webhook endpoint for close signals to all users with this strategy"""
    return await _process_broadcast(strategy_name, "close", request, background_tasks)

async def _process_webhook(strategy_name: str, signal: str, request: Request, background_tasks: BackgroundTasks, user_id: str = "default"):
    """Process webhook signal for a specific strategy and user"""
    try:
        client_ip = request.client.host if request.client else "unknown"
        logger.info(f"🔥 WEBHOOK RECEIVED: user={user_id} strategy={strategy_name} signal={signal} from_ip={client_ip}")
        
        # Validate user exists in environment variables
        if user_id.lower() != 'default' and not is_valid_user(user_id):
            error_response = {
                "status": "error",
                "error_type": "user_not_found",
                "message": f"User '{user_id}' does not exist. Users can only be created via environment variables."
            }
            logger.error(f"🔥 ERROR: user={user_id} does_not_exist webhook_ignored")
            return JSONResponse(status_code=404, content=error_response)
        
        # Get strategy for this user
        strategy = strategy_repo.get_strategy(strategy_name, user_id)
        
        # Auto-create strategy if it doesn't exist
        if not strategy:
            logger.info(f"🔥 AUTO-CREATE: user={user_id} strategy={strategy_name} signal={signal} auto_creating_strategy")
            try:
                strategy = strategy_repo.create_strategy(strategy_name, user_id)
                logger.info(f"🔥 AUTO-CREATE: user={user_id} strategy={strategy_name} created_successfully")
            except Exception as e:
                error_response = {
                    "status": "error",
                    "error_type": "strategy_creation_failed", 
                    "message": f"Failed to auto-create strategy '{strategy_name}' for user '{user_id}': {str(e)}"
                }
                logger.error(f"🔥 ERROR: user={user_id} strategy={strategy_name} auto_create_failed error={str(e)}")
                return JSONResponse(status_code=500, content=error_response)
        
        logger.info(f"🔥 STRATEGY LOOKUP: found user={user_id} strategy={strategy.name} symbols={strategy.long_symbol}/{strategy.short_symbol} cash={strategy.cash_balance}")
        
        # Process signal in background to avoid webhook timeout
        background_tasks.add_task(signal_processor.process_signal, signal, strategy)
        
        return {"status": "processing", "user": user_id, "strategy": strategy_name, "signal": signal}
        
    except Exception as e:
        logger.exception(f"🔥 ERROR: user={user_id} strategy={strategy_name} webhook_processing_error={str(e)}")
        return JSONResponse(
            status_code=500, 
            content={
                "status": "error",
                "error_type": "internal_error",
                "message": str(e),
                "help": "Check server logs for details"
            }
        )

async def _process_broadcast(strategy_name: str, signal: str, request: Request, background_tasks: BackgroundTasks):
    """Broadcast a signal to all users who have this strategy"""
    try:
        client_ip = request.client.host if request.client else "unknown"
        logger.info(f"🔥 BROADCAST RECEIVED: strategy={strategy_name} signal={signal} from_ip={client_ip}")
        
        # Get all valid users from environment variables
        valid_users = get_valid_users()
        if 'default' not in valid_users:
            valid_users.append('default')
            
        # Get users who have this strategy already
        users_with_strategy = strategy_repo.get_users_with_strategy(strategy_name)
        
        # If no users have this strategy yet, auto-create it for all valid users
        if not users_with_strategy:
            logger.info(f"🔥 BROADCAST AUTO-CREATE: strategy={strategy_name} no_existing_strategies creating_for_all_users")
            
            for user_id in valid_users:
                try:
                    strategy = strategy_repo.create_strategy(strategy_name, user_id)
                    users_with_strategy.append(user_id)
                    logger.info(f"🔥 AUTO-CREATE: user={user_id} strategy={strategy_name} created_successfully")
                except Exception as e:
                    logger.error(f"🔥 ERROR: user={user_id} strategy={strategy_name} auto_create_failed error={str(e)}")
        
        logger.info(f"🔥 BROADCAST: strategy={strategy_name} signal={signal} matched_users={len(users_with_strategy)}")
        
        # Process signals for each valid user in background tasks
        processed_count = 0
        for user_id in users_with_strategy:
            # Skip users that don't have an environment variable (except default)
            if user_id.lower() != 'default' and not is_valid_user(user_id):
                logger.warning(f"🔥 BROADCAST SKIP: user={user_id} strategy={strategy_name} reason=user_not_in_env_vars")
                continue
                
            strategy = strategy_repo.get_strategy(strategy_name, user_id)
            if strategy:
                # Process each user's strategy in a separate background task for isolation
                background_tasks.add_task(signal_processor.process_signal, signal, strategy)
                processed_count += 1
                logger.info(f"🔥 BROADCAST QUEUE: user={user_id} strategy={strategy_name} signal={signal} queued")
        
        return {
            "status": "broadcasting", 
            "strategy": strategy_name, 
            "signal": signal, 
            "user_count": processed_count,
            "users": users_with_strategy
        }
        
    except Exception as e:
        logger.exception(f"🔥 ERROR: broadcast strategy={strategy_name} signal={signal} error={str(e)}")
        return JSONResponse(
            status_code=500, 
            content={
                "status": "error",
                "error_type": "internal_error",
                "message": str(e),
                "help": "Check server logs for details"
            }
        )

# System status endpoint
@app.get("/status")
async def status():
    """Get system status"""
    all_users = get_valid_users()
    if 'default' not in all_users:
        all_users.append('default')
        
    strategies = strategy_repo.get_all_strategies()
    
    # Group strategies by user
    strategies_by_user = {}
    for user_id in all_users:
        user_strategies = strategy_repo.get_user_strategies(user_id)
        strategies_by_user[user_id] = [s.name for s in user_strategies]
    
    # Get webhook URLs
    webhook_urls = get_all_webhook_urls()
    webhook_user_info = [
        {"user_id": user_id, "has_webhook_url": True}
        for user_id in webhook_urls.keys()
    ]
    
    return {
        "status": "ok",
        "system": "multi-user-strategy-headless",
        "users": len(all_users),
        "users_with_webhook": len(webhook_urls),
        "strategies": len(strategies),
        "user_strategies": strategies_by_user,
        "webhook_users": webhook_user_info,
        "env_var_info": "Users can only be created/deleted via SIGNAL_STACK_WEBHOOK_URL_* environment variables"
    }

# System management endpoints
@app.post("/system/refresh-users")
async def refresh_users():
    """Refresh the list of users from environment variables"""
    try:
        # Refresh valid users in strategy repository
        strategy_repo.refresh_valid_users()
        
        # Get current user list
        valid_users = get_valid_users()
        if 'default' not in valid_users:
            valid_users.append('default')
        
        return {
            "status": "success",
            "message": "User list refreshed from environment variables",
            "users": valid_users,
            "count": len(valid_users)
        }
    except Exception as e:
        logger.exception(f"🔥 ERROR: refresh_users_error={str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", DASHBOARD_PORT))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
