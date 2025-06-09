# cash_manager.py - Cash balance tracking with persistence integration
import logging
from strategy import Strategy
from config import MINIMUM_CASH_BALANCE

logger = logging.getLogger(__name__)

class CashManager:
    def __init__(self):
        pass

    def get_max_shares(self, price: float, strategy: Strategy) -> int:
        """
        Calculate the maximum number of whole shares that can be bought for a strategy
        
        Args:
            price: Price per share
            strategy: Strategy instance to check cash balance
            
        Returns:
            Maximum number of whole shares that can be bought
        """
        cash_balance = strategy.cash_balance
        
        if cash_balance <= MINIMUM_CASH_BALANCE:
            logger.info(f"🔥 CASH CHECK: strategy={strategy.name} cash_balance={cash_balance} minimum={MINIMUM_CASH_BALANCE} insufficient_cash=true")
            return 0
            
        # Calculate max shares (whole shares only)
        max_shares = int(cash_balance / price)
        
        logger.info(f"🔥 CASH CHECK: strategy={strategy.name} cash_balance={cash_balance} price={price} max_shares={max_shares}")
        return max_shares

    def update_balance_from_close(self, price: float, quantity: int, strategy: Strategy) -> float:
        """
        Update cash balance after closing a position with persistence
        
        Args:
            price: Price per share when closed
            quantity: Number of shares closed
            strategy: Strategy instance to update
            
        Returns:
            New cash balance
        """
        if price is not None and quantity is not None:
            amount = price * quantity
            current_balance = strategy.cash_balance
            new_balance = current_balance + amount
            
            logger.info(f"🔥 CASH UPDATE: strategy={strategy.name} old_balance={current_balance} proceeds={amount} new_balance={new_balance}")
            
            # Update strategy cash balance and persist to disk
            self._update_strategy_cash_with_persistence(strategy, new_balance)
            
            return new_balance
        return strategy.cash_balance

    def update_balance_from_buy(self, price: float, quantity: int, strategy: Strategy) -> float:
        """
        Update cash balance after buying shares with persistence
        
        Args:
            price: Price per share when bought
            quantity: Number of shares bought
            strategy: Strategy instance to update
            
        Returns:
            New cash balance
        """
        if price is not None and quantity is not None:
            amount = price * quantity
            current_balance = strategy.cash_balance
            new_balance = current_balance - amount
            
            logger.info(f"🔥 CASH UPDATE: strategy={strategy.name} old_balance={current_balance} spent={amount} new_balance={new_balance}")
            
            # Update strategy cash balance and persist to disk
            self._update_strategy_cash_with_persistence(strategy, new_balance)
            
            return new_balance
        return strategy.cash_balance

    def update_balance_manual(self, amount: float, strategy: Strategy) -> bool:
        """
        Update cash balance manually for a strategy with persistence
        
        Args:
            amount: New cash balance amount
            strategy: Strategy instance to update
            
        Returns:
            True if successful, False if invalid amount
        """
        try:
            amount = float(amount)
            old_balance = strategy.cash_balance
            
            # Update strategy cash balance and persist to disk
            self._update_strategy_cash_with_persistence(strategy, amount)
            
            logger.info(f"🔥 CASH UPDATE: strategy={strategy.name} manual_update old_balance={old_balance} new_balance={amount}")
            return True
        except ValueError:
            logger.error(f"🔥 ERROR: strategy={strategy.name} invalid_cash_amount={amount}")
            return False

    def _update_strategy_cash_with_persistence(self, strategy: Strategy, new_amount: float):
        """
        Update strategy cash balance and persist to disk immediately
        
        Args:
            strategy: Strategy instance to update
            new_amount: New cash balance amount
        """
        # Import here to avoid circular imports
        from strategy_repository import StrategyRepository
        
        # Update the strategy object
        strategy.update_cash_balance(new_amount)
        
        # Persist to disk via repository (synchronous for data integrity)
        repo = StrategyRepository()
        repo.update_strategy(strategy.name, cash_balance=new_amount)
        
        logger.debug(f"🔥 PERSISTENCE: cash balance persisted for strategy={strategy.name} amount={new_amount}")
