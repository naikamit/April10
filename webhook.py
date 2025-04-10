# webhook.py
import logging
from typing import Dict, Any

from fastapi import APIRouter, Request, BackgroundTasks

from trading_engine import TradingEngine

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/webhook")
async def handle_webhook(request: Request, background_tasks: BackgroundTasks) -> Dict[str, Any]:
    """
    Handle incoming webhook signals.
    
    Args:
        request (Request): The incoming request
        background_tasks (BackgroundTasks): FastAPI background tasks manager
        
    Returns:
        Dict[str, Any]: Acknowledgment response
    """
    try:
        payload = await request.json()
        logger.info(f"Webhook received: {payload}")
        
        # Validate payload
        if not isinstance(payload, dict):
            logger.error(f"Invalid payload format: {payload}")
            return {"status": "error", "message": "Invalid payload format"}
        
        signal = payload.get("signal")
        if signal not in ["long", "short"]:
            logger.error(f"Invalid signal: {signal}")
            return {"status": "error", "message": "Invalid signal"}
        
        # Process signal in background
        trading_engine = TradingEngine()
        background_tasks.add_task(trading_engine.process_signal, signal)
        
        return {
            "status": "accepted",
            "message": f"Processing {signal} signal",
            "signal": signal
        }
    
    except Exception as e:
        logger.exception(f"Error processing webhook: {str(e)}")
        return {"status": "error", "message": f"Error processing webhook: {str(e)}"}
