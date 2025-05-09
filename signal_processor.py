# signal_processor.py - Signal processing logic
import logging
import asyncio
from typing import Dict, Any, Optional

from config import (
    LONG_SYMBOL, SHORT_SYMBOL, BUY_RETRY_REDUCTION_PERCENT, 
    MAX_BUY_RETRIES
)
from state_manager import StateManager
from api_client import SignalStackClient
from cash_manager import CashManager
from cooldown_manager import CooldownManager

logger = logging.getLogger(__name__)

class SignalProcessor:
    def __init__(self):
        self.state_manager = StateManager()
        self.api_client = SignalStackClient()
        self.cash_manager = CashManager()
        self.cooldown_manager = CooldownManager()

    async def process_signal(self, signal_type: str):
        """
        Process a signal (long or short)
        """
        logger.info(f"Processing {signal_type} signal")
        
        # Check if we're already processing a signal
        if self.state_manager.is_currently_processing():
            logger.warning("Already processing a signal, ignoring this one")
            return {"status": "ignored", "reason": "Already processing a signal"}
        
        # Set processing flag
        self.state_manager.set_processing(True)
        
        try:
            # Check cooldown state
            in_cooldown = self.cooldown_manager.is_in_cooldown()
            logger.info(f"Cooldown state: {in_cooldown}")
            
            if not in_cooldown:
                # Start the cooldown period
                self.cooldown_manager.start_cooldown()
                
                # Process normal signal (not in cooldown)
                if signal_type == "long":
                    await self._process_long_signal()
                elif signal_type == "short":
                    await self._process_short_signal()
                else:
                    logger.error(f"Unknown signal type: {signal_type}")
                    self.state_manager.set_processing(False)
                    return {"status": "error", "reason": f"Unknown signal type: {signal_type}"}
            else:
                # In cooldown period, do nothing
                logger.info("In cooldown period, ignoring signal")
                
            self.state_manager.set_processing(False)
            return {"status": "success"}
            
        except Exception as e:
            logger.exception(f"Error processing signal: {str(e)}")
            self.state_manager.set_processing(False)
            return {"status": "error", "reason": str(e)}

    async def _process_long_signal(self):
        """
        Process a long signal:
        1. Buy long symbol (if not null)
        2. Close short positions
        """
        logger.info("Processing long signal")
        
        # 1. Buy long symbol if not null
        if LONG_SYMBOL:
            await self._buy_symbol(LONG_SYMBOL)
            # Pause for 3 seconds as specified in requirements
            await asyncio.sleep(3)
        else:
            logger.info("Long symbol is null, skipping buy")
        
        # 2. Close short positions
        if SHORT_SYMBOL:
            await self._close_symbol_position(SHORT_SYMBOL)
        else:
            logger.info("Short symbol is null, skipping close")

    async def _process_short_signal(self):
        """
        Process a short signal:
        1. Buy short symbol (if not null)
        2. Close long positions
        """
        logger.info("Processing short signal")
        
        # 1. Buy short symbol if not null
        if SHORT_SYMBOL:
            await self._buy_symbol(SHORT_SYMBOL)
            # Pause for 3 seconds as specified in requirements
            await asyncio.sleep(3)
        else:
            logger.info("Short symbol is null, skipping buy")
        
        # 2. Close long positions
        if LONG_SYMBOL:
            await self._close_symbol_position(LONG_SYMBOL)
        else:
            logger.info("Long symbol is null, skipping close")

    async def _close_all_positions(self):
        """
        Close all positions for both symbols
        """
        logger.info("Closing all positions")
        
        close_tasks = []
        
        # Close long positions if symbol is not null
        if LONG_SYMBOL:
            close_tasks.append(self._close_symbol_position(LONG_SYMBOL))
        
        # Close short positions if symbol is not null
        if SHORT_SYMBOL:
            close_tasks.append(self._close_symbol_position(SHORT_SYMBOL))
        
        # Wait for all close tasks to complete
        if close_tasks:
            await asyncio.gather(*close_tasks)
        else:
            logger.info("No symbols to close positions for")

    async def _buy_symbol(self, symbol: str):
        """
        Buy a symbol with retry logic:
        1. Buy 1 share to get current price
        2. Calculate max shares
        3. Buy max shares with retry logic
        """
        logger.info(f"Buying {symbol}")
        
        # 1. Buy 1 share to get current price
        success, price, response = await self.api_client.buy_symbol(symbol, 1)
        
        if not success or price is None:
            logger.error(f"Failed to get price for {symbol}")
            return
        
        # 2. Calculate max shares based on current cash balance and price
        max_shares = self.cash_manager.get_max_shares(price)
        
        if max_shares <= 0:
            logger.info(f"Not enough cash to buy any shares of {symbol}")
            return
        
        # 3. Try to buy max shares with retry logic
        logger.info(f"Attempting to buy {max_shares} shares of {symbol}")
        
        retries = 0
        shares_to_buy = max_shares
        
        while retries < MAX_BUY_RETRIES:
            success, _, response = await self.api_client.buy_symbol(symbol, shares_to_buy)
            
            if success:
                logger.info(f"Successfully bought {shares_to_buy} shares of {symbol}")
                # Reduce cash balance by the amount spent
                self.state_manager.cash_balance -= (shares_to_buy * price)
                return
            
            # Calculate reduced shares for retry (ensure at least 1 fewer share)
            reduction = max(1, int(shares_to_buy * BUY_RETRY_REDUCTION_PERCENT / 100))
            shares_to_buy = max(1, shares_to_buy - reduction)
            
            logger.info(f"Retrying with {shares_to_buy} shares (retry {retries+1}/{MAX_BUY_RETRIES})")
            retries += 1
            await asyncio.sleep(3)  # Pause before retry
        
        logger.error(f"Failed to buy {symbol} after {MAX_BUY_RETRIES} attempts")

    async def _close_symbol_position(self, symbol: str):
        """
        Close positions for a symbol, retrying until successful
        """
        logger.info(f"Closing positions for {symbol}")
        
        while True:
            success, price, quantity, response = await self.api_client.close_position(symbol)
            
            if success:
                logger.info(f"Successfully closed positions for {symbol}")
                
                # Update cash balance if position was actually closed (not just "accepted" due to no positions)
                if price is not None and quantity is not None:
                    self.cash_manager.update_balance_from_close(price, quantity)
                
                return
            
            logger.warning(f"Failed to close positions for {symbol}, retrying...")
            await asyncio.sleep(3)  # Pause before retry
