# signal_processor.py - Signal processing logic (strategy-aware)
import logging
import asyncio
from typing import Dict, Any, Optional

from config import BUY_RETRY_REDUCTION_PERCENT, MAX_BUY_RETRIES
from strategy import Strategy
from api_client import SignalStackClient
from cash_manager import CashManager
from cooldown_manager import CooldownManager

logger = logging.getLogger(__name__)

# Add configuration for close position retries
MAX_CLOSE_RETRIES = 10  # Maximum retries for close position operations

class SignalProcessor:
    def __init__(self):
        self.api_client = SignalStackClient()
        self.cash_manager = CashManager()
        self.cooldown_manager = CooldownManager()

    async def process_signal(self, signal_type: str, strategy: Strategy) -> Dict[str, Any]:
        """
        Process a signal for a specific strategy
        
        Args:
            signal_type: Type of signal ('long', 'short', 'close')
            strategy: Strategy instance to process signal for
            
        Returns:
            Dictionary with processing result
        """
        logger.info(f"🔥 SIGNAL PROCESSING: strategy={strategy.name} owner={strategy.owner} signal={signal_type} starting_execution")
        
        # Check if strategy is already processing a signal
        if strategy.is_processing:
            logger.warning(f"🔥 SIGNAL IGNORED: strategy={strategy.name} owner={strategy.owner} signal={signal_type} reason=already_processing")
            return {"status": "ignored", "reason": "Strategy is already processing a signal"}
        
        # Set processing flag for this strategy
        strategy.is_processing = True
        
        try:
            # Check cooldown state
            in_cooldown = self.cooldown_manager.is_in_cooldown(strategy)
            logger.info(f"🔥 COOLDOWN CHECK: strategy={strategy.name} owner={strategy.owner} status={'active' if in_cooldown else 'inactive'} ready_to_process={not in_cooldown}")
            
            if not in_cooldown:
                # Start the cooldown period
                self.cooldown_manager.start_cooldown(strategy)
                
                # Process normal signal (not in cooldown)
                if signal_type == "long":
                    await self._process_long_signal(strategy)
                elif signal_type == "short":
                    await self._process_short_signal(strategy)
                elif signal_type == "close":
                    await self._close_all_positions(strategy)
                else:
                    logger.error(f"🔥 ERROR: strategy={strategy.name} owner={strategy.owner} unknown_signal_type={signal_type}")
                    strategy.is_processing = False
                    return {"status": "error", "reason": f"Unknown signal type: {signal_type}"}
            else:
                # In cooldown period, do nothing
                logger.info(f"🔥 SIGNAL IGNORED: strategy={strategy.name} owner={strategy.owner} signal={signal_type} reason=in_cooldown")
                
            strategy.is_processing = False
            logger.info(f"🔥 SIGNAL COMPLETE: strategy={strategy.name} owner={strategy.owner} signal={signal_type} result=success")
            return {"status": "success"}
            
        except Exception as e:
            logger.exception(f"🔥 ERROR: strategy={strategy.name} owner={strategy.owner} signal_processing_error={str(e)}")
            strategy.is_processing = False
            return {"status": "error", "reason": str(e)}

    async def _process_long_signal(self, strategy: Strategy):
        """
        Process a long signal for a strategy:
        1. Close short positions
        2. Buy long symbol (if not null)
        """
        logger.info(f"🔥 SIGNAL PROCESSING: strategy={strategy.name} owner={strategy.owner} signal=long starting_execution")
        
        # 1. Close short positions
        if strategy.short_symbol:
            await self._close_symbol_position(strategy.short_symbol, strategy)
        else:
            logger.info(f"🔥 SIGNAL PROCESSING: strategy={strategy.name} owner={strategy.owner} short_symbol=null skipping_close")
        
        # 2. Buy long symbol if not null
        if strategy.long_symbol:
            await self._buy_symbol(strategy.long_symbol, strategy)
            # Pause for 3 seconds as specified in requirements
            await asyncio.sleep(3)
        else:
            logger.info(f"🔥 SIGNAL PROCESSING: strategy={strategy.name} owner={strategy.owner} long_symbol=null skipping_buy")

    async def _process_short_signal(self, strategy: Strategy):
        """
        Process a short signal for a strategy:
        1. Close long positions
        2. Buy short symbol (if not null)
        """
        logger.info(f"🔥 SIGNAL PROCESSING: strategy={strategy.name} owner={strategy.owner} signal=short starting_execution")
        
        # 1. Close long positions
        if strategy.long_symbol:
            await self._close_symbol_position(strategy.long_symbol, strategy)
        else:
            logger.info(f"🔥 SIGNAL PROCESSING: strategy={strategy.name} owner={strategy.owner} long_symbol=null skipping_close")
        
        # 2. Buy short symbol if not null
        if strategy.short_symbol:
            await self._buy_symbol(strategy.short_symbol, strategy)
            # Pause for 3 seconds as specified in requirements
            await asyncio.sleep(3)
        else:
            logger.info(f"🔥 SIGNAL PROCESSING: strategy={strategy.name} owner={strategy.owner} short_symbol=null skipping_buy")

    async def _close_all_positions(self, strategy: Strategy):
        """
        Close all positions for both symbols in a strategy
        """
        logger.info(f"🔥 SIGNAL PROCESSING: strategy={strategy.name} owner={strategy.owner} signal=close closing_all_positions")
        
        close_tasks = []
        
        # Close long positions if symbol is not null
        if strategy.long_symbol:
            close_tasks.append(self._close_symbol_position(strategy.long_symbol, strategy))
        
        # Close short positions if symbol is not null
        if strategy.short_symbol:
            close_tasks.append(self._close_symbol_position(strategy.short_symbol, strategy))
        
        # Wait for all close tasks to complete
        if close_tasks:
            await asyncio.gather(*close_tasks)
        else:
            logger.info(f"🔥 SIGNAL PROCESSING: strategy={strategy.name} owner={strategy.owner} no_symbols_to_close")

    async def _buy_symbol(self, symbol: str, strategy: Strategy):
        """
        Buy a symbol with retry logic for a strategy:
        1. Buy 1 share to get current price
        2. Calculate max shares based on remaining cash
        3. Buy max shares with retry logic
        """
        logger.info(f"🔥 BUYING SHARES: strategy={strategy.name} owner={strategy.owner} symbol={symbol} attempting_purchase")
        
        # 1. Buy 1 share to get current price
        success, price, response = await self.api_client.buy_symbol(symbol, 1, strategy)
        
        if not success or price is None:
            logger.error(f"🔥 ERROR: strategy={strategy.name} owner={strategy.owner} symbol={symbol} failed_to_get_price")
            return
        
        # Update cash balance after the 1-share purchase
        self.cash_manager.update_balance_from_buy(price, 1, strategy)
        
        # 2. Calculate max shares based on remaining cash balance and price
        max_shares = self.cash_manager.get_max_shares(price, strategy)
        
        if max_shares <= 0:
            logger.info(f"🔥 BUYING COMPLETE: strategy={strategy.name} owner={strategy.owner} symbol={symbol} bought_1_share only_enough_cash_for_1")
            return
        
        # 3. Try to buy additional shares with retry logic
        logger.info(f"🔥 BUYING SHARES: strategy={strategy.name} owner={strategy.owner} symbol={symbol} max_additional_shares={max_shares} attempting_purchase")
        
        retries = 0
        shares_to_buy = max_shares
        
        while retries < MAX_BUY_RETRIES:
            success, final_price, response = await self.api_client.buy_symbol(symbol, shares_to_buy, strategy)
            
            if success:
                logger.info(f"🔥 API RESPONSE: strategy={strategy.name} owner={strategy.owner} action=buy symbol={symbol} price={final_price} quantity={shares_to_buy}")
                # Reduce cash balance by the amount spent
                if final_price:
                    self.cash_manager.update_balance_from_buy(final_price, shares_to_buy, strategy)
                logger.info(f"🔥 BUYING COMPLETE: strategy={strategy.name} owner={strategy.owner} symbol={symbol} total_shares={1 + shares_to_buy}")
                return
            
            # Calculate reduced shares for retry (ensure at least 1 fewer share)
            reduction = max(1, int(shares_to_buy * BUY_RETRY_REDUCTION_PERCENT / 100))
            shares_to_buy = max(1, shares_to_buy - reduction)
            
            logger.info(f"🔥 BUY RETRY: strategy={strategy.name} owner={strategy.owner} symbol={symbol} shares={shares_to_buy} retry={retries+1}/{MAX_BUY_RETRIES}")
            retries += 1
            await asyncio.sleep(3)  # Pause before retry
        
        logger.error(f"🔥 ERROR: strategy={strategy.name} owner={strategy.owner} symbol={symbol} max_buy_retries_exceeded={MAX_BUY_RETRIES} bought_1_share_only")
        logger.info(f"🔥 BUYING COMPLETE: strategy={strategy.name} owner={strategy.owner} symbol={symbol} total_shares=1 additional_buys_failed")

    async def _close_symbol_position(self, symbol: str, strategy: Strategy):
        """
        Close positions for a symbol with bounded retry logic
        """
        logger.info(f"🔥 CLOSING POSITIONS: strategy={strategy.name} owner={strategy.owner} symbol={symbol} calling_api")
        
        retries = 0
        while retries < MAX_CLOSE_RETRIES:
            success, price, quantity, response = await self.api_client.close_position(symbol, strategy)
            
            if success:
                logger.info(f"🔥 CLOSE COMPLETE: strategy={strategy.name} owner={strategy.owner} symbol={symbol} success=true")
                
                # Update cash balance if position was actually closed (not just "accepted" due to no positions)
                if price is not None and quantity is not None:
                    self.cash_manager.update_balance_from_close(price, quantity, strategy)
                
                return
            
            retries += 1
            if retries < MAX_CLOSE_RETRIES:
                logger.warning(f"🔥 CLOSE RETRY: strategy={strategy.name} owner={strategy.owner} symbol={symbol} retry={retries}/{MAX_CLOSE_RETRIES} retrying_in_3s")
                await asyncio.sleep(3)  # Pause before retry
            else:
                logger.error(f"🔥 ERROR: strategy={strategy.name} owner={strategy.owner} symbol={symbol} max_close_retries_exceeded={MAX_CLOSE_RETRIES}")
                break

    # Force methods for manual trading (bypass cooldown)
    async def force_long(self, strategy: Strategy):
        """Force a long position for a strategy (bypasses cooldown)"""
        logger.info(f"🔥 MANUAL FORCE: strategy={strategy.name} owner={strategy.owner} action=force_long")
        strategy.is_processing = True
        try:
            await self._process_long_signal(strategy)
        finally:
            strategy.is_processing = False

    async def force_short(self, strategy: Strategy):
        """Force a short position for a strategy (bypasses cooldown)"""
        logger.info(f"🔥 MANUAL FORCE: strategy={strategy.name} owner={strategy.owner} action=force_short")
        strategy.is_processing = True
        try:
            await self._process_short_signal(strategy)
        finally:
            strategy.is_processing = False

    async def force_close(self, strategy: Strategy):
        """Force close all positions for a strategy (bypasses cooldown)"""
        logger.info(f"🔥 MANUAL FORCE: strategy={strategy.name} owner={strategy.owner} action=force_close")
        strategy.is_processing = True
        try:
            await self._close_all_positions(strategy)
        finally:
            strategy.is_processing = False
