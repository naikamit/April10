# cooldown_manager.py - Cool down period logic
import logging
from datetime import datetime, timedelta
from state_manager import StateManager
from config import COOLDOWN_PERIOD_HOURS

logger = logging.getLogger(__name__)

class CooldownManager:
    def __init__(self):
        self.state_manager = StateManager()

    def start_cooldown(self):
        """
        Start the cooldown period
        """
        logger.info(f"Starting cooldown period for {COOLDOWN_PERIOD_HOURS} hours")
        self.state_manager.start_cooldown(COOLDOWN_PERIOD_HOURS)

    def is_in_cooldown(self):
        """
        Check if we're currently in the cooldown period
        """
        return self.state_manager.check_cooldown()

    def get_cooldown_info(self):
        """
        Get information about the current cooldown state
        """
        if not self.state_manager.in_cooldown:
            return {"active": False}
            
        now = datetime.now()
        end_time = self.state_manager.cooldown_end_time
        remaining = end_time - now
        
        hours = int(remaining.total_seconds() // 3600)
        minutes = int((remaining.total_seconds() % 3600) // 60)
        
        return {
            "active": True,
            "end_time": end_time.isoformat(),
            "remaining": {
                "hours": hours,
                "minutes": minutes
            }
        }
