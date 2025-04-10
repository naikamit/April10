# api_client.py - Signal Stack API client
import httpx
import asyncio
import logging
import json
from datetime import datetime
from typing import Dict, Any, Optional, Tuple

from config import SIGNAL_STACK_WEBHOOK_URL, API_TIMEOUT, MAX_RETRIES, RETRY_DELAY
from state_manager import StateManager

logger = logging.getLogger(__name__)

class SignalStackClient:
    def __init__(self):
        self.webhook_url = SIGNAL_STACK_WEBHOOK_URL
        self.timeout = API_TIMEOUT
        self.max_retries = MAX_RETRIES
        self.retry_delay = RETRY_DELAY
        self.state_manager = StateManager()

    async def _make_request(self, payload: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """
        Make a request to the Signal Stack API with retry logic
        Returns a tuple of (success, response)
        """
        logger.info(f"Making API request: {payload}")
        
        retry_count = 0
        while retry_count <= self.max_retries:
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        self.webhook_url,
                        json=payload,
                        timeout=self.timeout
                    )
                    
                    response_data = response.json()
                    logger.info(f"API response: {response_data}")
                    
                    # Log the API call in the state manager
                    self.state_manager.add_api_call(payload, response_data)
                    
                    # Check for successful response
                    if 'status' in response_data:
                        if response_data['status'] in ['filled', 'accepted']:
                            return True, response_data
                        elif response_data['status'] == 'ValidationError':
                            logger.error(f"Validation error: {response_data.get('message', 'Unknown error')}")
                            return False, response_data
                    
                    # If we get here, the response was not successful but also not a validation error
                    logger.warning(f"Unexpected response format: {response_data}")
                    retry_count += 1
                    
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                logger.error(f"API request failed (attempt {retry_count+1}/{self.max_retries+1}): {str(e)}")
                retry_count += 1
            except Exception as e:
                logger.exception(f"Unexpected error making API request: {str(e)}")
                retry_count += 1
                
            if retry_count <= self.max_retries:
                logger.info(f"Retrying in {self.retry_delay} seconds...")
                await asyncio.sleep(self.retry_delay)
            else:
                logger.error("Max retries exceeded")
                
        return False, {"status": "error", "message": "Max retries exceeded"}

    async def buy_symbol(self, symbol: str, quantity: int) -> Tuple[bool, Optional[float], Dict[str, Any]]:
        """
        Buy a symbol with the given quantity
        Returns a tuple of (success, price, response)
        """
        payload = {
            "symbol": symbol,
            "action": "buy",
            "quantity": quantity
        }
        
        success, response = await self._make_request(payload)
        
        if success and 'price' in response:
            return success, response.get('price'), response
        
        return success, None, response

    async def close_position(self, symbol: str) -> Tuple[bool, Optional[float], Optional[int], Dict[str, Any]]:
        """
        Close a position for the given symbol
        Returns a tuple of (success, price, quantity, response)
        """
        payload = {
            "symbol": symbol,
            "action": "close"
        }
        
        success, response = await self._make_request(payload)
        
        # Position was closed successfully
        if success and response.get('status') == 'filled':
            return success, response.get('price'), response.get('quantity'), response
        
        # No open positions to close is also considered a success
        if success and response.get('status') == 'accepted':
            return success, None, None, response
            
        return success, None, None, response
