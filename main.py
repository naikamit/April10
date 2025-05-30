# main.py - Entry point, FastAPI setup
import logging
import os
import json
from datetime import datetime
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Form, BackgroundTasks, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn

from config import DASHBOARD_PORT, LONG_SYMBOL, SHORT_SYMBOL
from state_manager import StateManager
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

# Initialize state
state_manager = StateManager()
signal_processor = SignalProcessor()
cash_manager = CashManager()
cooldown_manager = CooldownManager()

@asynccontextmanager
async def lifespan(app):
    # Startup event
    logger.info("Starting Trading Webhook Service")
    
    # Initialize symbols from config
    state_manager.set_symbols(LONG_SYMBOL, SHORT_SYMBOL)
    symbols = state_manager.get_symbols()
    logger.info(f"Long Symbol: {symbols['long_symbol']}")
    logger.info(f"Short Symbol: {symbols['short_symbol']}")
    
    yield
    
    # Shutdown event
    logger.info("Shutting down Trading Webhook Service")

# Initialize FastAPI
app = FastAPI(title="Trading Webhook Service", lifespan=lifespan)

# Setup templates and static files
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.post("/webhook")
async def webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Webhook endpoint to receive signals
    """
    try:
        payload = await request.json()
        logger.info(f"Received webhook: {payload}")
        
        signal = payload.get("signal")
        if not signal:
            raise HTTPException(status_code=400, detail="Missing 'signal' field")
            
        if signal not in ["long", "short"]:
            raise HTTPException(status_code=400, detail=f"Invalid signal: {signal}")
        
        # Process signal in background to avoid webhook timeout
        background_tasks.add_task(signal_processor.process_signal, signal)
        
        return {"status": "processing", "signal": signal}
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    except Exception as e:
        logger.exception(f"Error processing webhook: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """
    Dashboard to display system status
    """
    cash_info = state_manager.get_cash_balance_info()
    cooldown_info = cooldown_manager.get_cooldown_info()
    api_calls = state_manager.get_api_calls()
    symbols = state_manager.get_symbols()
    
    return templates.TemplateResponse(
        "index.html", 
        {
            "request": request,
            "cash_info": cash_info,
            "cooldown_info": cooldown_info,
            "api_calls": api_calls,
            "long_symbol": symbols["long_symbol"],
            "short_symbol": symbols["short_symbol"],
            "is_processing": state_manager.is_currently_processing()
        }
    )

@app.post("/update-cash")
async def update_cash(cash_amount: float = Form(...)):
    """
    Update cash balance manually
    """
    success = cash_manager.update_balance_manual(cash_amount)
    if success:
        return {"status": "success", "cash_balance": cash_amount}
    else:
        raise HTTPException(status_code=400, detail="Invalid cash amount")

@app.post("/update-symbols")
async def update_symbols(long_symbol: str = Form(...), short_symbol: str = Form(...)):
    """
    Update trading symbols
    """
    try:
        state_manager.set_symbols(long_symbol, short_symbol)
        symbols = state_manager.get_symbols()
        return {"status": "success", "symbols": symbols}
    except Exception as e:
        logger.exception(f"Error updating symbols: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/status")
async def status():
    """
    Get current system status
    """
    cash_info = state_manager.get_cash_balance_info()
    cooldown_info = cooldown_manager.get_cooldown_info()
    symbols = state_manager.get_symbols()
    
    return {
        "status": "ok",
        "cash_balance": cash_info,
        "cooldown": cooldown_info,
        "is_processing": state_manager.is_currently_processing(),
        "long_symbol": symbols["long_symbol"],
        "short_symbol": symbols["short_symbol"]
    }

if __name__ == "__main__":
    port = int(os.environ.get("PORT", DASHBOARD_PORT))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
