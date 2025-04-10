# state_manager.py
import json
import logging
import os
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple

from config import Config

logger = logging.getLogger(__name__)

class StateManager:
    """
    Manages the application state including cooldown status and cash balance.
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(StateManager, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance
    
    def _initialize(self) -> None:
        """Initialize the state manager."""
        self.config = Config()
        self._cooldown_active = False
        self._cooldown_end_time = 0  # Unix timestamp
        self._cash_balance = self.config.get("INITIAL_CASH_BALANCE")
        self._cash_balance_source = "initial"
        self._cash_balance_timestamp = time.time()
        self._api_calls: List[Dict[str, Any]] = []
        self._state_file = "state.json"
        
        # Try to load state from file if it exists
        self._load_state()
        
        logger.info(f"StateManager initialized. Cash balance: ${self._cash_balance:.2f}")
    
    def _load_state(self) -> None:
        """Load state from file if it exists."""
        if os.path.exists(self._state_file):
            try:
                with open(self._state_file, 'r') as f:
                    state = json.load(f)
                
                # Only load cooldown and cash info if it exists
                if "cooldown_active" in state:
                    self._cooldown_active = state["cooldown_active"]
                if "cooldown_end_time" in state:
                    self._cooldown_end_time = state["cooldown_end_time"]
                if "cash_balance" in state:
                    self._cash_balance = state["cash_balance"]
                if "cash_balance_source" in state:
                    self._cash_balance_source = state["cash_balance_source"]
                if "cash_balance_timestamp" in state:
                    self._cash_balance_timestamp = state["cash_balance_timestamp"]
                
                # Check if cooldown should still be active
                self._check_cooldown_expiry()
                
                logger.info(f"State loaded from file. Cash balance: ${self._cash_balance:.2f}")
                if self._cooldown_active:
                    end_time = datetime.fromtimestamp(self._cooldown_end_time)
                    now = datetime.now()
                    remaining = end_time - now
                    hours, remainder = divmod(remaining.seconds, 3600)
                    minutes, _ = divmod(remainder, 60)
                    logger.info(f"Cooldown active. Remaining time: {hours}h {minutes}m")
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Failed to load state from file: {e}")
    
    def _save_state(self) -> None:
        """Save state to file."""
        state = {
            "cooldown_active": self._cooldown_active,
            "cooldown_end_time": self._cooldown_end_time,
            "cash_balance": self._cash_balance,
            "cash_balance_source": self._cash_balance_source,
            "cash_balance_timestamp": self._cash_balance_timestamp
        }
        
        try:
            with open(self._state_file, 'w') as f:
                json.dump(state, f)
        except IOError as e:
            logger.error(f"Failed to save state to file: {e}")
    
    def _check_cooldown_expiry(self) -> None:
        """Check if the cooldown period has expired."""
        if self._cooldown_active and time.time() > self._cooldown_end_time:
            self._cooldown_active = False
            logger.info("Cooldown period has expired.")
            self._save_state()
    
    def activate_cooldown(self) -> bool:
        """
        Activate the cooldown period.
        
        Returns:
            bool: True if cooldown was newly activated, False if already active
        """
        self._check_cooldown_expiry()
        
        if not self._cooldown_active:
            self._cooldown_active = True
            cooldown_hours = self.config.get("COOLDOWN_PERIOD_HOURS")
            self._cooldown_end_time = time.time() + (cooldown_hours * 3600)
            logger.info(f"Cooldown period activated for {cooldown_hours} hours.")
            self._save_state()
            return True
        return False
    
    def is_cooldown_active(self) -> bool:
        """
        Check if the cooldown period is active.
        
        Returns:
            bool: True if cooldown is active, False otherwise
        """
        self._check_cooldown_expiry()
        return self._cooldown_active
    
    def get_cooldown_info(self) -> Dict[str, Any]:
        """
        Get information about the cooldown period.
        
        Returns:
            Dict[str, Any]: Dictionary with cooldown information
        """
        self._check_cooldown_expiry()
        
        if not self._cooldown_active:
            return {
                "active": False,
                "remaining_seconds": 0,
                "remaining_formatted": "0h 0m",
                "end_time": None
            }
        
        now = time.time()
        remaining_seconds = max(0, self._cooldown_end_time - now)
        hours, remainder = divmod(int(remaining_seconds), 3600)
        minutes, _ = divmod(remainder, 60)
        remaining_formatted = f"{hours}h {minutes}m"
        
        return {
            "active": True,
            "remaining_seconds": remaining_seconds,
            "remaining_formatted": remaining_formatted,
            "end_time": datetime.fromtimestamp(self._cooldown_end_time).isoformat()
        }
    
    def get_cash_balance(self) -> float:
        """
        Get the current cash balance.
        
        Returns:
            float: Current cash balance
        """
        return self._cash_balance
    
    def get_cash_balance_info(self) -> Dict[str, Any]:
        """
        Get information about the cash balance.
        
        Returns:
            Dict[str, Any]: Dictionary with cash balance information
        """
        now = time.time()
        seconds_since_update = now - self._cash_balance_timestamp
        
        if seconds_since_update < 60:
            age_formatted = f"{int(seconds_since_update)} seconds"
        elif seconds_since_update < 3600:
            age_formatted = f"{int(seconds_since_update / 60)} minutes"
        elif seconds_since_update < 86400:
            age_formatted = f"{int(seconds_since_update / 3600)} hours"
        else:
            age_formatted = f"{int(seconds_since_update / 86400)} days"
        
        return {
            "balance": self._cash_balance,
            "formatted": f"${self._cash_balance:.2f}",
            "source": self._cash_balance_source,
            "timestamp": datetime.fromtimestamp(self._cash_balance_timestamp).isoformat(),
            "age_seconds": seconds_since_update,
            "age_formatted": age_formatted
        }
    
    def update_cash_balance(self, new_balance: float, source: str) -> None:
        """
        Update the cash balance.
        
        Args:
            new_balance (float): New cash balance
            source (str): Source of the update (e.g., "user", "trade", "system")
        """
        if new_balance < 0:
            logger.warning(f"Attempted to set negative cash balance: ${new_balance:.2f}")
            new_balance = 0
        
        self._cash_balance = new_balance
        self._cash_balance_source = source
        self._cash_balance_timestamp = time.time()
        logger.info(f"Cash balance updated to ${new_balance:.2f} (source: {source})")
        self._save_state()
    
    def add_to_cash_balance(self, amount: float, source: str) -> None:
        """
        Add to the cash balance.
        
        Args:
            amount (float): Amount to add
            source (str): Source of the update (e.g., "trade", "system")
        """
        new_balance = self._cash_balance + amount
        self.update_cash_balance(new_balance, source)
    
    def log_api_call(self, request_data: Dict[str, Any], response_data: Dict[str, Any], 
                     success: bool, duration: float) -> None:
        """
        Log an API call.
        
        Args:
            request_data (Dict[str, Any]): Request data
            response_data (Dict[str, Any]): Response data
            success (bool): Whether the call was successful
            duration (float): Duration of the call in seconds
        """
        call_info = {
            "timestamp": time.time(),
            "request": request_data,
            "response": response_data,
            "success": success,
            "duration": duration
        }
        
        self._api_calls.append(call_info)
        
        # Keep the last 100 calls
        if len(self._api_calls) > 100:
            self._api_calls = self._api_calls[-100:]
    
    def get_api_calls(self) -> List[Dict[str, Any]]:
        """
        Get recent API calls.
        
        Returns:
            List[Dict[str, Any]]: List of recent API calls
        """
        # Format the timestamps
        formatted_calls = []
        for call in self._api_calls:
            formatted_call = call.copy()
            formatted_call["formatted_time"] = datetime.fromtimestamp(
                call["timestamp"]).strftime("%Y-%m-%d %H:%M:%S")
            formatted_call["formatted_duration"] = f"{call['duration']:.2f}s"
            formatted_calls.append(formatted_call)
        
        return formatted_calls[::-1]  # Return in reverse order (newest first)
