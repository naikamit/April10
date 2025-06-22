# api_client.py - Signal Stack API client (strategy-aware)
import httpx
import asyncio
import logging
import json
from datetime import datetime
from typing import Dict, Any, Optional, Tuple

from config import SIGNAL_STACK_WEBHOOK_URL, API_TIMEOUT, MAX_RETRIES, RETRY_DELAY
from strategy import Strategy

logger = logging.getLogger(__name__)

class SignalStackClient:
    def __init__(self):
        self.webhook_url = SIGNAL_STACK_WEBHOOK_URL
        self.timeout = API_TIMEOUT
        self.max_retries = MAX_RETRIES
        self.retry_delay = RETRY_DELAY

    async def _make_request(self, payload: Dict[str, Any], strategy: Strategy) -> Tuple[bool, Dict[str, Any]]:
        """
        Make a request to the Signal Stack API with retry logic
        Returns a tuple of (success, response)
        """
        logger.info(f"🔥 API REQUEST: strategy={strategy.name} owner={strategy.owner} payload={payload}")
        
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
                    logger.info(f"🔥 API RESPONSE: strategy={strategy.name} owner={strategy.owner} response={response_data}")
                    
                    # Log the API call in the strategy's history
                    strategy.add_api_call(payload, response_data)
                    
                    # Check for successful response
                    if 'status' in response_data:
                        if response_data['status'] in ['filled', 'accepted']:
                            return True, response_data
                        elif response_data['status'] == 'ValidationError':
                            logger.error(f"🔥 ERROR: strategy={strategy.name} owner={strategy.owner} validation_error={response_data.get('message', 'Unknown error')}")
                            return False, response_data
                    
                    # If we get here, the response was not successful but also not a validation error
                    logger.warning(f"🔥 ERROR: strategy={strategy.name} owner={strategy.owner} unexpected_response={response_data}")
                    retry_count += 1
                    
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                logger.error(f"🔥 ERROR: strategy={strategy.name} owner={strategy.owner} api_timeout={self.timeout}s retrying_attempt={retry_count+1}/{self.max_retries+1} error={str(e)}")
                retry_count += 1
            except Exception as e:
                logger.exception(f"🔥 ERROR: strategy={strategy.name} owner={strategy.owner} unexpected_api_error={str(e)}")
                retry_count += 1
                
            if retry_count <= self.max_retries:
                logger.info(f"🔥 API RETRY: strategy={strategy.name} owner={strategy.owner} retrying_in={self.retry_delay}s")
                await asyncio.sleep(self.retry_delay)
            else:
                logger.error(f"🔥 ERROR: strategy={strategy.name} owner={strategy.owner} max_retries_exceeded={self.max_retries}")
                
        # Add failed request to strategy history
        failed_response = {"status": "error", "message": "Max retries exceeded"}
        strategy.add_api_call(payload, failed_response)
        return False, failed_response

    async def buy_symbol(self, symbol: str, quantity: int, strategy: Strategy) -> Tuple[bool, Optional[float], Dict[str, Any]]:
        """
        Buy a symbol with the given quantity
        Returns a tuple of (success, price, response)
        """
        payload = {
            "symbol": symbol,
            "action": "buy",
            "quantity": quantity
        }
        
        logger.info(f"🔥 BUYING SHARES: strategy={strategy.name} owner={strategy.owner} symbol={symbol} quantity={quantity}")
        
        success, response = await self._make_request(payload, strategy)
        
        if success and 'price' in response:
            logger.info(f"🔥 API RESPONSE: strategy={strategy.name} owner={strategy.owner} action=buy symbol={symbol} price={response.get('price')} quantity={quantity}")
            return success, response.get('price'), response
        
        return success, None, response

    async def close_position(self, symbol: str, strategy: Strategy) -> Tuple[bool, Optional[float], Optional[int], Dict[str, Any]]:
        """
        Close a position for the given symbol
        Returns a tuple of (success, price, quantity, response)
        """
        payload = {
            "symbol": symbol,
            "action": "close"
        }
        
        logger.info(f"🔥 CLOSING POSITIONS: strategy={strategy.name} owner={strategy.owner} symbol={symbol} calling_api")
        
        success, response = await self._make_request(payload, strategy)
        
        # Position was closed successfully
        if success and response.get('status') == 'filled':
            logger.info(f"🔥 API RESPONSE: strategy={strategy.name} owner={strategy.owner} action=close symbol={symbol} price={response.get('price')} quantity={response.get('quantity')}")
            return success, response.get('price'), response.get('quantity'), response
        
        # No open positions to close is also considered a success
        if success and response.get('status') == 'accepted':
            logger.info(f"🔥 API RESPONSE: strategy={strategy.name} owner={strategy.owner} action=close symbol={symbol} no_positions_to_close")
            return success, None, None, response
            
        return success, None, None, response
