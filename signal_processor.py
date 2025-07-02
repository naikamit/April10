# signal_processor.py - Signal processing logic with multi-symbol support
import logging
import asyncio
from typing import Dict, Any, Optional, List

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

    async def process_multi_symbol_signal(self, buy_symbol: Optional[str], sell_symbols: List[str], strategy: Strategy) -> Dict[str, Any]:
        """
        Process a multi-symbol signal for a specific strategy
        Sells symbols in sequence (already in correct order), then buys with all collected cash
        
        Args:
            buy_symbol: Symbol to buy with all collected cash (None for close-only)
            sell_symbols: List of symbols to sell in order (already reversed from URL)
            strategy: Strategy instance to process signal for
            
        Returns:
            Dictionary with processing result
        """
        logger.info(f"🔥 MULTI-SYMBOL PROCESSING: strategy={strategy.name} owner={strategy.owner} buy_symbol={buy_symbol} sell_sequence={sell_symbols} starting_execution")
        
        # Check if strategy is already processing a signal
        if strategy.is_processing:
            logger.warning(f"🔥 MULTI-SYMBOL IGNORED: strategy={strategy.name} owner={strategy.owner} buy={buy_symbol} sell={sell_symbols} reason=already_processing")
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
                
                # Process sell symbols sequentially (in order provided)
                if sell_symbols:
                    logger.info(f"🔥 MULTI-SYMBOL PROCESSING: strategy={strategy.name} owner={strategy.owner} selling_sequence={sell_symbols}")
                    for i, sell_symbol in enumerate(sell_symbols):
                        logger.info(f"🔥 SELLING SEQUENCE: strategy={strategy.name} owner={strategy.owner} step={i+1}/{len(sell_symbols)} symbol={sell_symbol}")
                        await self._close_symbol_position(sell_symbol, strategy)
                        # Brief pause between sells
                        if i < len(sell_symbols) - 1:
                            await asyncio.sleep(1)
                else:
                    logger.info(f"🔥 MULTI-SYMBOL PROCESSING: strategy={strategy.name} owner={strategy.owner} no_sell_symbols skipping_sell_phase")
                
                # Process buy symbol if provided
                if buy_symbol:
                    logger.info(f"🔥 MULTI-SYMBOL PROCESSING: strategy={strategy.name} owner={strategy.owner} buying_symbol={buy_symbol} with_all_available_cash")
                    await self._buy_symbol_all_cash(buy_symbol, strategy)
                    # Pause for 3 seconds as specified in requirements
                    await asyncio.sleep(3)
                else:
                    logger.info(f"🔥 MULTI-SYMBOL PROCESSING: strategy={strategy.name} owner={strategy.owner} no_buy_symbol close_only_operation")
                
                if not sell_symbols and not buy_symbol:
                    logger.warning(f"🔥 MULTI-SYMBOL WARNING: strategy={strategy.name} owner={strategy.owner} no_operations_provided no_action_taken")
            else:
                # In cooldown period, do nothing
                logger.info(f"🔥 MULTI-SYMBOL IGNORED: strategy={strategy.name} owner={strategy.owner} buy={buy_symbol} sell={sell_symbols} reason=in_cooldown")
                
            strategy.is_processing = False
            logger.info(f"🔥 MULTI-SYMBOL COMPLETE: strategy={strategy.name} owner={strategy.owner} buy={buy_symbol} sell={sell_symbols} result=success")
            return {"status": "success"}
            
        except Exception as e:
            logger.exception(f"🔥 ERROR: strategy={strategy.name} owner={strategy.owner} multi_symbol_signal_processing_error={str(e)}")
            strategy.is_processing = False
            return {"status": "error", "reason": str(e)}

    async def _buy_symbol_all_cash(self, symbol: str, strategy: Strategy):
        """
        Buy a symbol with ALL available cash (aggressive buying)
        Uses a different approach than the retry logic - just goes all-in
        
        Args:
            symbol: Symbol to buy
            strategy: Strategy instance
        """
        logger.info(f"🔥 ALL-CASH BUYING: strategy={strategy.name} owner={strategy.owner} symbol={symbol} using_all_available_cash")
        
        # Get current cash balance
        available_cash = strategy.cash_balance
        
        if available_cash <= 5:  # Minimum cash check
            logger.info(f"🔥 ALL-CASH BUYING: strategy={strategy.name} owner={strategy.owner} symbol={symbol} insufficient_cash={available_cash}")
            return
        
        # Buy 1 share to get current price
        success, price, response = await self.api_client.buy_symbol(symbol, 1, strategy)
        
        if not success or price is None:
            logger.error(f"🔥 ERROR: strategy={strategy.name} owner={strategy.owner} symbol={symbol} failed_to_get_price_for_all_cash_buy")
            return
        
        # Update cash balance after the 1-share purchase
        self.cash_manager.update_balance_from_buy(price, 1, strategy)
        
        # Calculate max shares with remaining cash
        max_shares = self.cash_manager.get_max_shares(price, strategy)
        
        if max_shares <= 0:
            logger.info(f"🔥 ALL-CASH BUYING COMPLETE: strategy={strategy.name} owner={strategy.owner} symbol={symbol} bought_1_share only_enough_cash_for_1")
            return
        
        # Try to buy all remaining shares (no retry logic, just all-in)
        logger.info(f"🔥 ALL-CASH BUYING: strategy={strategy.name} owner={strategy.owner} symbol={symbol} attempting_max_shares={max_shares}")
        
        success, final_price, response = await self.api_client.buy_symbol(symbol, max_shares, strategy)
        
        if success:
            logger.info(f"🔥 API RESPONSE: strategy={strategy.name} owner={strategy.owner} action=all_cash_buy symbol={symbol} price={final_price} quantity={max_shares}")
            # Reduce cash balance by the amount spent
            if final_price:
                self.cash_manager.update_balance_from_buy(final_price, max_shares, strategy)
            logger.info(f"🔥 ALL-CASH BUYING COMPLETE: strategy={strategy.name} owner={strategy.owner} symbol={symbol} total_shares={1 + max_shares} all_cash_used")
        else:
            logger.error(f"🔥 ERROR: strategy={strategy.name} owner={strategy.owner} symbol={symbol} all_cash_buy_failed bought_1_share_only")
            logger.info(f"🔥 ALL-CASH BUYING COMPLETE: strategy={strategy.name} owner={strategy.owner} symbol={symbol} total_shares=1 max_buy_failed")

    # Legacy methods for backward compatibility and dashboard operations

    async def process_buy_sell_signal(self, buy_symbol: Optional[str], sell_symbol: Optional[str], strategy: Strategy) -> Dict[str, Any]:
        """
        LEGACY: Process a buy/sell signal with two symbols (for backward compatibility)
        
        Args:
            buy_symbol: Symbol to buy (None if not buying)
            sell_symbol: Symbol to sell (None if not selling)
            strategy: Strategy instance to process signal for
            
        Returns:
            Dictionary with processing result
        """
        logger.info(f"🔥 LEGACY BUY/SELL PROCESSING: strategy={strategy.name} owner={strategy.owner} buy_symbol={buy_symbol} sell_symbol={sell_symbol}")
        
        # Convert to multi-symbol format
        sell_symbols = [sell_symbol] if sell_symbol else []
        return await self.process_multi_symbol_signal(buy_symbol, sell_symbols, strategy)

    async def process_close_symbols_signal(self, symbol_list: List[str], strategy: Strategy) -> Dict[str, Any]:
        """
        LEGACY: Process a close signal for multiple symbols (for backward compatibility)
        
        Args:
            symbol_list: List of symbols to close positions for
            strategy: Strategy instance to process signal for
            
        Returns:
            Dictionary with processing result
        """
        logger.info(f"🔥 LEGACY CLOSE SYMBOLS PROCESSING: strategy={strategy.name} owner={strategy.owner} symbols={symbol_list}")
        
        # Convert to multi-symbol format (close-only)
        return await self.process_multi_symbol_signal(None, symbol_list, strategy)

    async def process_signal(self, signal_type: str, strategy: Strategy) -> Dict[str, Any]:
        """
        LEGACY: Process a signal for a specific strategy using dashboard symbols
        Used by dashboard Force operations
        
        Args:
            signal_type: Type of signal ('long', 'short', 'close')
            strategy: Strategy instance to process signal for
            
        Returns:
            Dictionary with processing result
        """
        logger.info(f"🔥 LEGACY SIGNAL PROCESSING: strategy={strategy.name} owner={strategy.owner} signal={signal_type} using_dashboard_symbols")
        
        # Check if strategy is already processing a signal
        if strategy.is_processing:
            logger.warning(f"🔥 LEGACY SIGNAL IGNORED: strategy={strategy.name} owner={strategy.owner} signal={signal_type} reason=already_processing")
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
                
                # Process normal signal (not in cooldown) using dashboard symbols
                if signal_type == "long":
                    await self._process_long_signal_dashboard(strategy)
                elif signal_type == "short":
                    await self._process_short_signal_dashboard(strategy)
                elif signal_type == "close":
                    await self._close_all_positions_dashboard(strategy)
                else:
                    logger.error(f"🔥 ERROR: strategy={strategy.name} owner={strategy.owner} unknown_legacy_signal_type={signal_type}")
                    strategy.is_processing = False
                    return {"status": "error", "reason": f"Unknown signal type: {signal_type}"}
            else:
                # In cooldown period, do nothing
                logger.info(f"🔥 LEGACY SIGNAL IGNORED: strategy={strategy.name} owner={strategy.owner} signal={signal_type} reason=in_cooldown")
                
            strategy.is_processing = False
            logger.info(f"🔥 LEGACY SIGNAL COMPLETE: strategy={strategy.name} owner={strategy.owner} signal={signal_type} result=success")
            return {"status": "success"}
            
        except Exception as e:
            logger.exception(f"🔥 ERROR: strategy={strategy.name} owner={strategy.owner} legacy_signal_processing_error={str(e)}")
            strategy.is_processing = False
            return {"status": "error", "reason": str(e)}

    async def _process_long_signal_dashboard(self, strategy: Strategy):
        """
        Process a long signal for a strategy using dashboard symbols:
        1. Close short positions (dashboard short symbol)
        2. Buy long symbol (dashboard long symbol)
        """
        logger.info(f"🔥 LEGACY LONG SIGNAL: strategy={strategy.name} owner={strategy.owner} using_dashboard_symbols long={strategy.long_symbol} short={strategy.short_symbol}")
        
        # 1. Close short positions
        if strategy.short_symbol:
            await self._close_symbol_position(strategy.short_symbol, strategy)
        else:
            logger.info(f"🔥 LEGACY LONG SIGNAL: strategy={strategy.name} owner={strategy.owner} dashboard_short_symbol=null skipping_close")
        
        # 2. Buy long symbol if not null
        if strategy.long_symbol:
            await self._buy_symbol(strategy.long_symbol, strategy)
            # Pause for 3 seconds as specified in requirements
            await asyncio.sleep(3)
        else:
            logger.info(f"🔥 LEGACY LONG SIGNAL: strategy={strategy.name} owner={strategy.owner} dashboard_long_symbol=null skipping_buy")

    async def _process_short_signal_dashboard(self, strategy: Strategy):
        """
        Process a short signal for a strategy using dashboard symbols:
        1. Close long positions (dashboard long symbol)
        2. Buy short symbol (dashboard short symbol)
        """
        logger.info(f"🔥 LEGACY SHORT SIGNAL: strategy={strategy.name} owner={strategy.owner} using_dashboard_symbols long={strategy.long_symbol} short={strategy.short_symbol}")
        
        # 1. Close long positions
        if strategy.long_symbol:
            await self._close_symbol_position(strategy.long_symbol, strategy)
        else:
            logger.info(f"🔥 LEGACY SHORT SIGNAL: strategy={strategy.name} owner={strategy.owner} dashboard_long_symbol=null skipping_close")
        
        # 2. Buy short symbol if not null
        if strategy.short_symbol:
            await self._buy_symbol(strategy.short_symbol, strategy)
            # Pause for 3 seconds as specified in requirements
            await asyncio.sleep(3)
        else:
            logger.info(f"🔥 LEGACY SHORT SIGNAL: strategy={strategy.name} owner={strategy.owner} dashboard_short_symbol=null skipping_buy")

    async def _close_all_positions_dashboard(self, strategy: Strategy):
        """
        Close all positions for both dashboard symbols in a strategy
        """
        logger.info(f"🔥 LEGACY CLOSE SIGNAL: strategy={strategy.name} owner={strategy.owner} using_dashboard_symbols closing_all_positions long={strategy.long_symbol} short={strategy.short_symbol}")
        
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
            logger.info(f"🔥 LEGACY CLOSE SIGNAL: strategy={strategy.name} owner={strategy.owner} no_dashboard_symbols_to_close")

    async def _buy_symbol(self, symbol: str, strategy: Strategy):
        """
        LEGACY: Buy a symbol with retry logic for a strategy (used by dashboard operations)
        1. Buy 1 share to get current price
        2. Calculate max shares based on remaining cash
        3. Buy max shares with retry logic
        """
        logger.info(f"🔥 LEGACY BUYING SHARES: strategy={strategy.name} owner={strategy.owner} symbol={symbol} attempting_purchase_with_retry")
        
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
            logger.info(f"🔥 LEGACY BUYING COMPLETE: strategy={strategy.name} owner={strategy.owner} symbol={symbol} bought_1_share only_enough_cash_for_1")
            return
        
        # 3. Try to buy additional shares with retry logic
        logger.info(f"🔥 LEGACY BUYING SHARES: strategy={strategy.name} owner={strategy.owner} symbol={symbol} max_additional_shares={max_shares} attempting_purchase")
        
        retries = 0
        shares_to_buy = max_shares
        
        while retries < MAX_BUY_RETRIES:
            success, final_price, response = await self.api_client.buy_symbol(symbol, shares_to_buy, strategy)
            
            if success:
                logger.info(f"🔥 API RESPONSE: strategy={strategy.name} owner={strategy.owner} action=legacy_buy symbol={symbol} price={final_price} quantity={shares_to_buy}")
                # Reduce cash balance by the amount spent
                if final_price:
                    self.cash_manager.update_balance_from_buy(final_price, shares_to_buy, strategy)
                logger.info(f"🔥 LEGACY BUYING COMPLETE: strategy={strategy.name} owner={strategy.owner} symbol={symbol} total_shares={1 + shares_to_buy}")
                return
            
            # Calculate reduced shares for retry (ensure at least 1 fewer share)
            reduction = max(1, int(shares_to_buy * BUY_RETRY_REDUCTION_PERCENT / 100))
            shares_to_buy = max(1, shares_to_buy - reduction)
            
            logger.info(f"🔥 LEGACY BUY RETRY: strategy={strategy.name} owner={strategy.owner} symbol={symbol} shares={shares_to_buy} retry={retries+1}/{MAX_BUY_RETRIES}")
            retries += 1
            await asyncio.sleep(3)  # Pause before retry
        
        logger.error(f"🔥 ERROR: strategy={strategy.name} owner={strategy.owner} symbol={symbol} max_legacy_buy_retries_exceeded={MAX_BUY_RETRIES} bought_1_share_only")
        logger.info(f"🔥 LEGACY BUYING COMPLETE: strategy={strategy.name} owner={strategy.owner} symbol={symbol} total_shares=1 additional_buys_failed")

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

    # Force methods for manual trading (bypass cooldown, use dashboard symbols)
    async def force_long(self, strategy: Strategy):
        """Force a long position for a strategy using dashboard symbols (bypasses cooldown)"""
        logger.info(f"🔥 MANUAL FORCE: strategy={strategy.name} owner={strategy.owner} action=force_long using_dashboard_symbols")
        strategy.is_processing = True
        try:
            await self._process_long_signal_dashboard(strategy)
        finally:
            strategy.is_processing = False

    async def force_short(self, strategy: Strategy):
        """Force a short position for a strategy using dashboard symbols (bypasses cooldown)"""
        logger.info(f"🔥 MANUAL FORCE: strategy={strategy.name} owner={strategy.owner} action=force_short using_dashboard_symbols")
        strategy.is_processing = True
        try:
            await self._process_short_signal_dashboard(strategy)
        finally:
            strategy.is_processing = False

    async def force_close(self, strategy: Strategy):
        """Force close all positions for a strategy using dashboard symbols (bypasses cooldown)"""
        logger.info(f"🔥 MANUAL FORCE: strategy={strategy.name} owner={strategy.owner} action=force_close using_dashboard_symbols")
        strategy.is_processing = True
        try:
            await self._close_all_positions_dashboard(strategy)
        finally:
            strategy.is_processing = False
