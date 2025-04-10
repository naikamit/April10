# cash_manager.py - Cash balance tracking
import logging
from state_manager import StateManager
from config import MINIMUM_CASH_BALANCE

logger = logging.getLogger(__name__)

class CashManager:
    def __init__(self):
        self.state_manager = StateManager()

    def get_max_shares(self, price):
        """
        Calculate the maximum number of whole shares that can be bought
        """
        cash_balance = self.state_manager.cash_balance
        
        if cash_balance <= MINIMUM_CASH_BALANCE:
            logger.info(f"Cash balance ({cash_balance}) <= minimum ({MINIMUM_CASH_BALANCE}), can't buy shares")
            return 0
            
        # Calculate max shares (whole shares only)
        max_shares = int(cash_balance / price)
        
        logger.info(f"Cash balance: {cash_balance}, price: {price}, max shares: {max_shares}")
        return max_shares

    def update_balance_from_close(self, price, quantity):
        """
        Update cash balance after closing a position
        """
        if price is not None and quantity is not None:
            amount = price * quantity
            current_balance = self.state_manager.cash_balance
            new_balance = current_balance + amount
            
            logger.info(f"Updating cash balance: {current_balance} + ({price} * {quantity}) = {new_balance}")
            self.state_manager.update_cash_balance(new_balance)
            
            return new_balance
        return self.state_manager.cash_balance

    def update_balance_manual(self, amount):
        """
        Update cash balance manually
        """
        try:
            amount = float(amount)
            self.state_manager.update_cash_balance(amount, source="user")
            logger.info(f"Cash balance manually updated to: {amount}")
            return True
        except ValueError:
            logger.error(f"Invalid cash balance amount: {amount}")
            return False
