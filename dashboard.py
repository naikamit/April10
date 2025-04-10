# dashboard.py
import logging
from typing import Dict, Any

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from config import Config
from state_manager import StateManager

router = APIRouter()
logger = logging.getLogger(__name__)

# Initialize templates
templates = Jinja2Templates(directory="templates")

@router.get("/", response_class=HTMLResponse)
async def dashboard_page(request: Request) -> HTMLResponse:
    """
    Render the dashboard page.
    
    Args:
        request (Request): The incoming request
        
    Returns:
        HTMLResponse: Dashboard HTML
    """
    state_manager = StateManager()
    config = Config()
    
    # Get data for the dashboard
    cooldown_info = state_manager.get_cooldown_info()
    cash_info = state_manager.get_cash_balance_info()
    api_calls = state_manager.get_api_calls()
    
    # Get configuration values for display
    config_values = {
        "LONG_SYMBOL": config.get("LONG_SYMBOL"),
        "SHORT_SYMBOL": config.get("SHORT_SYMBOL"),
        "COOLDOWN_PERIOD_HOURS": config.get("COOLDOWN_PERIOD_HOURS"),
        "RETRY_MAX_ATTEMPTS": config.get("RETRY_MAX_ATTEMPTS"),
        "MAX_BUY_RETRIES": config.get("MAX_BUY_RETRIES"),
        "BUY_RETRY_PERCENTAGE_REDUCTION": config.get("BUY_RETRY_PERCENTAGE_REDUCTION")
    }
    
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "cooldown": cooldown_info,
            "cash": cash_info,
            "api_calls": api_calls,
            "config": config_values
        }
    )

@router.post("/update_cash_balance")
async def update_cash_balance(request: Request, cash_balance: float = Form(...)) -> Dict[str, Any]:
    """
    Update the cash balance manually.
    
    Args:
        request (Request): The incoming request
        cash_balance (float): New cash balance value
        
    Returns:
        Dict[str, Any]: Result of the update operation
    """
    try:
        state_manager = StateManager()
        
        # Update cash balance
        state_manager.update_cash_balance(cash_balance, "user")
        
        logger.info(f"Cash balance manually updated to ${cash_balance:.2f}")
        
        return {
            "status": "success",
            "message": f"Cash balance updated to ${cash_balance:.2f}",
            "cash_balance": cash_balance
        }
    
    except Exception as e:
        logger.exception(f"Error updating cash balance: {str(e)}")
        return {"status": "error", "message": f"Error updating cash balance: {str(e)}"}
