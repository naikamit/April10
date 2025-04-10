# webhook.py
import logging
import time
from typing import Dict, Any

from fastapi import APIRouter, Request, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse

from trading_engine import TradingEngine
from utils import validate_payload, timed_execution
from error_handler import ErrorHandler

router = APIRouter(tags=["webhook"])
logger = logging.getLogger(__name__)

@router.post("/webhook")
@timed_execution
async def handle_webhook(request: Request, background_tasks: BackgroundTasks) -> Dict[str, Any]:
    """
    Handle incoming webhook signals for trading.
    
    Args:
        request (Request): The incoming request
        background_tasks (BackgroundTasks): FastAPI background tasks manager
        
    Returns:
        Dict[str, Any]: Acknowledgment response
    """
    request_time = time.time()
    client_ip = request.client.host if request.client else "unknown"
    
    logger.info(f"Webhook request received from {client_ip}")
    
    try:
        # Parse request payload
        payload = await request.json()
        logger.info(f"Webhook payload: {payload}")
        
        # Validate payload
        error = validate_payload(payload, ["signal"])
        if error:
            logger.error(f"Invalid webhook payload: {error}")
            raise HTTPException(status_code=400, detail=error)
        
        signal = payload["signal"]
        if signal not in ["long", "short"]:
            logger.error(f"Invalid signal value: {signal}")
            raise HTTPException(status_code=400, detail=f"Invalid signal value: {signal}. Must be 'long' or 'short'.")
        
        # Process signal in background to allow quick response
        logger.info(f"Starting background processing of {signal} signal")
        trading_engine = TradingEngine()
        background_tasks.add_task(
            ErrorHandler.try_execute_async, 
            trading_engine.process_signal, 
            signal
        )
        
        # Immediate response
        processing_time = time.time() - request_time
        response = {
            "status": "accepted",
            "message": f"Processing {signal} signal",
            "signal": signal,
            "processing_time_ms": round(processing_time * 1000)
        }
        
        logger.info(f"Webhook request acknowledged in {processing_time:.4f} seconds")
        return response
    
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    
    except ValueError as e:
        # JSON parse errors
        logger.error(f"JSON parse error: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Invalid JSON payload: {str(e)}")
    
    except Exception as e:
        # Unexpected errors
        logger.exception(f"Error processing webhook: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing webhook: {str(e)}")
