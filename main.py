# main.py - Entry point, FastAPI setup - Environment-based user management with broadcast functionality
import logging
import os
from datetime import datetime
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Form, BackgroundTasks, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn
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
    logger.info("🔥 SYSTEM STARTUP: Multi-User Trading Webhook Service")
    
    # Log configured users from environment variables
    valid_users = get_valid_users()
    webhook_urls = get_all_webhook_urls()
    
    logger.info(f"🔥 USER MANAGEMENT: found {len(valid_users)} users in environment variables")
    for user_id in valid_users:
        logger.info(f"🔥 USER MANAGEMENT: found user={user_id} with webhook URL")
    
    yield
    
    # Shutdown event
    logger.info("🔥 SYSTEM SHUTDOWN: Multi-User Trading Webhook Service")

# Initialize FastAPI
app = FastAPI(title="Multi-User Trading Webhook Service", lifespan=lifespan)

# Setup templates and static files
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

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
        if not strategy:
            available_strategies = strategy_repo.get_strategy_names(user_id)
            error_response = {
                "status": "error",
                "error_type": "strategy_not_found", 
                "message": f"Strategy '{strategy_name}' not found for user '{user_id}'",
                "available_strategies": available_strategies,
                "help": "Create this strategy first or check the strategy name in your webhook URL"
            }
            logger.error(f"🔥 ERROR: user={user_id} strategy={strategy_name} not_found webhook_ignored")
            return JSONResponse(status_code=404, content=error_response)
        
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
        
        # Get all users who have this strategy - must be valid users from env vars
        users_with_strategy = strategy_repo.get_users_with_strategy(strategy_name)
        
        if not users_with_strategy:
            error_response = {
                "status": "error",
                "error_type": "no_matching_strategies", 
                "message": f"No users found with strategy '{strategy_name}'",
                "help": "Create this strategy for at least one user first"
            }
            logger.error(f"🔥 ERROR: broadcast strategy={strategy_name} no_matching_strategies broadcast_ignored")
            return JSONResponse(status_code=404, content=error_response)
        
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

# Strategy management endpoints
@app.post("/strategies")
async def create_strategy(
    name: str = Form(...),
    user_id: str = Form("default"),
    long_symbol: Optional[str] = Form(None),
    short_symbol: Optional[str] = Form(None),
    cash_balance: float = Form(0.0)
):
    """Create a new strategy"""
    try:
        # Clean up inputs
        user_id = user_id.strip() if user_id and user_id.strip() else "default"
        
        # Validate user exists in environment variables
        if user_id.lower() != 'default' and not is_valid_user(user_id):
            raise HTTPException(
                status_code=400, 
                detail=f"User '{user_id}' does not exist. Users can only be created via environment variables."
            )
        
        long_symbol = long_symbol.strip() if long_symbol and long_symbol.strip() else None
        short_symbol = short_symbol.strip() if short_symbol and short_symbol.strip() else None
        
        strategy = strategy_repo.create_strategy(name, user_id, long_symbol, short_symbol, cash_balance)
        return {"status": "success", "strategy": strategy.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception(f"🔥 ERROR: create_strategy_error={str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/strategies")
async def list_strategies(user_id: Optional[str] = None):
    """List all strategies, optionally filtered by user_id"""
    if user_id:
        # Validate user exists in environment variables
        if user_id.lower() != 'default' and not is_valid_user(user_id):
            return {
                "user_id": user_id,
                "error": "User does not exist. Users can only be created via environment variables.",
                "strategies": [],
                "count": 0
            }
            
        strategies = strategy_repo.get_user_strategies(user_id)
        return {
            "user_id": user_id,
            "strategies": [strategy.to_dict() for strategy in strategies],
            "count": len(strategies)
        }
    else:
        strategies = strategy_repo.get_all_strategies()
        return {
            "strategies": [strategy.to_dict() for strategy in strategies],
            "count": len(strategies)
        }

@app.get("/strategies/{name}")
async def get_strategy(name: str, user_id: str = "default"):
    """Get a specific strategy for a user"""
    # Validate user exists in environment variables
    if user_id.lower() != 'default' and not is_valid_user(user_id):
        raise HTTPException(
            status_code=404, 
            detail=f"User '{user_id}' does not exist. Users can only be created via environment variables."
        )
        
    strategy = strategy_repo.get_strategy(name, user_id)
    if not strategy:
        raise HTTPException(status_code=404, detail=f"Strategy '{name}' not found for user '{user_id}'")
    return {"strategy": strategy.to_dict()}

@app.put("/strategies/{name}")
async def update_strategy(
    name: str,
    user_id: str = Form("default"),
    long_symbol: Optional[str] = Form(None),
    short_symbol: Optional[str] = Form(None),
    cash_balance: Optional[float] = Form(None)
):
    """Update a strategy"""
    try:
        # Clean up inputs
        user_id = user_id.strip() if user_id and user_id.strip() else "default"
        
        # Validate user exists in environment variables
        if user_id.lower() != 'default' and not is_valid_user(user_id):
            raise HTTPException(
                status_code=404, 
                detail=f"User '{user_id}' does not exist. Users can only be created via environment variables."
            )
            
        if long_symbol is not None:
            long_symbol = long_symbol.strip() if long_symbol.strip() else None
        if short_symbol is not None:
            short_symbol = short_symbol.strip() if short_symbol.strip() else None
        
        strategy = strategy_repo.update_strategy(name, user_id, long_symbol, short_symbol, cash_balance)
        if not strategy:
            raise HTTPException(status_code=404, detail=f"Strategy '{name}' not found for user '{user_id}'")
        return {"status": "success", "strategy": strategy.to_dict()}
    except Exception as e:
        logger.exception(f"🔥 ERROR: update_strategy_error={str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/strategies/{name}")
async def delete_strategy(name: str, user_id: str = "default"):
    """Delete a strategy"""
    # Validate user exists in environment variables
    if user_id.lower() != 'default' and not is_valid_user(user_id):
        raise HTTPException(
            status_code=404, 
            detail=f"User '{user_id}' does not exist. Users can only be created via environment variables."
        )
        
    success = strategy_repo.delete_strategy(name, user_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Strategy '{name}' not found for user '{user_id}'")
    return {"status": "success", "message": f"Strategy '{name}' deleted for user '{user_id}'"}

# User management endpoints
@app.get("/users")
async def list_users():
    """List all users from environment variables"""
    users = get_valid_users()
    # Always include default user
    if 'default' not in users:
        users.append('default')
    
    # Get webhook URLs for all users
    webhook_urls = get_all_webhook_urls()
    
    # Format user info
    user_info = []
    for user_id in users:
        # Get strategies for this user
        strategies = strategy_repo.get_user_strategies(user_id)
        
        # Add user info
        user_info.append({
            "user_id": user_id,
            "has_webhook_url": user_id.lower() == 'default' or user_id.lower() in webhook_urls,
            "strategy_count": len(strategies),
            "strategies": [s.name for s in strategies]
        })
    
    return {
        "users": user_info,
        "count": len(user_info),
        "env_var_info": "Users can only be created/deleted via SIGNAL_STACK_WEBHOOK_URL_* environment variables"
    }

@app.get("/users/{user_id}")
async def get_user_strategies(user_id: str):
    """Get all strategies for a specific user"""
    # Validate user exists in environment variables
    if user_id.lower() != 'default' and not is_valid_user(user_id):
        return {
            "user_id": user_id,
            "error": "User does not exist. Users can only be created via environment variables.",
            "has_webhook_url": False,
            "strategies": [],
            "count": 0
        }
        
    strategies = strategy_repo.get_user_strategies(user_id)
    return {
        "user_id": user_id,
        "has_webhook_url": user_id.lower() == 'default' or is_valid_user(user_id),
        "strategies": [strategy.to_dict() for strategy in strategies],
        "count": len(strategies)
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

# Strategy-specific operations
@app.post("/strategies/{name}/update-symbols")
async def update_strategy_symbols(
    name: str,
    user_id: str = Form("default"),
    long_symbol: Optional[str] = Form(""),
    short_symbol: Optional[str] = Form("")
):
    """Update symbols for a specific strategy"""
    try:
        # Clean up inputs
        user_id = user_id.strip() if user_id and user_id.strip() else "default"
        
        # Validate user exists in environment variables
        if user_id.lower() != 'default' and not is_valid_user(user_id):
            raise HTTPException(
                status_code=404, 
                detail=f"User '{user_id}' does not exist. Users can only be created via environment variables."
            )
            
        long_symbol = long_symbol.strip() if long_symbol.strip() else None
        short_symbol = short_symbol.strip() if short_symbol.strip() else None
        
        strategy = strategy_repo.update_strategy_symbols_both(name, user_id, long_symbol, short_symbol)
        if not strategy:
            raise HTTPException(status_code=404, detail=f"Strategy '{name}' not found for user '{user_id}'")
        return {"status": "success", "strategy": strategy.to_dict()}
    except Exception as e:
        logger.exception(f"🔥 ERROR: update_symbols_error={str(e)}")
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/strategies/{name}/update-cash")
async def update_strategy_cash(
    name: str, 
    cash_amount: float = Form(...),
    user_id: str = Form("default")
):
    """Update cash balance for a specific strategy"""
    try:
        user_id = user_id.strip() if user_id and user_id.strip() else "default"
        
        # Validate user exists in environment variables
        if user_id.lower() != 'default' and not is_valid_user(user_id):
            raise HTTPException(
                status_code=404, 
                detail=f"User '{user_id}' does not exist. Users can only be created via environment variables."
            )
            
        strategy = strategy_repo.get_strategy(name, user_id)
        if not strategy:
            raise HTTPException(status_code=404, detail=f"Strategy '{name}' not found for user '{user_id}'")
        
        success = cash_manager.update_balance_manual(cash_amount, strategy)
        if not success:
            raise HTTPException(status_code=400, detail="Invalid cash amount")
        
        return {"status": "success", "strategy": strategy.to_dict()}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"🔥 ERROR: update_cash_error={str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/strategies/{name}/start-cooldown")
async def start_strategy_cooldown(name: str, user_id: str = Form("default")):
    """Start cooldown for a specific strategy"""
    try:
        user_id = user_id.strip() if user_id and user_id.strip() else "default"
        
        # Validate user exists in environment variables
        if user_id.lower() != 'default' and not is_valid_user(user_id):
            raise HTTPException(
                status_code=404, 
                detail=f"User '{user_id}' does not exist. Users can only be created via environment variables."
            )
            
        strategy = strategy_repo.get_strategy(name, user_id)
        if not strategy:
            raise HTTPException(status_code=404, detail=f"Strategy '{name}' not found for user '{user_id}'")
        
        cooldown_manager.start_cooldown(strategy)
        return {"status": "success", "strategy": strategy.to_dict()}
    except Exception as e:
        logger.exception(f"🔥 ERROR: start_cooldown_error={str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/strategies/{name}/stop-cooldown")
async def stop_strategy_cooldown(name: str, user_id: str = Form("default")):
    """Stop cooldown for a specific strategy"""
    try:
        user_id = user_id.strip() if user_id and user_id.strip() else "default"
        
        # Validate user exists in environment variables
        if user_id.lower() != 'default' and not is_valid_user(user_id):
            raise HTTPException(
                status_code=404, 
                detail=f"User '{user_id}' does not exist. Users can only be created via environment variables."
            )
            
        strategy = strategy_repo.get_strategy(name, user_id)
        if not strategy:
            raise HTTPException(status_code=404, detail=f"Strategy '{name}' not found for user '{user_id}'")
        
        cooldown_manager.stop_cooldown(strategy)
        return {"status": "success", "strategy": strategy.to_dict()}
    except Exception as e:
        logger.exception(f"🔥 ERROR: stop_cooldown_error={str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/strategies/{name}/force-long")
async def force_strategy_long(name: str, user_id: str = Form("default"), background_tasks: BackgroundTasks = None):
    """Force long position for a specific strategy"""
    try:
        if background_tasks is None:
            background_tasks = BackgroundTasks()
            
        user_id = user_id.strip() if user_id and user_id.strip() else "default"
        
        # Validate user exists in environment variables
        if user_id.lower() != 'default' and not is_valid_user(user_id):
            raise HTTPException(
                status_code=404, 
                detail=f"User '{user_id}' does not exist. Users can only be created via environment variables."
            )
            
        strategy = strategy_repo.get_strategy(name, user_id)
        if not strategy:
            raise HTTPException(status_code=404, detail=f"Strategy '{name}' not found for user '{user_id}'")
        
        if strategy.is_processing:
            return {"status": "error", "message": "Strategy is already processing a signal"}
        
        background_tasks.add_task(signal_processor.force_long, strategy)
        return {"status": "success", "message": f"Force long initiated for user '{user_id}' strategy '{name}'"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"🔥 ERROR: force_long_error={str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/strategies/{name}/force-short")
async def force_strategy_short(name: str, user_id: str = Form("default"), background_tasks: BackgroundTasks = None):
    """Force short position for a specific strategy"""
    try:
        if background_tasks is None:
            background_tasks = BackgroundTasks()
            
        user_id = user_id.strip() if user_id and user_id.strip() else "default"
        
        # Validate user exists in environment variables
        if user_id.lower() != 'default' and not is_valid_user(user_id):
            raise HTTPException(
                status_code=404, 
                detail=f"User '{user_id}' does not exist. Users can only be created via environment variables."
            )
            
        strategy = strategy_repo.get_strategy(name, user_id)
        if not strategy:
            raise HTTPException(status_code=404, detail=f"Strategy '{name}' not found for user '{user_id}'")
        
        if strategy.is_processing:
            return {"status": "error", "message": "Strategy is already processing a signal"}
        
        background_tasks.add_task(signal_processor.force_short, strategy)
        return {"status": "success", "message": f"Force short initiated for user '{user_id}' strategy '{name}'"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"🔥 ERROR: force_short_error={str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/strategies/{name}/force-close")
async def force_strategy_close(name: str, user_id: str = Form("default"), background_tasks: BackgroundTasks = None):
    """Force close all positions for a specific strategy"""
    try:
        if background_tasks is None:
            background_tasks = BackgroundTasks()
            
        user_id = user_id.strip() if user_id and user_id.strip() else "default"
        
        # Validate user exists in environment variables
        if user_id.lower() != 'default' and not is_valid_user(user_id):
            raise HTTPException(
                status_code=404, 
                detail=f"User '{user_id}' does not exist. Users can only be created via environment variables."
            )
            
        strategy = strategy_repo.get_strategy(name, user_id)
        if not strategy:
            raise HTTPException(status_code=404, detail=f"Strategy '{name}' not found for user '{user_id}'")
        
        if strategy.is_processing:
            return {"status": "error", "message": "Strategy is already processing a signal"}
        
        background_tasks.add_task(signal_processor.force_close, strategy)
        return {"status": "success", "message": f"Force close initiated for user '{user_id}' strategy '{name}'"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"🔥 ERROR: force_close_error={str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Broadcast force operations
@app.post("/cast/{strategy_name}/force-long")
async def broadcast_force_long(strategy_name: str, background_tasks: BackgroundTasks):
    """Broadcast force long to all users with this strategy"""
    try:
        # Get all users who have this strategy
        users_with_strategy = strategy_repo.get_users_with_strategy(strategy_name)
        
        if not users_with_strategy:
            raise HTTPException(status_code=404, detail=f"No users found with strategy '{strategy_name}'")
        
        logger.info(f"🔥 BROADCAST FORCE: action=long strategy={strategy_name} matched_users={len(users_with_strategy)}")
        
        # Process signals for each valid user in background tasks
        processed_count = 0
        for user_id in users_with_strategy:
            # Skip users that don't have an environment variable (except default)
            if user_id.lower() != 'default' and not is_valid_user(user_id):
                logger.warning(f"🔥 BROADCAST SKIP: user={user_id} strategy={strategy_name} reason=user_not_in_env_vars")
                continue
                
            strategy = strategy_repo.get_strategy(strategy_name, user_id)
            if strategy and not strategy.is_processing:
                # Process each user's strategy in a separate background task for isolation
                background_tasks.add_task(signal_processor.force_long, strategy)
                processed_count += 1
                logger.info(f"🔥 BROADCAST FORCE QUEUE: user={user_id} strategy={strategy_name} action=long queued")
        
        return {
            "status": "broadcasting", 
            "action": "force_long",
            "strategy": strategy_name, 
            "user_count": processed_count,
            "users": users_with_strategy
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"🔥 ERROR: broadcast_force_long_error={str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/cast/{strategy_name}/force-short")
async def broadcast_force_short(strategy_name: str, background_tasks: BackgroundTasks):
    """Broadcast force short to all users with this strategy"""
    try:
        # Get all users who have this strategy
        users_with_strategy = strategy_repo.get_users_with_strategy(strategy_name)
        
        if not users_with_strategy:
            raise HTTPException(status_code=404, detail=f"No users found with strategy '{strategy_name}'")
        
        logger.info(f"🔥 BROADCAST FORCE: action=short strategy={strategy_name} matched_users={len(users_with_strategy)}")
        
        # Process signals for each valid user in background tasks
        processed_count = 0
        for user_id in users_with_strategy:
            # Skip users that don't have an environment variable (except default)
            if user_id.lower() != 'default' and not is_valid_user(user_id):
                logger.warning(f"🔥 BROADCAST SKIP: user={user_id} strategy={strategy_name} reason=user_not_in_env_vars")
                continue
                
            strategy = strategy_repo.get_strategy(strategy_name, user_id)
            if strategy and not strategy.is_processing:
                # Process each user's strategy in a separate background task for isolation
                background_tasks.add_task(signal_processor.force_short, strategy)
                processed_count += 1
                logger.info(f"🔥 BROADCAST FORCE QUEUE: user={user_id} strategy={strategy_name} action=short queued")
        
        return {
            "status": "broadcasting", 
            "action": "force_short",
            "strategy": strategy_name, 
            "user_count": processed_count,
            "users": users_with_strategy
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"🔥 ERROR: broadcast_force_short_error={str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/cast/{strategy_name}/force-close")
async def broadcast_force_close(strategy_name: str, background_tasks: BackgroundTasks):
    """Broadcast force close to all users with this strategy"""
    try:
        # Get all users who have this strategy
        users_with_strategy = strategy_repo.get_users_with_strategy(strategy_name)
        
        if not users_with_strategy:
            raise HTTPException(status_code=404, detail=f"No users found with strategy '{strategy_name}'")
        
        logger.info(f"🔥 BROADCAST FORCE: action=close strategy={strategy_name} matched_users={len(users_with_strategy)}")
        
        # Process signals for each valid user in background tasks
        processed_count = 0
        for user_id in users_with_strategy:
            # Skip users that don't have an environment variable (except default)
            if user_id.lower() != 'default' and not is_valid_user(user_id):
                logger.warning(f"🔥 BROADCAST SKIP: user={user_id} strategy={strategy_name} reason=user_not_in_env_vars")
                continue
                
            strategy = strategy_repo.get_strategy(strategy_name, user_id)
            if strategy and not strategy.is_processing:
                # Process each user's strategy in a separate background task for isolation
                background_tasks.add_task(signal_processor.force_close, strategy)
                processed_count += 1
                logger.info(f"🔥 BROADCAST FORCE QUEUE: user={user_id} strategy={strategy_name} action=close queued")
        
        return {
            "status": "broadcasting", 
            "action": "force_close",
            "strategy": strategy_name, 
            "user_count": processed_count,
            "users": users_with_strategy
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"🔥 ERROR: broadcast_force_close_error={str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Dashboard endpoints
@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, user_id: Optional[str] = None):
    """Multi-strategy dashboard with optional user filter"""
    
    # Get all valid users for the dropdown (from environment variables)
    all_users = get_valid_users()
    if 'default' not in all_users:
        all_users.append('default')
    
    # If user_id is provided, validate and filter strategies for that user
    if user_id:
        if user_id.lower() != 'default' and not is_valid_user(user_id):
            return templates.TemplateResponse(
                "index.html", 
                {
                    "request": request,
                    "strategies": [],
                    "all_users": all_users,
                    "selected_user": user_id,
                    "error": f"User '{user_id}' does not exist. Users can only be created via environment variables."
                }
            )
            
        strategies = strategy_repo.get_user_strategies(user_id)
        selected_user = user_id
    else:
        # Otherwise, show all strategies for valid users
        strategies = strategy_repo.get_all_strategies()
        selected_user = None
    
    # Get webhook URLs for all valid users
    webhook_urls = get_all_webhook_urls()
    
    return templates.TemplateResponse(
        "index.html", 
        {
            "request": request,
            "strategies": [strategy.to_dict() for strategy in strategies],
            "all_users": all_users,
            "webhook_urls": webhook_urls,
            "selected_user": selected_user
        }
    )

# Legacy compatibility and utility endpoints
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
        "system": "multi-user-strategy",
        "users": len(all_users),
        "users_with_webhook": len(webhook_urls),
        "strategies": len(strategies),
        "user_strategies": strategies_by_user,
        "webhook_users": webhook_user_info,
        "env_var_info": "Users can only be created/deleted via SIGNAL_STACK_WEBHOOK_URL_* environment variables"
    }

@app.post("/debug")
async def debug_log(request: Request):
    """Debug endpoint to log JavaScript activity"""
    try:
        payload = await request.json()
        message = payload.get("message", "No message")
        logger.info(f"🔥 JAVASCRIPT DEBUG: {message}")
        return {"status": "logged", "message": message}
    except Exception as e:
        logger.info(f"🔥 JAVASCRIPT DEBUG (text): {await request.body()}")
        return {"status": "logged"}

@app.get("/debug-test")
async def debug_test():
    """Simple debug test endpoint"""
    logger.info("🔥 DEBUG TEST ENDPOINT CALLED - JavaScript is working!")
    return {"status": "success", "message": "Debug test successful"}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", DASHBOARD_PORT))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
