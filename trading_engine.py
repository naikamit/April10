# trading_engine.py
import asyncio
import logging
import math
from typing import Dict, Any, List, Tuple, Optional

from config import Config
from signal_client import SignalClient
from state_manager import StateManager

logger = logging.getLogger(__name__)

class TradingEngine:
    """
    Implements the core trading logic for processing signals.
    """
    
    def __init__(self):
        self.config = Config()
        self.signal_client = SignalClient()
        self.state_manager = StateManager()
        
        self.long_symbol = self.config.get("LONG_SYMBOL")
        self.short_symbol = self.config.get("SHORT_SYMBOL")
        self.max_buy_retries = self.config.get("MAX_BUY_RETRIES")
        self.buy_retry_percentage_reduction = self.config.get("BUY_RETRY_PERCENTAGE_REDUCTION")
        
        logger.info(f"TradingEngine initialized. Long symbol: {self.long_symbol}, Short symbol: {self.short_symbol}")
    
    async def process_signal(self, signal_type: str) -> Dict[str, Any]:
        """
        Process a trading signal.
        
        Args:
            signal_type (str): The signal type ('long' or 'short')
            
        Returns:
            Dict[str, Any]: Result of signal processing
        """
        if signal_type not in ['long', 'short']:
            logger.error(f"Invalid signal type: {signal_type}")
            return {"success": False, "error": "Invalid signal type"}
        
        logger.info(f"Processing {signal_type} signal")
        
        # Determine symbols based on signal type
        buy_symbol = self.long_symbol if signal_type == 'long' else self.short_symbol
        close_symbol = self.short_symbol if signal_type == 'long' else self.long_symbol
        
        # Check cooldown status
        cooldown_active = self.state_manager.is_cooldown_active()
        
        if not cooldown_active:
            # Activate cooldown
            self.state_manager.activate_cooldown()
            logger.info("Cooldown period activated")
            
            # Execute normal trading logic
            return await self._execute_trading_logic(signal_type, buy_symbol, close_symbol)
        else:
            # In cooldown period, just close both positions
            logger.info("In cooldown period, closing both positions")
            return await self._close_both_positions()
    
    async def _execute_trading_logic(self, signal_type: str, buy_symbol: str, 
                                    close_symbol: str) -> Dict[str, Any]:
        """
        Execute the main trading logic for a signal when not in cooldown period.
        
        Args:
            signal_type (str): The signal type ('long' or 'short')
            buy_symbol (str): Symbol to buy
            close_symbol (str): Symbol to close
            
        Returns:
            Dict[str, Any]: Result of trading operations
        """
        result = {
            "success": False,
            "signal_type": signal_type,
            "buy_symbol": buy_symbol,
            "close_symbol": close_symbol,
            "actions": []
        }
        
        # Step 1: Buy 1 share to determine current price
        logger.info(f"Buying 1 share of {buy_symbol} to determine price")
        success, response = await self.signal_client.buy_symbol(buy_symbol, 1)
        
        if not success:
            logger.error(f"Failed to buy 1 share of {buy_symbol}: {response}")
            result["actions"].append({
                "action": "price_check_buy",
                "success": False,
                "data": response
            })
            return result
        
        # We successfully bought 1 share, get the price
        result["actions"].append({
            "action": "price_check_buy",
            "success": True,
            "data": response
        })
        
        current_price = response.get("price")
        if not current_price:
            logger.error(f"Price information missing from response: {response}")
            return result
        
        logger.info(f"Current price of {buy_symbol}: ${current_price}")
        
        # Step 2: Buy maximum possible whole shares
        await self._buy_max_shares(buy_symbol, current_price, result)
        
        # Step 3: Close all positions for the opposite symbol
        await self._close_position_for_symbol(close_symbol, result)
        
        # Update final success status
        result["success"] = True
        return result
    
    async def _buy_max_shares(self, symbol: str, current_price: float, 
                             result: Dict[str, Any]) -> None:
        """
        Buy the maximum possible whole shares within available cash balance.
        
        Args:
            symbol (str): Symbol to buy
            current_price (float): Current price per share
            result (Dict[str, Any]): Result dictionary to update
        """
        cash_balance = self.state_manager.get_cash_balance()
        
        # Calculate max shares (leaving some margin for price fluctuations)
        safety_factor = 0.98  # 2% safety margin
        max_shares = int(cash_balance * safety_factor / current_price)
        
        if max_shares <= 0:
            logger.warning(f"Insufficient cash balance (${cash_balance:.2f}) to buy {symbol} at ${current_price}")
            result["actions"].append({
                "action": "max_shares_buy",
                "success": False,
                "reason": "insufficient_balance",
                "cash_balance": cash_balance,
                "current_price": current_price
            })
            return
        
        # Try to buy max shares with retry logic
        for attempt in range(self.max_buy_retries):
            shares_to_buy = max(1, int(max_shares * (1.0 - attempt * self.buy_retry_percentage_reduction / 100.0)))
            logger.info(f"Attempting to buy {shares_to_buy} shares of {symbol} (attempt {attempt+1}/{self.max_buy_retries})")
            
            success, response = await self.signal_client.buy_symbol(symbol, shares_to_buy)
            
            if success:
                logger.info(f"Successfully bought {shares_to_buy} shares of {symbol} at ${response.get('price', current_price)}")
                
                # Update cash balance
                cost = shares_to_buy * response.get('price', current_price)
                new_balance = cash_balance - cost
                self.state_manager.update_cash_balance(new_balance, f"buy_{symbol}")
                
                result["actions"].append({
                    "action": "max_shares_buy",
                    "success": True,
                    "shares_bought": shares_to_buy,
                    "price": response.get('price', current_price),
                    "cost": cost,
                    "new_cash_balance": new_balance,
                    "data": response
                })
                return
            
            logger.warning(f"Failed to buy {shares_to_buy} shares of {symbol}: {response}")
            
            # If this is the last attempt, record the failure
            if attempt == self.max_buy_retries - 1:
                result["actions"].append({
                    "action": "max_shares_buy",
                    "success": False,
                    "attempts": attempt + 1,
                    "last_attempt_shares": shares_to_buy,
                    "data": response
                })
            
            # Small delay before next attempt
            await asyncio.sleep(1)
    
    async def _close_position_for_symbol(self, symbol: str, result: Dict[str, Any]) -> None:
        """
        Close all positions for a symbol with persistent retries.
        
        Args:
            symbol (str): Symbol to close positions for
            result (Dict[str, Any]): Result dictionary to update
        """
        logger.info(f"Closing all positions for {symbol}")
        
        # This will keep retrying until successful
        success, response = await self.signal_client.close_position_with_retries(symbol)
        
        if success:
            logger.info(f"Successfully closed positions for {symbol}")
            
            # Update cash balance if positions were actually closed (not just 'no positions')
            if response.get("status") == "filled":
                quantity = response.get("quantity", 0)
                price = response.get("price", 0)
                proceeds = quantity * price
                
                logger.info(f"Closed {quantity} shares of {symbol} at ${price}, proceeds: ${proceeds:.2f}")
                
                # Add proceeds to cash balance
                current_balance = self.state_manager.get_cash_balance()
                new_balance = current_balance + proceeds
                self.state_manager.update_cash_balance(new_balance, f"close_{symbol}")
                
                result["actions"].append({
                    "action": "close_position",
                    "symbol": symbol,
                    "success": True,
                    "quantity": quantity,
                    "price": price,
                    "proceeds": proceeds,
                    "new_cash_balance": new_balance,
                    "data": response
                })
            else:
                # No positions were closed
                result["actions"].append({
                    "action": "close_position",
                    "symbol": symbol,
                    "success": True,
                    "note": "No open positions to close",
                    "data": response
                })
        else:
            logger.error(f"Failed to close positions for {symbol} after multiple attempts")
            result["actions"].append({
                "action": "close_position",
                "symbol": symbol,
                "success": False,
                "data": response
            })
    
    async def _close_both_positions(self) -> Dict[str, Any]:
        """
        Close positions for both long and short symbols.
        Used during cooldown period.
        
        Returns:
            Dict[str, Any]: Result of closing operations
        """
        result = {
            "success": False,
            "in_cooldown": True,
            "actions": []
        }
        
        # Close long symbol positions
        await self._close_position_for_symbol(self.long_symbol, result)
        
        # Close short symbol positions
        await self._close_position_for_symbol(self.short_symbol, result)
        
        # Update success if we got this far
        result["success"] = True
        return result
