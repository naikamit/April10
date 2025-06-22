# cooldown_manager.py - Cool down period logic - Updated for multi-user support
import logging
from datetime import datetime, timedelta
from strategy import Strategy
from config import COOLDOWN_PERIOD_HOURS

logger = logging.getLogger(__name__)

class CooldownManager:
    def __init__(self):
        pass

    def start_cooldown(self, strategy: Strategy):
        """
        Start the cooldown period for a specific strategy
        
        Args:
            strategy: Strategy instance to start cooldown for
        """
        logger.info(f"🔥 COOLDOWN STARTED: user={strategy.user_id} strategy={strategy.name} duration={COOLDOWN_PERIOD_HOURS}h end_time={strategy.cooldown_end_time}")
        strategy.start_cooldown(COOLDOWN_PERIOD_HOURS)

    def is_in_cooldown(self, strategy: Strategy) -> bool:
        """
        Check if a strategy is currently in the cooldown period
        
        Args:
            strategy: Strategy instance to check
            
        Returns:
            True if in cooldown, False otherwise
        """
        return strategy.check_cooldown()

    def stop_cooldown(self, strategy: Strategy):
        """
        Manually stop cooldown period for a strategy
        
        Args:
            strategy: Strategy instance to stop cooldown for
        """
        strategy.stop_cooldown()
        logger.info(f"🔥 COOLDOWN STOPPED: user={strategy.user_id} strategy={strategy.name} manually_stopped=true")

    def get_cooldown_info(self, strategy: Strategy) -> dict:
        """
        Get information about the current cooldown state for a strategy
        
        Args:
            strategy: Strategy instance to get cooldown info for
            
        Returns:
            Dictionary with cooldown information
        """
        return strategy.get_cooldown_info()
