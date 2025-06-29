# main.py - Entry point, FastAPI setup (environment-based multi-user with fixed strategy keying)
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
    logger.info(f"🔥 MULTI-USER SUPPORT: Multiple users can now have strategies with identical names")
    yield
    # Shutdown event
    logger.info("🔥 SYSTEM SHUTDOWN: Environment-Based Multi-User Trading Webhook Service")

# Initialize FastAPI
app = FastAPI(title="Environment-Based Multi-User Trading Webhook Service", lifespan=lifespan)

# Setup templates and static files
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# Broadcast webhook endpoints (MUST come BEFORE user-specific routes)
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

# User-specific webhook endpoints (MUST come AFTER broadcast routes)
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
            all_strategy_names = strategy_repo.get_strategy_names()
            
            error_response = {
                "status": "error",
                "error_type": "strategy_not_found", 
                "message": f"No strategies named '{strategy_name}' found across any users",
                "available_strategies": all_strategy_names,
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
                    
                    <!-- Strategy Management Section -->
                    {f'''
                    <div class="master-strategy-section">
                        <h2>Strategy Management</h2>
                        <div class="strategy-controls">
                            <div class="form-group">
                                <label for="strategy-select">Select Strategy:</label>
                                <select id="strategy-select" onchange="onStrategySelect()">
                                    <option value="">-- Select a Strategy --</option>
                                    {strategy_options}
                                </select>
                            </div>
                            
                            <div id="strategy-details" style="display: none;">
                                <div class="strategy-info">
                                    <h3 id="selected-strategy-name"></h3>
                                    <div id="strategy-users"></div>
                                </div>
                                
                                <!-- Symbol Update Section -->
                                <div class="symbols-update-section">
                                    <h4>Update Symbols (All Users)</h4>
                                    <div class="symbols-form">
                                        <div class="form-group">
                                            <label for="long-symbol">Long Symbol:</label>
                                            <input type="text" id="long-symbol" placeholder="e.g., MSTU">
                                        </div>
                                        <div class="form-group">
                                            <label for="short-symbol">Short Symbol:</label>
                                            <input type="text" id="short-symbol" placeholder="e.g., MSTZ">
                                        </div>
                                        <button type="button" onclick="updateSymbolsForAll()" class="update-btn">
                                            Update Symbols for All Users
                                        </button>
                                    </div>
                                </div>
                                
                                <!-- Force Actions Section -->
                                <div class="force-actions-section">
                                    <h4>Force Actions (All Users)</h4>
                                    <div class="force-actions">
                                        <button type="button" onclick="forceActionForAll('long')" class="force-btn force-long">
                                            Force Long (All Users)
                                        </button>
                                        <button type="button" onclick="forceActionForAll('short')" class="force-btn force-short">
                                            Force Short (All Users)
                                        </button>
                                        <button type="button" onclick="forceActionForAll('close')" class="force-btn force-close">
                                            Force Close (All Users)
                                        </button>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                    ''' if all_strategy_names else '<div class="empty-state"><h2>No Strategies Found</h2><p>Create strategies first to manage them here.</p></div>'}
                    
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
                .master-strategy-section {{
                    background: #1e293b;
                    border-radius: 8px;
                    padding: 30px;
                    margin-bottom: 30px;
                    border: 1px solid #374151;
                }}
                
                .strategy-controls {{
                    max-width: 600px;
                }}
                
                .form-group {{
                    margin-bottom: 20px;
                }}
                
                .form-group label {{
                    display: block;
                    color: #cbd5e1;
                    font-weight: 500;
                    margin-bottom: 8px;
                    font-size: 0.95rem;
                }}
                
                .form-group select,
                .form-group input {{
                    width: 100%;
                    padding: 12px;
                    background-color: #475569;
                    border: 1px solid #64748b;
                    border-radius: 6px;
                    color: #e4e4e7;
                    font-size: 0.95rem;
                    transition: border-color 0.3s, box-shadow 0.3s;
                }}
                
                .form-group select:focus,
                .form-group input:focus {{
                    outline: none;
                    border-color: #60a5fa;
                    box-shadow: 0 0 0 3px rgba(96, 165, 250, 0.2);
                }}
                
                #strategy-details {{
                    margin-top: 30px;
                    padding-top: 20px;
                    border-top: 1px solid #475569;
                }}
                
                .strategy-info {{
                    margin-bottom: 30px;
                }}
                
                .strategy-info h3 {{
                    color: #60a5fa;
                    margin-bottom: 10px;
                }}
                
                .strategy-users {{
                    color: #94a3b8;
                    font-size: 0.9rem;
                }}
                
                .symbols-update-section,
                .force-actions-section {{
                    background: #334155;
                    border-radius: 8px;
                    padding: 20px;
                    margin-bottom: 20px;
                }}
                
                .symbols-update-section h4,
                .force-actions-section h4 {{
                    color: #f1f5f9;
                    margin-bottom: 15px;
                    margin-top: 0;
                }}
                
                .symbols-form {{
                    display: grid;
                    grid-template-columns: 1fr 1fr auto;
                    gap: 15px;
                    align-items: end;
                }}
                
                .update-btn {{
                    background-color: #3b82f6;
                    color: white;
                    border: none;
                    padding: 12px 20px;
                    border-radius: 6px;
                    cursor: pointer;
                    font-weight: 500;
                    font-size: 0.95rem;
                    transition: background-color 0.3s, transform 0.1s;
                    white-space: nowrap;
                }}
                
                .update-btn:hover {{
                    background-color: #2563eb;
                    transform: translateY(-1px);
                }}
                
                .force-actions {{
                    display: flex;
                    gap: 15px;
                    flex-wrap: wrap;
                }}
                
                .force-btn {{
                    padding: 12px 20px;
                    border: none;
                    border-radius: 6px;
                    cursor: pointer;
                    font-weight: 500;
                    font-size: 0.95rem;
                    transition: all 0.3s;
                    min-width: 140px;
                }}
                
                .force-btn:hover {{
                    transform: translateY(-1px);
                    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
                }}
                
                .force-long {{
                    background-color: #059669;
                    color: white;
                }}
                
                .force-long:hover {{
                    background-color: #047857;
                }}
                
                .force-short {{
                    background-color: #dc2626;
                    color: white;
                }}
                
                .force-short:hover {{
                    background-color: #b91c1c;
                }}
                
                .force-close {{
                    background-color: #f59e0b;
                    color: #000;
                }}
                
                .force-close:hover {{
                    background-color: #d97706;
                }}
                
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
                
                .empty-state {{
                    text-align: center;
                    padding: 60px 20px;
                    background-color: #1e293b;
                    border-radius: 8px;
                    border: 2px dashed #374151;
                    margin-bottom: 30px;
                }}
                
                .empty-state h2 {{
                    color: #f1f5f9;
                    margin-bottom: 15px;
                    border: none;
                }}
                
                .empty-state p {{
                    color: #94a3b8;
                    margin-bottom: 0;
                    font-size: 1.1rem;
                }}
                
                @media (max-width: 768px) {{
                    .symbols-form {{
                        grid-template-columns: 1fr;
                    }}
                    
                    .force-actions {{
                        flex-direction: column;
                    }}
                    
                    .force-btn {{
                        width: 100%;
                    }}
                }}
                
                /* Toast notifications */
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
                
                .toast-success {{
                    border-left-color: #34d399;
                    background-color: #065f46;
                }}
                
                .toast-error {{
                    border-left-color: #f87171;
                    background-color: #7f1d1d;
                }}
                
                .toast-info {{
                    border-left-color: #60a5fa;
                    background-color: #1e3a8a;
                }}
                </style>
                
                <script>
                var selectedStrategy = null;
                
                // Toast notification system
                function showToast(message, type) {{
                    if (!type) type = 'info';
                    
                    var container = document.getElementById('toast-container');
                    var toast = document.createElement('div');
                    toast.className = 'toast toast-' + type;
                    toast.textContent = message;
                    
                    container.appendChild(toast);
                    
                    // Trigger animation
                    setTimeout(function() {{
                        toast.classList.add('show');
                    }}, 100);
                    
                    // Remove toast after 5 seconds
                    setTimeout(function() {{
                        toast.classList.remove('show');
                        setTimeout(function() {{
                            if (container.contains(toast)) {{
                                container.removeChild(toast);
                            }}
                        }}, 300);
                    }}, 5000);
                }}
                
                function onStrategySelect() {{
                    var select = document.getElementById('strategy-select');
                    var detailsDiv = document.getElementById('strategy-details');
                    var strategyNameEl = document.getElementById('selected-strategy-name');
                    var strategyUsersEl = document.getElementById('strategy-users');
                    
                    selectedStrategy = select.value;
                    
                    if (selectedStrategy) {{
                        // Show details section
                        detailsDiv.style.display = 'block';
                        strategyNameEl.textContent = selectedStrategy;
                        
                        // Fetch strategy details
                        fetchStrategyDetails(selectedStrategy);
                        
                        // Clear symbol inputs
                        document.getElementById('long-symbol').value = '';
                        document.getElementById('short-symbol').value = '';
                    }} else {{
                        detailsDiv.style.display = 'none';
                    }}
                }}
                
                function fetchStrategyDetails(strategyName) {{
                    fetch('/api/strategies/by-name/' + strategyName)
                    .then(function(response) {{
                        return response.json();
                    }})
                    .then(function(result) {{
                        if (result.status === 'success') {{
                            var users = result.strategies.map(function(s) {{ return s.owner; }});
                            var usersText = 'Users with this strategy: ' + users.join(', ');
                            document.getElementById('strategy-users').textContent = usersText;
                            
                            // Pre-populate symbols if they're consistent across users
                            var firstStrategy = result.strategies[0];
                            if (firstStrategy) {{
                                document.getElementById('long-symbol').value = firstStrategy.long_symbol || '';
                                document.getElementById('short-symbol').value = firstStrategy.short_symbol || '';
                            }}
                        }}
                    }})
                    .catch(function(error) {{
                        console.error('Error fetching strategy details:', error);
                    }});
                }}
                
                function updateSymbolsForAll() {{
                    if (!selectedStrategy) {{
                        showToast('Please select a strategy first', 'error');
                        return;
                    }}
                    
                    var longSymbol = document.getElementById('long-symbol').value.trim();
                    var shortSymbol = document.getElementById('short-symbol').value.trim();
                    
                    var formData = new FormData();
                    formData.append('long_symbol', longSymbol);
                    formData.append('short_symbol', shortSymbol);
                    
                    var button = document.querySelector('.update-btn');
                    button.disabled = true;
                    button.textContent = 'Updating...';
                    
                    fetch('/api/strategies/' + selectedStrategy + '/update-symbols-all', {{
                        method: 'POST',
                        body: formData
                    }})
                    .then(function(response) {{
                        return response.json();
                    }})
                    .then(function(result) {{
                        if (result.status === 'success') {{
                            showToast('Symbols updated for all users with strategy: ' + selectedStrategy, 'success');
                        }} else {{
                            showToast('Error: ' + (result.detail || 'Failed to update symbols'), 'error');
                        }}
                    }})
                    .catch(function(error) {{
                        showToast('Error updating symbols: ' + error.message, 'error');
                    }})
                    .finally(function() {{
                        button.disabled = false;
                        button.textContent = 'Update Symbols for All Users';
                    }});
                }}
                
                function forceActionForAll(action) {{
                    if (!selectedStrategy) {{
                        showToast('Please select a strategy first', 'error');
                        return;
                    }}
                    
                    var actionText = action.charAt(0).toUpperCase() + action.slice(1);
                    var confirmed = confirm('Are you sure you want to force ' + actionText.toUpperCase() + ' for ALL users with strategy "' + selectedStrategy + '"?\\n\\nThis will affect all users who have this strategy.');
                    
                    if (!confirmed) {{
                        return;
                    }}
                    
                    var button = document.querySelector('.force-' + action);
                    button.disabled = true;
                    button.textContent = 'Processing...';
                    
                    fetch('/api/strategies/' + selectedStrategy + '/force-' + action + '-all', {{
                        method: 'POST',
                        headers: {{
                            'Content-Type': 'application/json'
                        }}
                    }})
                    .then(function(response) {{
                        return response.json();
                    }})
                    .then(function(result) {{
                        if (result.status === 'success') {{
                            showToast('Force ' + actionText + ' executed for all users with strategy: ' + selectedStrategy, 'success');
                        }} else {{
                            showToast('Error: ' + (result.message || 'Unknown error'), 'error');
                        }}
                    }})
                    .catch(function(error) {{
                        showToast('Error executing force ' + action + ': ' + error.message, 'error');
                    }})
                    .finally(function() {{
                        button.disabled = false;
                        button.textContent = 'Force ' + actionText + ' (All Users)';
                    }});
                }}
                </script>
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
    """Get a specific strategy (DEPRECATED - may return any user's strategy with this name)"""
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
    """Update a strategy (DEPRECATED - may update any user's strategy with this name)"""
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
    """Delete a strategy (DEPRECATED - may delete any user's strategy with this name)"""
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
    """Update symbols for a specific strategy (DEPRECATED - may update any user's strategy with this name)"""
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
    """Update cash balance for a specific strategy (DEPRECATED - may update any user's strategy with this name)"""
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
    """Start cooldown for a specific strategy (DEPRECATED - may affect any user's strategy with this name)"""
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
    """Stop cooldown for a specific strategy (DEPRECATED - may affect any user's strategy with this name)"""
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
    """Force long position for a specific strategy (DEPRECATED - may affect any user's strategy with this name)"""
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
    """Force short position for a specific strategy (DEPRECATED - may affect any user's strategy with this name)"""
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
    """Force close all positions for a specific strategy (DEPRECATED - may affect any user's strategy with this name)"""
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

# User-aware API endpoints (NEW - target specific user's strategies)
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
    """Force long position for a specific user's strategy"""
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
    """Force short position for a specific user's strategy"""
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
    """Force close all positions for a specific user's strategy"""
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

# Master dashboard API endpoints for bulk operations
@app.get("/api/strategies/by-name/{strategy_name}")
async def get_strategies_by_name(strategy_name: str):
    """Get all strategies with a specific name across all users"""
    try:
        strategies = strategy_repo.get_strategies_by_name(strategy_name)
        if not strategies:
            raise HTTPException(status_code=404, detail=f"No strategies named '{strategy_name}' found")
        
        return {
            "status": "success",
            "strategy_name": strategy_name,
            "count": len(strategies),
            "strategies": [strategy.to_dict() for strategy in strategies]
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"🔥 ERROR: get_strategies_by_name error={str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/strategies/{strategy_name}/update-symbols-all")
async def update_symbols_for_all_users(
    strategy_name: str,
    long_symbol: Optional[str] = Form(""),
    short_symbol: Optional[str] = Form("")
):
    """Update symbols for all users who have a strategy with this name"""
    try:
        # Get all strategies with this name
        strategies = strategy_repo.get_strategies_by_name(strategy_name)
        if not strategies:
            raise HTTPException(status_code=404, detail=f"No strategies named '{strategy_name}' found")
        
        # Clean up inputs
        long_symbol = long_symbol.strip() if long_symbol.strip() else None
        short_symbol = short_symbol.strip() if short_symbol.strip() else None
        
        updated_strategies = []
        failed_updates = []
        
        # Update each strategy
        for strategy in strategies:
            try:
                updated_strategy = strategy_repo.update_strategy_symbols_both_by_owner_and_name(
                    strategy.owner, strategy.name, long_symbol, short_symbol
                )
                if updated_strategy:
                    updated_strategies.append(f"{strategy.owner}/{strategy.name}")
                else:
                    failed_updates.append(f"{strategy.owner}/{strategy.name}")
            except Exception as e:
                logger.error(f"🔥 ERROR: failed to update symbols for {strategy.owner}/{strategy.name}: {str(e)}")
                failed_updates.append(f"{strategy.owner}/{strategy.name}")
        
        return {
            "status": "success",
            "strategy_name": strategy_name,
            "updated_count": len(updated_strategies),
            "failed_count": len(failed_updates),
            "updated_strategies": updated_strategies,
            "failed_strategies": failed_updates,
            "symbols": {"long_symbol": long_symbol, "short_symbol": short_symbol}
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"🔥 ERROR: update_symbols_for_all_users error={str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/strategies/{strategy_name}/force-long-all")
async def force_long_for_all_users(strategy_name: str, background_tasks: BackgroundTasks):
    """Force long position for all users who have a strategy with this name"""
    try:
        strategies = strategy_repo.get_strategies_by_name(strategy_name)
        if not strategies:
            raise HTTPException(status_code=404, detail=f"No strategies named '{strategy_name}' found")
        
        # Queue force long tasks for all strategies
        for strategy in strategies:
            if not strategy.is_processing:
                background_tasks.add_task(signal_processor.force_long, strategy)
                logger.info(f"🔥 MASTER FORCE LONG: queued for {strategy.owner}/{strategy.name}")
            else:
                logger.warning(f"🔥 MASTER FORCE LONG: skipped {strategy.owner}/{strategy.name} (already processing)")
        
        return {
            "status": "success",
            "action": "force_long",
            "strategy_name": strategy_name,
            "target_count": len(strategies),
            "target_users": [s.owner for s in strategies],
            "message": f"Force long initiated for {len(strategies)} strategies named '{strategy_name}'"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"🔥 ERROR: force_long_for_all_users error={str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/strategies/{strategy_name}/force-short-all")
async def force_short_for_all_users(strategy_name: str, background_tasks: BackgroundTasks):
    """Force short position for all users who have a strategy with this name"""
    try:
        strategies = strategy_repo.get_strategies_by_name(strategy_name)
        if not strategies:
            raise HTTPException(status_code=404, detail=f"No strategies named '{strategy_name}' found")
        
        # Queue force short tasks for all strategies
        for strategy in strategies:
            if not strategy.is_processing:
                background_tasks.add_task(signal_processor.force_short, strategy)
                logger.info(f"🔥 MASTER FORCE SHORT: queued for {strategy.owner}/{strategy.name}")
            else:
                logger.warning(f"🔥 MASTER FORCE SHORT: skipped {strategy.owner}/{strategy.name} (already processing)")
        
        return {
            "status": "success",
            "action": "force_short",
            "strategy_name": strategy_name,
            "target_count": len(strategies),
            "target_users": [s.owner for s in strategies],
            "message": f"Force short initiated for {len(strategies)} strategies named '{strategy_name}'"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"🔥 ERROR: force_short_for_all_users error={str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/strategies/{strategy_name}/force-close-all")
async def force_close_for_all_users(strategy_name: str, background_tasks: BackgroundTasks):
    """Force close all positions for all users who have a strategy with this name"""
    try:
        strategies = strategy_repo.get_strategies_by_name(strategy_name)
        if not strategies:
            raise HTTPException(status_code=404, detail=f"No strategies named '{strategy_name}' found")
        
        # Queue force close tasks for all strategies
        for strategy in strategies:
            if not strategy.is_processing:
                background_tasks.add_task(signal_processor.force_close, strategy)
                logger.info(f"🔥 MASTER FORCE CLOSE: queued for {strategy.owner}/{strategy.name}")
            else:
                logger.warning(f"🔥 MASTER FORCE CLOSE: skipped {strategy.owner}/{strategy.name} (already processing)")
        
        return {
            "status": "success",
            "action": "force_close",
            "strategy_name": strategy_name,
            "target_count": len(strategies),
            "target_users": [s.owner for s in strategies],
            "message": f"Force close initiated for {len(strategies)} strategies named '{strategy_name}'"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"🔥 ERROR: force_close_for_all_users error={str(e)}")
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
        "multi_user_support": "Multiple users can have strategies with identical names",
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
