# signal_client.py
import asyncio
import logging
import time
from typing import Dict, Any, Optional, Tuple

import httpx

from config import Config
from state_manager import StateManager

logger = logging.getLogger(__name__)

class SignalClient:
    """
    Client for interacting with the Signal Stack API.
    Handles API calls with retry logic and error handling.
    """
    
    def __init__(self):
        self.config = Config()
        self.state_manager = StateManager()
        self.api_url = self.config.get("SIGNAL_STACK_API_URL")
        self.max_attempts = self.config.get("RETRY_MAX_ATTEMPTS")
        self.backoff_factor = self.config.get("RETRY_BACKOFF_FACTOR")
        
        # Configure long timeout for API calls
        self.timeout = httpx.Timeout(connect=30, read=240, write=30, pool=30)
        
        logger.info(f"SignalClient initialized with API URL: {self.api_url}")
    
    async def execute_trade(self, payload: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """
        Execute a trade via the Signal Stack API with retry logic.
        
        Args:
            payload (Dict[str, Any]): The trade request payload
            
        Returns:
            Tuple[bool, Dict[str, Any]]: (success, response_data)
        """
        start_time = time.time()
        attempt = 0
        last_error = None
        response_data = {}
        
        while attempt < self.max_attempts:
            attempt += 1
            
            try:
                logger.info(f"API call attempt {attempt}/{self.max_attempts}: {payload}")
                
                # Make API call with long timeout
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(self.api_url, json=payload)
                
                response_data = response.json()
                duration = time.time() - start_time
                
                # Log the API call
                self.state_manager.log_api_call(
                    request_data=payload,
                    response_data=response_data,
                    success=True,
                    duration=duration
                )
                
                logger.info(f"API response (attempt {attempt}): {response_data}")
                
                # Check for successful response
                if response.status_code == 200 and "status" in response_data:
                    if response_data["status"] in ["filled", "accepted"]:
                        logger.info(f"Trade executed successfully: {response_data}")
                        return True, response_data
                    elif response_data["status"] == "ValidationError":
                        logger.warning(f"Validation error: {response_data.get('message', 'Unknown error')}")
                        return False, response_data
                
                # If we get here, something went wrong but we got a response
                # We'll retry unless we've exhausted our attempts
                logger.warning(f"Unexpected response: {response_data}")
                
            except (httpx.RequestError, httpx.TimeoutException, asyncio.TimeoutError) as e:
                # Connection or timeout error
                last_error = str(e)
                duration = time.time() - start_time
                
                # Log the failed API call
                self.state_manager.log_api_call(
                    request_data=payload,
                    response_data={"error": last_error},
                    success=False,
                    duration=duration
                )
                
                logger.error(f"API call failed (attempt {attempt}): {last_error}")
            
            except Exception as e:
                # Other unexpected errors
                last_error = str(e)
                duration = time.time() - start_time
                
                # Log the failed API call
                self.state_manager.log_api_call(
                    request_data=payload,
                    response_data={"error": last_error},
                    success=False,
                    duration=duration
                )
                
                logger.error(f"Unexpected error (attempt {attempt}): {last_error}")
            
            # If we reach here, we need to retry
            if attempt < self.max_attempts:
                # Calculate backoff delay (exponential)
                delay = self.backoff_factor ** (attempt - 1)
                logger.info(f"Retrying in {delay:.1f} seconds...")
                await asyncio.sleep(delay)
        
        # If we've exhausted all attempts, return failure
        logger.error(f"Failed to execute trade after {self.max_attempts} attempts")
        return False, {"error": last_error, "attempts": attempt}
    
    async def buy_symbol(self, symbol: str, quantity: int) -> Tuple[bool, Dict[str, Any]]:
        """
        Buy a specified quantity of a symbol.
        
        Args:
            symbol (str): The symbol to buy
            quantity (int): The quantity to buy
            
        Returns:
            Tuple[bool, Dict[str, Any]]: (success, response_data)
        """
        payload = {
            "symbol": symbol,
            "action": "buy",
            "quantity": quantity
        }
        
        logger.info(f"Buying {quantity} shares of {symbol}")
        return await self.execute_trade(payload)
    
    async def close_position(self, symbol: str) -> Tuple[bool, Dict[str, Any]]:
        """
        Close all positions for a symbol.
        
        Args:
            symbol (str): The symbol to close positions for
            
        Returns:
            Tuple[bool, Dict[str, Any]]: (success, response_data)
        """
        payload = {
            "symbol": symbol,
            "action": "close"
        }
        
        logger.info(f"Closing position for {symbol}")
        return await self.execute_trade(payload)
    
    async def close_position_with_retries(self, symbol: str, 
                                         max_retries: Optional[int] = None) -> Tuple[bool, Dict[str, Any]]:
        """
        Close a position with persistent retries until successful.
        This is critical for ensuring positions are closed.
        
        Args:
            symbol (str): The symbol to close positions for
            max_retries (Optional[int]): Maximum number of retries, or None for unlimited
            
        Returns:
            Tuple[bool, Dict[str, Any]]: (success, response_data)
        """
        attempt = 0
        last_response = {}
        
        while max_retries is None or attempt < max_retries:
            attempt += 1
            
            logger.info(f"Close position attempt {attempt} for {symbol}")
            success, response = await self.close_position(symbol)
            last_response = response
            
            # Check if successful or if no positions exist (both are valid outcomes)
            if success:
                if response.get("status") == "filled":
                    logger.info(f"Successfully closed position for {symbol}: {response}")
                    return True, response
                elif response.get("status") == "accepted" and response.get("status_description") == "No open positions for the asset":
                    logger.info(f"No open positions for {symbol}")
                    return True, response
            
            # If we're here, we need to retry
            delay = min(30, self.backoff_factor ** (attempt - 1))  # Cap at 30 seconds
            logger.warning(f"Failed to close position for {symbol}. Retrying in {delay:.1f} seconds...")
            await asyncio.sleep(delay)
        
        logger.error(f"Failed to close position for {symbol} after {attempt} attempts")
        return False, last_response
