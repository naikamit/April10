# state_manager.py - In-memory state management
from datetime import datetime, timedelta
import threading
import logging

logger = logging.getLogger(__name__)

class StateManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(StateManager, cls).__new__(cls)
                cls._instance._initialize()
            return cls._instance

    def _initialize(self):
        """Initialize the state with default values"""
        self.cash_balance = 0.0
        self.cash_balance_source = "system"
        self.cash_balance_updated_at = datetime.now()
        self.in_cooldown = False
        self.cooldown_end_time = None
        self.api_calls = []
        self.is_processing = False
        # Initialize symbols with default values - will be set from config on startup
        self.long_symbol = "MSTU"
        self.short_symbol = "MSTZ"

    def update_cash_balance(self, amount, source="system"):
        """Update the cash balance with the given amount"""
        with self._lock:
            self.cash_balance = amount
            self.cash_balance_source = source
            self.cash_balance_updated_at = datetime.now()
            logger.info(f"Cash balance updated to {amount} ({source})")

    def get_cash_balance_info(self):
        """Get information about the current cash balance"""
        with self._lock:
            staleness = datetime.now() - self.cash_balance_updated_at
            minutes = staleness.total_seconds() // 60
            hours = minutes // 60
            days = hours // 24
            
            return {
                "balance": self.cash_balance,
                "source": self.cash_balance_source,
                "staleness": {
                    "minutes": int(minutes % 60),
                    "hours": int(hours % 24),
                    "days": int(days)
                },
                "updated_at": self.cash_balance_updated_at.isoformat()
            }

    def start_cooldown(self, duration_hours):
        """Start the cooldown period for the specified duration"""
        with self._lock:
            self.in_cooldown = True
            self.cooldown_end_time = datetime.now() + timedelta(hours=duration_hours)
            logger.info(f"Cooldown started, will end at {self.cooldown_end_time}")

    def check_cooldown(self):
        """Check if we're currently in the cooldown period"""
        with self._lock:
            if not self.in_cooldown:
                return False
                
            if datetime.now() > self.cooldown_end_time:
                self.in_cooldown = False
                logger.info("Cooldown period ended")
                return False
                
            return True

    def add_api_call(self, request, response, timestamp=None):
        """Add an API call to the history"""
        if timestamp is None:
            timestamp = datetime.now()
            
        with self._lock:
            self.api_calls.append({
                "request": request,
                "response": response,
                "timestamp": timestamp.isoformat()
            })
            # Keep only the last 100 API calls
            if len(self.api_calls) > 100:
                self.api_calls.pop(0)

    def get_api_calls(self):
        """Get the history of API calls"""
        with self._lock:
            return list(self.api_calls)

    def set_processing(self, status):
        """Set the processing status"""
        with self._lock:
            self.is_processing = status

    def is_currently_processing(self):
        """Check if we're currently processing a signal"""
        with self._lock:
            return self.is_processing

    def set_symbols(self, long_symbol=None, short_symbol=None):
        """Set the trading symbols"""
        with self._lock:
            if long_symbol is not None:
                self.long_symbol = long_symbol.strip() if long_symbol.strip() else None
                logger.info(f"Long symbol updated to: {self.long_symbol}")
            if short_symbol is not None:
                self.short_symbol = short_symbol.strip() if short_symbol.strip() else None
                logger.info(f"Short symbol updated to: {self.short_symbol}")

    def get_symbols(self):
        """Get the current trading symbols"""
        with self._lock:
            return {
                "long_symbol": self.long_symbol,
                "short_symbol": self.short_symbol
            }
