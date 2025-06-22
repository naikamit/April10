# main.py - Entry point, FastAPI setup (environment-based multi-user with new webhook structure)
import logging
import os
import asyncio
from datetime import datetime
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Form, BackgroundTasks, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn
from typing import Optional

from config import DASHBOARD_PORT, get_available_users, user_exists, get_users_from_environment
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
    available_users = get_available_users()
    logger.info(f"🔥 SYSTEM STARTUP: Environment-Based Multi-User Trading Webhook Service")
    logger.info(f"🔥 AVAILABLE USERS: {', '.join(available_users) if available_users else 'None configured'}")
    logger.info(f"🔥 WEBHOOK STRUCTURE: User-specific: /{{username}}/{{strategy}}/{{signal}} | Broadcast: /cast/{{strategy}}/{{signal}}")
    yield
    # Shutdown event
    logger.info("🔥 SYSTEM SHUTDOWN: Environment-Based Multi-User Trading Webhook Service")

# Initialize FastAPI
app = FastAPI(title="Environment-Based Multi-User Trading Webhook Service", lifespan=lifespan)

# Setup templates and static files
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# User-specific webhook endpoints
@app.post("/{username}/{strategy_name}/long")
async def webhook_user_long(username: str, strategy_name: str, request: Request, background_tasks: BackgroundTasks):
    """User-specific webhook endpoint for long signals"""
    return await _process_user_webhook(username, strategy_name, "long", request, background_tasks)

@app.post("/{username}/{strategy_name}/short")
async def webhook_user_short(username: str, strategy_name: str, request: Request, background_tasks: BackgroundTasks):
    """User-specific webhook endpoint for short signals"""
    return await _process_user_webhook(username, strategy_name, "short", request, background_tasks)

@app.post("/{username}/{strategy_name}/close")
async def webhook_user_close(username: str, strategy_name: str, request: Request, background_tasks: BackgroundTasks):
    """User-specific webhook endpoint for close signals"""
    return await _process_user_webhook(username, strategy_name, "close", request, background_tasks)

# Broadcast webhook endpoints
@app.post("/cast/{strategy_name}/long")
async def webhook_broadcast_long(strategy_name: str, request: Request, background_tasks: BackgroundTasks):
    """Broadcast webhook endpoint for long signals (all users with this strategy)"""
    return await _process_broadcast_webhook(strategy_name, "long", request, background_tasks)

@app.post("/cast/{strategy_name}/short")
async def webhook_broadcast_short(strategy_name: str, request: Request, background_tasks: BackgroundTasks):
    """Broadcast webhook endpoint for short signals (all users with this strategy)"""
    return await _process_broadcast_webhook(strategy_name, "short", request, background_tasks)

@app.post("/cast/{strategy_name}/close")
async def webhook_broadcast_close(strategy_name: str, request: Request, background_tasks: BackgroundTasks):
    """Broadcast webhook endpoint for close signals (all users with this strategy)"""
    return await _process_broadcast_webhook(strategy_name, "close", request, background_tasks)

async def _process_user_webhook(username: str, strategy_name: str, signal: str, request: Request, background_tasks: BackgroundTasks):
    """Process webhook signal for a specific user's strategy"""
    try:
        client_ip = request.client.host if request.client else "unknown"
        logger.info(f"🔥 USER WEBHOOK RECEIVED: user={username} strategy={strategy_name} signal={signal} from_ip={client_ip}")
        
        # Check if user exists
        if not user_exists(username):
            available_users = get_available_users()
            error_response = {
                "status": "error",
                "error_type": "user_not_found", 
                "message": f"User '{username}' not found",
                "available_users": available_users,
                "help": "Check the username in your webhook URL or configure this user's environment variable"
            }
            logger.error(f"🔥 ERROR: user={username} not_found webhook_ignored")
            return JSONResponse(status_code=404, content=error_response)
        
        # Get user's specific strategy
        strategy = strategy_repo.get_strategy_by_owner_and_name(username, strategy_name)
        if not strategy:
            user_strategies = strategy_repo.get_strategies_by_owner(username)
            error_response = {
                "status": "error",
                "error_type": "strategy_not_found", 
                "message": f"Strategy '{strategy_name}' not found for user '{username}'",
                "user_strategies": [s.name for s in user_strategies],
                "help": "Create this strategy first or check the strategy name in your webhook URL"
            }
            logger.error(f"🔥 ERROR: user={username} strategy={strategy_name} not_found webhook_ignored")
            return JSONResponse(status_code=404, content=error_response)
        
        logger.info(f"🔥 USER STRATEGY LOOKUP: found strategy={strategy.name} owner={strategy.owner} symbols={strategy.long_symbol}/{strategy.short_symbol} cash={strategy.cash_balance}")
        
        # Process signal in background to avoid webhook timeout
        background_tasks.add_task(signal_processor.process_signal, signal, strategy)
        
        return {"status": "processing", "user": username, "strategy": strategy_name, "signal": signal}
        
    except Exception as e:
        logger.exception(f"🔥 ERROR: user={username} strategy={strategy_name} webhook_processing_error={str(e)}")
        return JSONResponse(
            status_code=500, 
            content={
                "status": "error",
                "error_type": "internal_error",
                "message": str(e),
                "help": "Check server logs for details"
            }
        )

async def _process_broadcast_webhook(strategy_name: str, signal: str, request: Request, background_tasks: BackgroundTasks):
    """Process webhook signal for all users with the same strategy name"""
    try:
        client_ip = request.client.host if request.client else "unknown"
        logger.info(f"🔥 BROADCAST WEBHOOK RECEIVED: strategy={strategy_name} signal={signal} from_ip={client_ip}")
        
        # Get all strategies with this name across all users
        strategies = strategy_repo.get_strategies_by_name(strategy_name)
        if not strategies:
            all_strategy_names = set()
            all_strategies = strategy_repo.get_all_strategies()
            for s in all_strategies:
                all_strategy_names.add(s.name)
            
            error_response = {
                "status": "error",
                "error_type": "strategy_not_found", 
                "message": f"No strategies named '{strategy_name}' found across any users",
                "available_strategies": sorted(list(all_strategy_names)),
                "help": "Create strategies with this name first or check the strategy name in your webhook URL"
            }
            logger.error(f"🔥 ERROR: broadcast strategy={strategy_name} not_found webhook_ignored")
            return JSONResponse(status_code=404, content=error_response)
        
        logger.info(f"🔥 BROADCAST STRATEGY LOOKUP: found {len(strategies)} strategies named '{strategy_name}' across users: {[s.owner for s in strategies]}")
        
        # Log each strategy being processed
        for strategy in strategies:
            logger.info(f"🔥 BROADCAST PROCESSING: strategy={strategy.name} owner={strategy.owner} symbols={strategy.long_symbol}/{strategy.short_symbol} cash={strategy.cash_balance}")
        
        # Process signals in parallel for all matching strategies
        background_tasks.add_task(_process_broadcast_signals_parallel, signal, strategies)
        
        return {
            "status": "processing", 
            "strategy": strategy_name, 
            "signal": signal,
            "target_count": len(strategies),
            "target_users": [s.owner for s in strategies]
        }
        
    except Exception as e:
        logger.exception(f"🔥 ERROR: broadcast strategy={strategy_name} webhook_processing_error={str(e)}")
        return JSONResponse(
            status_code=500, 
            content={
                "status": "error",
                "error_type": "internal_error",
                "message": str(e),
                "help": "Check server logs for details"
            }
        )

async def _process_broadcast_signals_parallel(signal: str, strategies):
    """Process signal for multiple strategies in parallel"""
    logger.info(f"🔥 BROADCAST PARALLEL: starting signal={signal} for {len(strategies)} strategies")
    
    # Create tasks for each strategy
    tasks = []
    for strategy in strategies:
        logger.info(f"🔥 BROADCAST PARALLEL: queuing strategy={strategy.name} owner={strategy.owner}")
        task = asyncio.create_task(signal_processor.process_signal(signal, strategy))
        tasks.append(task)
    
    # Wait for all signals to complete in parallel
    try:
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Log results
        success_count = 0
        error_count = 0
        for i, result in enumerate(results):
            strategy = strategies[i]
            if isinstance(result, Exception):
                logger.error(f"🔥 BROADCAST PARALLEL ERROR: strategy={strategy.name} owner={strategy.owner} error={str(result)}")
                error_count += 1
            else:
                logger.info(f"🔥 BROADCAST PARALLEL SUCCESS: strategy={strategy.name} owner={strategy.owner} result={result}")
                success_count += 1
        
        logger.info(f"🔥 BROADCAST PARALLEL COMPLETE: signal={signal} success={success_count} errors={error_count} total={len(strategies)}")
        
    except Exception as e:
        logger.exception(f"🔥 ERROR: broadcast parallel processing failed: {str(e)}")

# Root route - show available users
@app.get("/", response_class=HTMLResponse)
async def root():
    """Show available users or redirect if only one user"""
    available_users = get_available_users()
    users_data = get_users_from_environment()
    
    if len(available_users) == 1:
        # If only one user, redirect to their dashboard
        return RedirectResponse(url=f"/{available_users[0]}", status_code=302)
    elif len(available_users) == 0:
        # No users configured
        return HTMLResponse(f"""
        <html>
            <head>
                <title>RetardTrader</title>
                <link rel="stylesheet" href="/static/style.css">
            </head>
            <body style="font-family: Arial; margin: 40px; background: #0f172a; color: #e4e4e7;">
                <div class="container">
                    <h1>No Users Configured</h1>
                    <p>To add users, set environment variables like:</p>
                    <ul>
                        <li><code>SIGNAL_STACK_WEBHOOK_URL_AMIT=https://your-webhook-url</code></li>
                        <li><code>SIGNAL_STACK_WEBHOOK_URL_JOHN=https://your-webhook-url</code></li>
                    </ul>
                    <p>Then restart the service.</p>
                </div>
            </body>
        </html>
        """)
    else:
        # Multiple users - show selection
        user_links = ''.join(
            f'<div class="user-card"><a href="/{user}" class="user-link">{user}</a></div>' 
            for user in sorted(available_users)
        )
        return HTMLResponse(f"""
        <html>
            <head>
                <title>RetardTrader</title>
                <link rel="stylesheet" href="/static/style.css">
            </head>
            <body>
                <div class="container">
                    <h1>Select User</h1>
                    <div class="users-grid">
                        {user_links}
                    </div>
                    <div style="margin-top: 30px; text-align: center; color: #94a3b8;">
                        <p>{len(available_users)} users available</p>
                    </div>
                </div>
                <style>
                .users-grid {{
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                    gap: 20px;
                    margin: 30px 0;
                }}
                .user-card {{
                    background: #1e293b;
                    border-radius: 8px;
                    padding: 0;
                    border: 1px solid #374151;
                    transition: all 0.3s;
                }}
                .user-card:hover {{
                    border-color: #60a5fa;
                    transform: translateY(-2px);
                    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
                }}
                .user-link {{
                    display: block;
                    padding: 30px 20px;
                    color: #e4e4e7;
                    text-decoration: none;
                    font-size: 1.2rem;
                    font-weight: 500;
                    text-align: center;
                    transition: color 0.3s;
                }}
                .user-link:hover {{
                    color: #60a5fa;
                }}
                </style>
            </body>
        </html>
        """)

# User-specific dashboard
@app.get("/{username}", response_class=HTMLResponse)
async def user_dashboard(username: str, request: Request):
    """User-specific dashboard showing all strategies for a user"""
    try:
        # Check if user exists (has environment variable configured)
        if not user_exists(username):
            available_users = get_available_users()
            return HTMLResponse(f"""
            <html>
                <head>
                    <title>User Not Found - RetardTrader</title>
                    <link rel="stylesheet" href="/static/style.css">
                </head>
                <body>
                    <div class="container">
                        <div class="empty-state">
                            <h2>User "{username}" Not Found</h2>
                            <p>This user is not configured in the system.</p>
                            <p>To add this user, set the environment variable:</p>
                            <code style="background: #334155; padding: 10px; border-radius: 4px; display: block; margin: 20px 0;">
                                SIGNAL_STACK_WEBHOOK_URL_{username.upper()}=https://your-webhook-url
                            </code>
                            {"<h3>Available Users:</h3>" if available_users else "<p>No users currently configured.</p>"}
                            {"".join(f'<div style=\"margin: 10px 0;\"><a href=\"/{user}\" style=\"color: #60a5fa;\">{user}</a></div>' for user in available_users) if available_users else ""}
                            <div style="margin-top: 30px;">
                                <a href="/" style="color: #60a5fa; text-decoration: none;">&larr; Back to Home</a>
                            </div>
                        </div>
                    </div>
                </body>
            </html>
            """, status_code=404)
        
        # Get strategies for this user
        user_strategies = strategy_repo.get_strategies_by_owner(username)
        
        return templates.TemplateResponse(
            "index.html", 
            {
                "request": request,
                "username": username,
                "strategies": [strategy.to_dict() for strategy in user_strategies]
            }
        )
    except Exception as e:
        logger.exception(f"🔥 ERROR: user_dashboard_error username={username} error={str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Strategy management endpoints (moved to /api/ prefix)
@app.post("/api/strategies")
async def create_strategy(
    name: str = Form(...),
    owner: str = Form(...),
    long_symbol: Optional[str] = Form(None),
    short_symbol: Optional[str] = Form(None),
    cash_balance: float = Form(0.0)
):
    """Create a new strategy"""
    try:
        # Validate that the owner exists (has environment variable configured)
        if not user_exists(owner):
            available_users = get_available_users()
            raise HTTPException(
                status_code=400, 
                detail=f"User '{owner}' is not configured. Available users: {', '.join(available_users) if available_users else 'None'}"
            )
        
        # Clean up symbol inputs
        long_symbol = long_symbol.strip() if long_symbol and long_symbol.strip() else None
        short_symbol = short_symbol.strip() if short_symbol and short_symbol.strip() else None
        
        strategy = strategy_repo.create_strategy(name, owner, long_symbol, short_symbol, cash_balance)
        return {"status": "success", "strategy": strategy.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"🔥 ERROR: create_strategy_error={str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/strategies")
async def list_strategies():
    """List all strategies"""
    strategies = strategy_repo.get_all_strategies()
    return {
        "strategies": [strategy.to_dict() for strategy in strategies],
        "count": len(strategies)
    }

@app.get("/api/strategies/{name}")
async def get_strategy(name: str):
    """Get a specific strategy"""
    strategy = strategy_repo.get_strategy(name)
    if not strategy:
        raise HTTPException(status_code=404, detail=f"Strategy '{name}' not found")
    return {"strategy": strategy.to_dict()}

@app.put("/api/strategies/{name}")
async def update_strategy(
    name: str,
    long_symbol: Optional[str] = Form(None),
    short_symbol: Optional[str] = Form(None),
    cash_balance: Optional[float] = Form(None)
):
    """Update a strategy"""
    try:
        # Clean up symbol inputs
        if long_symbol is not None:
            long_symbol = long_symbol.strip() if long_symbol.strip() else None
        if short_symbol is not None:
            short_symbol = short_symbol.strip() if short_symbol.strip() else None
        
        strategy = strategy_repo.update_strategy(name, long_symbol, short_symbol, cash_balance)
        if not strategy:
            raise HTTPException(status_code=404, detail=f"Strategy '{name}' not found")
        return {"status": "success", "strategy": strategy.to_dict()}
    except Exception as e:
        logger.exception(f"🔥 ERROR: update_strategy_error={str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/strategies/{name}")
async def delete_strategy(name: str):
    """Delete a strategy"""
    success = strategy_repo.delete_strategy(name)
    if not success:
        raise HTTPException(status_code=404, detail=f"Strategy '{name}' not found")
    return {"status": "success", "message": f"Strategy '{name}' deleted"}

# Strategy-specific operations (moved to /api/ prefix)
@app.post("/api/strategies/{name}/update-symbols")
async def update_strategy_symbols(
    name: str,
    long_symbol: Optional[str] = Form(""),
    short_symbol: Optional[str] = Form("")
):
    """Update symbols for a specific strategy"""
    try:
        # Clean up inputs
        long_symbol = long_symbol.strip() if long_symbol.strip() else None
        short_symbol = short_symbol.strip() if short_symbol.strip() else None
        
        strategy = strategy_repo.update_strategy_symbols_both(name, long_symbol, short_symbol)
        if not strategy:
            raise HTTPException(status_code=404, detail=f"Strategy '{name}' not found")
        return {"status": "success", "strategy": strategy.to_dict()}
    except Exception as e:
        logger.exception(f"🔥 ERROR: update_symbols_error={str(e)}")
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/strategies/{name}/update-cash")
async def update_strategy_cash(name: str, cash_amount: float = Form(...)):
    """Update cash balance for a specific strategy"""
    try:
        strategy = strategy_repo.get_strategy(name)
        if not strategy:
            raise HTTPException(status_code=404, detail=f"Strategy '{name}' not found")
        
        success = cash_manager.update_balance_manual(cash_amount, strategy)
        if not success:
            raise HTTPException(status_code=400, detail="Invalid cash amount")
        
        return {"status": "success", "strategy": strategy.to_dict()}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"🔥 ERROR: update_cash_error={str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/strategies/{name}/start-cooldown")
async def start_strategy_cooldown(name: str):
    """Start cooldown for a specific strategy"""
    try:
        strategy = strategy_repo.get_strategy(name)
        if not strategy:
            raise HTTPException(status_code=404, detail=f"Strategy '{name}' not found")
        
        cooldown_manager.start_cooldown(strategy)
        return {"status": "success", "strategy": strategy.to_dict()}
    except Exception as e:
        logger.exception(f"🔥 ERROR: start_cooldown_error={str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/strategies/{name}/stop-cooldown")
async def stop_strategy_cooldown(name: str):
    """Stop cooldown for a specific strategy"""
    try:
        strategy = strategy_repo.get_strategy(name)
        if not strategy:
            raise HTTPException(status_code=404, detail=f"Strategy '{name}' not found")
        
        cooldown_manager.stop_cooldown(strategy)
        return {"status": "success", "strategy": strategy.to_dict()}
    except Exception as e:
        logger.exception(f"🔥 ERROR: stop_cooldown_error={str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/strategies/{name}/force-long")
async def force_strategy_long(name: str, background_tasks: BackgroundTasks):
    """Force long position for a specific strategy"""
    try:
        strategy = strategy_repo.get_strategy(name)
        if not strategy:
            raise HTTPException(status_code=404, detail=f"Strategy '{name}' not found")
        
        if strategy.is_processing:
            return {"status": "error", "message": "Strategy is already processing a signal"}
        
        background_tasks.add_task(signal_processor.force_long, strategy)
        return {"status": "success", "message": f"Force long initiated for strategy '{name}'"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"🔥 ERROR: force_long_error={str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/strategies/{name}/force-short")
async def force_strategy_short(name: str, background_tasks: BackgroundTasks):
    """Force short position for a specific strategy"""
    try:
        strategy = strategy_repo.get_strategy(name)
        if not strategy:
            raise HTTPException(status_code=404, detail=f"Strategy '{name}' not found")
        
        if strategy.is_processing:
            return {"status": "error", "message": "Strategy is already processing a signal"}
        
        background_tasks.add_task(signal_processor.force_short, strategy)
        return {"status": "success", "message": f"Force short initiated for strategy '{name}'"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"🔥 ERROR: force_short_error={str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/strategies/{name}/force-close")
async def force_strategy_close(name: str, background_tasks: BackgroundTasks):
    """Force close all positions for a specific strategy"""
    try:
        strategy = strategy_repo.get_strategy(name)
        if not strategy:
            raise HTTPException(status_code=404, detail=f"Strategy '{name}' not found")
        
        if strategy.is_processing:
            return {"status": "error", "message": "Strategy is already processing a signal"}
        
        background_tasks.add_task(signal_processor.force_close, strategy)
        return {"status": "success", "message": f"Force close initiated for strategy '{name}'"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"🔥 ERROR: force_close_error={str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# System endpoints
@app.get("/status")
async def status():
    """Get system status"""
    strategies = strategy_repo.get_all_strategies()
    available_users = get_available_users()
    users_data = get_users_from_environment()
    
    return {
        "status": "ok",
        "system": "environment-based-multi-user",
        "webhook_structure": {
            "user_specific": "/{username}/{strategy}/{signal}",
            "broadcast": "/cast/{strategy}/{signal}"
        },
        "strategies": len(strategies),
        "users": len(available_users),
        "strategy_names": [s.name for s in strategies],
        "user_names": available_users,
        "configured_users": {user: "configured" for user in users_data.keys()}
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
