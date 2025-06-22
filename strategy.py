# strategy.py - Core Strategy entity for multi-strategy trading system
from datetime import datetime, timedelta
from typing import Optional
import re

class Strategy:
    """
    Core Strategy entity representing an independent trading strategy
    with its own symbols, cash balance, cooldown state, and owner.
    """
    
    def __init__(self, name: str, owner: str, long_symbol: Optional[str] = None, 
                 short_symbol: Optional[str] = None, cash_balance: float = 0.0):
        """
        Initialize a new Strategy
        
        Args:
            name: URL-safe strategy name (alphanumeric + underscores)
            owner: Username who owns this strategy
            long_symbol: Symbol to buy for long signals (nullable)
            short_symbol: Symbol to buy for short signals (nullable) 
            cash_balance: Initial cash balance for this strategy
        """
        try:
            if not self._is_valid_strategy_name(name):
                raise ValueError(f"Invalid strategy name: {name}. Must be alphanumeric + underscores, 3-50 chars")
            
            if not self._is_valid_username(owner):
                raise ValueError(f"Invalid owner: {owner}. Must be alphanumeric + underscores, 3-50 chars")
            
            # Set core attributes first
            self.name = name.lower()  # Store in lowercase for URL consistency
            self.display_name = name  # Preserve original casing for UI display
            self.owner = owner.lower()  # Store owner in lowercase for URL consistency
            
            # Process symbols
            self.long_symbol = long_symbol.strip() if long_symbol and long_symbol.strip() else None
            self.short_symbol = short_symbol.strip() if short_symbol and short_symbol.strip() else None
            self.cash_balance = float(cash_balance)
            
            # Cooldown state
            self.in_cooldown = False
            self.cooldown_end_time: Optional[datetime] = None
            
            # Timestamps
            self.created_at = datetime.now()
            self.updated_at = datetime.now()
            
            # Processing state
            self.is_processing = False
            
            # API call history for this strategy
            self.api_calls = []
            
        except Exception as e:
            # If anything fails during init, log it
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Strategy.__init__ failed for name='{name}' owner='{owner}': {str(e)}")
            raise
    
    @property
    def display_name_safe(self) -> str:
        """Safe access to display_name with fallback"""
        return getattr(self, 'display_name', self.name)
    
    @staticmethod
    def _is_valid_strategy_name(name: str) -> bool:
        """
        Validate strategy name follows URL-safe rules:
        - Alphanumeric + underscores only
        - 3-50 characters
        - Case insensitive
        - Cannot be reserved names
        """
        if not name or not isinstance(name, str):
            return False
        
        # Check length
        if len(name) < 3 or len(name) > 50:
            return False
        
        # Check pattern (alphanumeric + underscores)
        if not re.match(r'^[a-zA-Z0-9_]+$', name):
            return False
        
        # Check for reserved names
        reserved_names = {'strategies', 'static', 'api', 'status', 'debug'}
        if name.lower() in reserved_names:
            return False
        
        return True
    
    @staticmethod
    def _is_valid_username(username: str) -> bool:
        """
        Validate username follows URL-safe rules:
        - Alphanumeric + underscores only
        - 3-50 characters
        - Case insensitive
        - Cannot be reserved names
        """
        if not username or not isinstance(username, str):
            return False
        
        # Check length
        if len(username) < 3 or len(username) > 50:
            return False
        
        # Check pattern (alphanumeric + underscores)
        if not re.match(r'^[a-zA-Z0-9_]+$', username):
            return False
        
        # Check for reserved names
        reserved_names = {'strategies', 'static', 'api', 'status', 'debug', 'health', 'ping'}
        if username.lower() in reserved_names:
            return False
        
        return True
    
    def update_symbols(self, long_symbol: Optional[str] = None, short_symbol: Optional[str] = None):
        """Update trading symbols for this strategy"""
        if long_symbol is not None:
            self.long_symbol = long_symbol.strip() if long_symbol.strip() else None
        if short_symbol is not None:
            self.short_symbol = short_symbol.strip() if short_symbol.strip() else None
        self.updated_at = datetime.now()
    
    def update_cash_balance(self, amount: float):
        """Update cash balance for this strategy"""
        self.cash_balance = float(amount)
        self.updated_at = datetime.now()
    
    def start_cooldown(self, duration_hours: int):
        """Start cooldown period for this strategy"""
        self.in_cooldown = True
        self.cooldown_end_time = datetime.now() + timedelta(hours=duration_hours)
        self.updated_at = datetime.now()
    
    def stop_cooldown(self):
        """Stop cooldown period for this strategy"""
        self.in_cooldown = False
        self.cooldown_end_time = None
        self.updated_at = datetime.now()
    
    def check_cooldown(self) -> bool:
        """Check if strategy is currently in cooldown"""
        if not self.in_cooldown:
            return False
        
        if self.cooldown_end_time and datetime.now() > self.cooldown_end_time:
            self.stop_cooldown()
            return False
        
        return True
    
    def add_api_call(self, request: dict, response: dict, timestamp: Optional[datetime] = None):
        """Add API call to this strategy's history with persistence"""
        # Import here to avoid circular imports
        from strategy_repository import StrategyRepository
        repo = StrategyRepository()
        repo.add_api_call_sync(self, request, response, timestamp)
    
    def get_cooldown_info(self) -> dict:
        """Get cooldown information for this strategy"""
        if not self.in_cooldown:
            return {"
