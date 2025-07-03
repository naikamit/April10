# main.py - Entry point with improved dynamic symbol URL format (buy/sell multiple)
import logging
import os
import asyncio
from datetime import datetime
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Form, BackgroundTasks, HTTPException, Path
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn
from typing import Optional, List

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
    logger.info(f"🔥 SYSTEM STARTUP: Multi-User Trading Webhook Service (Dynamic Multi-Symbol)")
    logger.info(f"🔥 AVAILABLE USERS: {', '.join(available_users) if available_users else 'None configured'}")
    logger.info(f"🔥 WEBHOOK STRUCTURE: User: /{{username}}/{{strategy}}/{{buy_symbol}}/{{sell_symbols...}} | Broadcast: /cast/{{strategy}}/{{buy_symbol}}/{{sell_symbols...}}")
    logger.info(f"🔥 SELLING ORDER: Symbols sold in reverse URL order (last symbol in URL gets sold first)")
    yield
    # Shutdown event
    logger.info("🔥 SYSTEM SHUTDOWN: Multi-User Trading Webhook Service")

# Initialize FastAPI
app = FastAPI(title="Multi-User Trading Webhook Service (Dynamic Multi-Symbol)", lifespan=lifespan)

# Setup templates and static files
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# Strategy creation endpoint (only user-aware creation allowed)
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

# Strategy listing endpoint (all strategies)
@app.get("/api/strategies")
async def list_strategies():
    """List all strategies"""
    strategies = strategy_repo.get_all_strategies()
    return {
        "strategies": [strategy.to_dict() for strategy in strategies],
        "count": len(strategies)
    }

# User-aware API endpoints (dashboard operations)
@app.post("/api/users/{username}/strategies/{strategy_name}/update-symbols")
async def update_user_strategy_symbols(
    username: str,
    strategy_name: str,
    long_symbol: Optional[str] = Form(""),
    short_symbol: Optional[str] = Form("")
):
    """Update symbols for a specific user's strategy"""
    try:
        # Check if user exists
        if not user_exists(username):
            raise HTTPException(status_code=404, detail=f"User '{username}' not found")
        
        # Clean up inputs
        long_symbol = long_symbol.strip() if long_symbol.strip() else None
        short_symbol = short_symbol.strip() if short_symbol.strip() else None
        
        strategy = strategy_repo.update_strategy_symbols_both_by_owner_and_name(username, strategy_name, long_symbol, short_symbol)
        if not strategy:
            raise HTTPException(status_code=404, detail=f"Strategy '{strategy_name}' not found for user '{username}'")
        return {"status": "success", "strategy": strategy.to_dict()}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"🔥 ERROR: update_user_symbols_error={str(e)}")
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/users/{username}/strategies/{strategy_name}/update-cash")
async def update_user_strategy_cash(username: str, strategy_name: str, cash_amount: float = Form(...)):
    """Update cash balance for a specific user's strategy"""
    try:
        # Check if user exists
        if not user_exists(username):
            raise HTTPException(status_code=404, detail=f"User '{username}' not found")
        
        strategy = strategy_repo.get_strategy_by_owner_and_name(username, strategy_name)
        if not strategy:
            raise HTTPException(status_code=404, detail=f"Strategy '{strategy_name}' not found for user '{username}'")
        
        success = cash_manager.update_balance_manual(cash_amount, strategy)
        if not success:
            raise HTTPException(status_code=400, detail="Invalid cash amount")
        
        return {"status": "success", "strategy": strategy.to_dict()}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"🔥 ERROR: update_user_cash_error={str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/users/{username}/strategies/{strategy_name}/start-cooldown")
async def start_user_strategy_cooldown(username: str, strategy_name: str):
    """Start cooldown for a specific user's strategy"""
    try:
        # Check if user exists
        if not user_exists(username):
            raise HTTPException(status_code=404, detail=f"User '{username}' not found")
        
        strategy = strategy_repo.get_strategy_by_owner_and_name(username, strategy_name)
        if not strategy:
            raise HTTPException(status_code=404, detail=f"Strategy '{strategy_name}' not found for user '{username}'")
        
        cooldown_manager.start_cooldown(strategy)
        return {"status": "success", "strategy": strategy.to_dict()}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"🔥 ERROR: start_user_cooldown_error={str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/users/{username}/strategies/{strategy_name}/stop-cooldown")
async def stop_user_strategy_cooldown(username: str, strategy_name: str):
    """Stop cooldown for a specific user's strategy"""
    try:
        # Check if user exists
        if not user_exists(username):
            raise HTTPException(status_code=404, detail=f"User '{username}' not found")
        
        strategy = strategy_repo.get_strategy_by_owner_and_name(username, strategy_name)
        if not strategy:
            raise HTTPException(status_code=404, detail=f"Strategy '{strategy_name}' not found for user '{username}'")
        
        cooldown_manager.stop_cooldown(strategy)
        return {"status": "success", "strategy": strategy.to_dict()}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"🔥 ERROR: stop_user_cooldown_error={str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/users/{username}/strategies/{strategy_name}/force-long")
async def force_user_strategy_long(username: str, strategy_name: str, background_tasks: BackgroundTasks):
    """Force long position for a specific user's strategy (uses dashboard symbols)"""
    try:
        # Check if user exists
        if not user_exists(username):
            raise HTTPException(status_code=404, detail=f"User '{username}' not found")
        
        strategy = strategy_repo.get_strategy_by_owner_and_name(username, strategy_name)
        if not strategy:
            raise HTTPException(status_code=404, detail=f"Strategy '{strategy_name}' not found for user '{username}'")
        
        if strategy.is_processing:
            return {"status": "error", "message": "Strategy is already processing a signal"}
        
        background_tasks.add_task(signal_processor.force_long, strategy)
        return {"status": "success", "message": f"Force long initiated for strategy '{strategy_name}' (user: {username})"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"🔥 ERROR: force_user_long_error={str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/users/{username}/strategies/{strategy_name}/force-short")
async def force_user_strategy_short(username: str, strategy_name: str, background_tasks: BackgroundTasks):
    """Force short position for a specific user's strategy (uses dashboard symbols)"""
    try:
        # Check if user exists
        if not user_exists(username):
            raise HTTPException(status_code=404, detail=f"User '{username}' not found")
        
        strategy = strategy_repo.get_strategy_by_owner_and_name(username, strategy_name)
        if not strategy:
            raise HTTPException(status_code=404, detail=f"Strategy '{strategy_name}' not found for user '{username}'")
        
        if strategy.is_processing:
            return {"status": "error", "message": "Strategy is already processing a signal"}
        
        background_tasks.add_task(signal_processor.force_short, strategy)
        return {"status": "success", "message": f"Force short initiated for strategy '{strategy_name}' (user: {username})"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"🔥 ERROR: force_user_short_error={str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/users/{username}/strategies/{strategy_name}/force-close")
async def force_user_strategy_close(username: str, strategy_name: str, background_tasks: BackgroundTasks):
    """Force close all positions for a specific user's strategy (uses dashboard symbols)"""
    try:
        # Check if user exists
        if not user_exists(username):
            raise HTTPException(status_code=404, detail=f"User '{username}' not found")
        
        strategy = strategy_repo.get_strategy_by_owner_and_name(username, strategy_name)
        if not strategy:
            raise HTTPException(status_code=404, detail=f"Strategy '{strategy_name}' not found for user '{username}'")
        
        if strategy.is_processing:
            return {"status": "error", "message": "Strategy is already processing a signal"}
        
        background_tasks.add_task(signal_processor.force_close, strategy)
        return {"status": "success", "message": f"Force close initiated for strategy '{strategy_name}' (user: {username})"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"🔥 ERROR: force_user_close_error={str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/users/{username}/strategies/{strategy_name}")
async def delete_user_strategy(username: str, strategy_name: str):
    """Delete a specific user's strategy"""
    try:
        # Check if user exists
        if not user_exists(username):
            raise HTTPException(status_code=404, detail=f"User '{username}' not found")
        
        success = strategy_repo.delete_strategy_by_owner_and_name(username, strategy_name)
        if not success:
            raise HTTPException(status_code=404, detail=f"Strategy '{strategy_name}' not found for user '{username}'")
        return {"status": "success", "message": f"Strategy '{strategy_name}' deleted for user '{username}'"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"🔥 ERROR: delete_user_strategy_error={str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/users/{username}/strategies/{strategy_name}/logs")
async def get_user_strategy_logs(username: str, strategy_name: str, skip: int = 0, limit: int = 20):
    """Get API logs for a specific user's strategy with pagination"""
    try:
        # Check if user exists
        if not user_exists(username):
            raise HTTPException(status_code=404, detail=f"User '{username}' not found")
        
        strategy = strategy_repo.get_strategy_by_owner_and_name(username, strategy_name)
        if not strategy:
            raise HTTPException(status_code=404, detail=f"Strategy '{strategy_name}' not found for user '{username}'")
        
        # Get all API calls for this strategy
        all_logs = getattr(strategy, 'api_calls', [])
        total_count = len(all_logs)
        
        # Apply pagination (skip from the end since we want most recent first)
        start_idx = max(0, total_count - skip - limit)
        end_idx = total_count - skip
        
        if start_idx >= end_idx:
            # No more logs to return
            paginated_logs = []
        else:
            paginated_logs = all_logs[start_idx:end_idx]
            # Reverse to show most recent first
            paginated_logs = list(reversed(paginated_logs))
        
        return {
            "status": "success",
            "logs": paginated_logs,
            "pagination": {
                "skip": skip,
                "limit": limit,
                "total": total_count,
                "returned": len(paginated_logs),
                "has_more": (skip + limit) < total_count
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"🔥 ERROR: get_user_strategy_logs error={str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Root route - blank page
@app.get("/", response_class=HTMLResponse)
async def root():
    """Blank root page"""
    return HTMLResponse("""
    <html>
        <head>
            <title>RetardTrader</title>
            <link rel="stylesheet" href="/static/style.css">
        </head>
        <body style="font-family: Arial; margin: 0; padding: 0; background: #0f172a; color: #e4e4e7;">
        </body>
    </html>
    """)

# Master dashboard route - show available users with strategy management
@app.get("/cast", response_class=HTMLResponse)
async def master_dashboard():
    """Master dashboard with strategy management across all users"""
    available_users = get_available_users()
    users_data = get_users_from_environment()
    
    # Get all unique strategy names for the dropdown
    all_strategy_names = strategy_repo.get_strategy_names()
    
    if len(available_users) == 0:
        # No users configured
        return HTMLResponse(f"""
        <html>
            <head>
                <title>RetardTrader - Master Dashboard</title>
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
        # Show master dashboard with strategy management
        strategy_options = ''.join(
            f'<option value="{name}">{name}</option>' 
            for name in sorted(all_strategy_names)
        )
        
        user_links = ''.join(
            f'<div class="user-card"><a href="/{user}" class="user-link">{user}</a></div>' 
            for user in sorted(available_users)
        )
        
        return HTMLResponse(f"""
        <html>
            <head>
                <title>RetardTrader - Master Dashboard</title>
                <link rel="stylesheet" href="/static/style.css">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
            </head>
            <body>
                <div id="toast-container"></div>
                <div class="container">
                    <h1>Master Dashboard</h1>
                    <div style="background: #1e293b; padding: 20px; border-radius: 8px; margin-bottom: 20px; border: 1px solid #374151;">
                        <h3 style="color: #f59e0b; margin-top: 0;">🚀 Multi-Symbol Webhook URLs</h3>
                        <p style="color: #94a3b8; margin-bottom: 15px;">New format supports multiple sell symbols:</p>
                        <div style="font-family: monospace; background: #0f172a; padding: 15px; border-radius: 4px; margin-bottom: 15px;">
                            <div style="color: #34d399;">✅ /user/strategy/BUY_SYMBOL/SELL1/SELL2/SELL3</div>
                            <div style="color: #34d399;">✅ /cast/strategy/none/SELL1/SELL2/SELL3 (close only)</div>
                            <div style="color: #94a3b8; margin-top: 8px; font-size: 0.9rem;">Sells in reverse order: SELL3 → SELL2 → SELL1 → Buy BUY_SYMBOL</div>
                        </div>
                        <div style="color: #fbbf24; font-size: 0.9rem;">
                            <strong>Examples:</strong><br>
                            • <code>/cast/mstr/MSTU/MSTZ/SQQQ/TQQQ</code> → Sell TQQQ, SQQQ, MSTZ → Buy MSTU<br>
                            • <code>/cast/mstr/none/MSTZ/SQQQ</code> → Close SQQQ, then MSTZ
                        </div>
                    </div>
                    
                    <!-- User Selection Section -->
                    <div class="users-section">
                        <h2>User Dashboards</h2>
                        <div class="users-grid">
                            {user_links}
                        </div>
                        <div style="margin-top: 20px; text-align: center; color: #94a3b8;">
                            <p>{len(available_users)} users available</p>
                        </div>
                    </div>
                </div>
                
                <style>
                .users-section {{
                    background: #1e293b;
                    border-radius: 8px;
                    padding: 30px;
                    border: 1px solid #374151;
                }}
                
                .users-grid {{
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                    gap: 20px;
                    margin: 20px 0;
                }}
                
                .user-card {{
                    background: #334155;
                    border-radius: 8px;
                    padding: 0;
                    border: 1px solid #475569;
                    transition: all 0.3s;
                }}
                
                .user-card:hover {{
                    border-color: #60a5fa;
                    transform: translateY(-2px);
                    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
                }}
                
                .user-link {{
                    display: block;
                    padding: 25px 20px;
                    color: #e4e4e7;
                    text-decoration: none;
                    font-size: 1.1rem;
                    font-weight: 500;
                    text-align: center;
                    transition: color 0.3s;
                }}
                
                .user-link:hover {{
                    color: #60a5fa;
                }}
                
                #toast-container {{
                    position: fixed;
                    top: 20px;
                    right: 20px;
                    z-index: 1000;
                    display: flex;
                    flex-direction: column;
                    gap: 10px;
                }}
                
                .toast {{
                    background-color: #334155;
                    color: #e4e4e7;
                    padding: 12px 20px;
                    border-radius: 8px;
                    border-left: 4px solid #60a5fa;
                    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
                    transform: translateX(400px);
                    opacity: 0;
                    transition: all 0.3s ease;
                    max-width: 350px;
                    word-wrap: break-word;
                }}
                
                .toast.show {{
                    transform: translateX(0);
                    opacity: 1;
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

# Webhook endpoints - MOVED AFTER API ROUTES TO PREVENT CONFLICTS

# Broadcast webhooks MUST come FIRST (before user-specific routes)
@app.post("/cast/{strategy_name}/{symbols:path}")
async def webhook_broadcast_multi_symbol(
    strategy_name: str, 
    symbols: str, 
    request: Request, 
    background_tasks: BackgroundTasks
):
    """Broadcast webhook for buy/sell operations with multiple symbols"""
    return await _process_broadcast_multi_symbol_webhook(strategy_name, symbols, request, background_tasks)

# User-specific webhooks - buy/sell operations with variable sell symbols
@app.post("/{username}/{strategy_name}/{symbols:path}")
async def webhook_user_multi_symbol(
    username: str, 
    strategy_name: str, 
    symbols: str, 
    request: Request, 
    background_tasks: BackgroundTasks
):
    """User-specific webhook for buy/sell operations with multiple symbols"""
    return await _process_user_multi_symbol_webhook(username, strategy_name, symbols, request, background_tasks)

def _parse_symbol_path(symbols: str) -> tuple:
    """
    Parse symbol path into buy_symbol and sell_symbols list
    
    Args:
        symbols: Path like "MSTU/MSTZ/SQQQ/TQQQ" or "none/MSTZ/SQQQ"
        
    Returns:
        Tuple of (buy_symbol, sell_symbols_list)
        buy_symbol is None if "none"
        sell_symbols_list is in reverse order (ready for execution)
    """
    symbol_parts = [s.strip().upper() for s in symbols.split('/') if s.strip()]
    
    if not symbol_parts:
        return None, []
    
    # First symbol is buy_symbol
    buy_symbol = symbol_parts[0] if symbol_parts[0].upper() != "NONE" else None
    
    # Rest are sell symbols - reverse them for execution order
    sell_symbols = symbol_parts[1:] if len(symbol_parts) > 1 else []
    sell_symbols_reversed = list(reversed(sell_symbols))
    
    return buy_symbol, sell_symbols_reversed

async def _process_user_multi_symbol_webhook(username: str, strategy_name: str, symbols: str, request: Request, background_tasks: BackgroundTasks):
    """Process multi-symbol webhook signal for a specific user's strategy"""
    try:
        client_ip = request.client.host if request.client else "unknown"
        logger.info(f"🔥 USER MULTI-SYMBOL WEBHOOK RECEIVED: user={username} strategy={strategy_name} symbols_path={symbols} from_ip={client_ip}")
        
        # Parse symbols
        buy_symbol, sell_symbols = _parse_symbol_path(symbols)
        logger.info(f"🔥 USER SYMBOL PARSING: buy={buy_symbol} sell_order={sell_symbols}")
        
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
        
        # Validate we have at least one operation
        if not buy_symbol and not sell_symbols:
            error_response = {
                "status": "error",
                "error_type": "no_operations",
                "message": "No buy or sell operations specified"
            }
            return JSONResponse(status_code=400, content=error_response)
        
        logger.info(f"🔥 USER STRATEGY LOOKUP: found strategy={strategy.name} owner={strategy.owner} dashboard_symbols={strategy.long_symbol}/{strategy.short_symbol}")
        logger.info(f"🔥 USER OPERATIONS: buy={buy_symbol} sell_sequence={sell_symbols}")
        
        # Process signal in background to avoid webhook timeout
        background_tasks.add_task(signal_processor.process_multi_symbol_signal, buy_symbol, sell_symbols, strategy)
        
        return {
            "status": "processing", 
            "user": username, 
            "strategy": strategy_name, 
            "operation": "multi_symbol",
            "buy_symbol": buy_symbol,
            "sell_symbols": sell_symbols,
            "execution_order": f"Sell: {' → '.join(sell_symbols) if sell_symbols else 'none'}, Buy: {buy_symbol or 'none'}"
        }
        
    except Exception as e:
        logger.exception(f"🔥 ERROR: user={username} strategy={strategy_name} multi_symbol_webhook_processing_error={str(e)}")
        return JSONResponse(
            status_code=500, 
            content={
                "status": "error",
                "error_type": "internal_error",
                "message": str(e),
                "help": "Check server logs for details"
            }
        )

async def _process_broadcast_multi_symbol_webhook(strategy_name: str, symbols: str, request: Request, background_tasks: BackgroundTasks):
    """Process multi-symbol webhook signal for all users with the same strategy name"""
    try:
        client_ip = request.client.host if request.client else "unknown"
        logger.info(f"🔥 BROADCAST MULTI-SYMBOL WEBHOOK RECEIVED: strategy={strategy_name} symbols_path={symbols} from_ip={client_ip}")
        
        # Parse symbols
        buy_symbol, sell_symbols = _parse_symbol_path(symbols)
        logger.info(f"🔥 BROADCAST SYMBOL PARSING: buy={buy_symbol} sell_order={sell_symbols}")
        
        # Get all strategies with this name across all users
        strategies = strategy_repo.get_strategies_by_name(strategy_name)
        if not strategies:
            all_strategy_names = strategy_repo.get_strategy_names()
            error_response = {
                "status": "error",
                "error_type": "strategy_not_found", 
                "message": f"No strategies named '{strategy_name}' found across any users",
                "available_strategies": all_strategy_names
            }
            logger.error(f"🔥 ERROR: broadcast strategy={strategy_name} not_found webhook_ignored")
            return JSONResponse(status_code=404, content=error_response)
        
        # Validate we have at least one operation
        if not buy_symbol and not sell_symbols:
            error_response = {
                "status": "error",
                "error_type": "no_operations",
                "message": "No buy or sell operations specified"
            }
            return JSONResponse(status_code=400, content=error_response)
        
        logger.info(f"🔥 BROADCAST STRATEGY LOOKUP: found {len(strategies)} strategies named '{strategy_name}' across users: {[s.owner for s in strategies]}")
        
        # Log each strategy being processed
        for strategy in strategies:
            logger.info(f"🔥 BROADCAST PROCESSING: strategy={strategy.name} owner={strategy.owner} dashboard_symbols={strategy.long_symbol}/{strategy.short_symbol}")
        
        logger.info(f"🔥 BROADCAST OPERATIONS: buy={buy_symbol} sell_sequence={sell_symbols}")
        
        # Process signals in parallel for all matching strategies
        background_tasks.add_task(_process_broadcast_multi_symbol_signals_parallel, buy_symbol, sell_symbols, strategies)
        
        return {
            "status": "processing", 
            "strategy": strategy_name, 
            "operation": "multi_symbol",
            "buy_symbol": buy_symbol,
            "sell_symbols": sell_symbols,
            "execution_order": f"Sell: {' → '.join(sell_symbols) if sell_symbols else 'none'}, Buy: {buy_symbol or 'none'}",
            "target_count": len(strategies),
            "target_users": [s.owner for s in strategies]
        }
        
    except Exception as e:
        logger.exception(f"🔥 ERROR: broadcast strategy={strategy_name} multi_symbol_webhook_processing_error={str(e)}")
        return JSONResponse(
            status_code=500, 
            content={
                "status": "error",
                "error_type": "internal_error",
                "message": str(e)
            }
        )

async def _process_broadcast_multi_symbol_signals_parallel(buy_symbol: str, sell_symbols: List[str], strategies):
    """Process multi-symbol signal for multiple strategies in parallel"""
    logger.info(f"🔥 BROADCAST PARALLEL: starting buy={buy_symbol} sell_sequence={sell_symbols} for {len(strategies)} strategies")
    
    # Create tasks for each strategy
    tasks = []
    for strategy in strategies:
        logger.info(f"🔥 BROADCAST PARALLEL: queuing strategy={strategy.name} owner={strategy.owner}")
        task = asyncio.create_task(signal_processor.process_multi_symbol_signal(buy_symbol, sell_symbols, strategy))
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
        
        logger.info(f"🔥 BROADCAST PARALLEL COMPLETE: buy={buy_symbol} sell_sequence={sell_symbols} success={success_count} errors={error_count} total={len(strategies)}")
        
    except Exception as e:
        logger.exception(f"🔥 ERROR: broadcast parallel processing failed: {str(e)}")

# System endpoints
@app.get("/status")
async def status():
    """Get system status"""
    strategies = strategy_repo.get_all_strategies()
    available_users = get_available_users()
    users_data = get_users_from_environment()
    
    return {
        "status": "ok",
        "system": "multi-user-trading-webhook-multi-symbol",
        "webhook_structure": {
            "user_specific": "/{username}/{strategy}/{buy_symbol}/{sell_symbol1}/{sell_symbol2}/...",
            "broadcast": "/cast/{strategy}/{buy_symbol}/{sell_symbol1}/{sell_symbol2}/...",
            "close_only": "/cast/{strategy}/none/{sell_symbol1}/{sell_symbol2}/..."
        },
        "execution_order": "Sell symbols in reverse URL order, then buy with all collected cash",
        "symbol_handling": "URL symbols override dashboard symbols for webhook trades",
        "dashboard_symbols": "Used for Force Close and manual operations only",
        "strategies": len(strategies),
        "users": len(available_users),
        "strategy_names": strategy_repo.get_strategy_names(),
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
