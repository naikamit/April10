# strategy.py - Core Strategy entity for multi-strategy trading system
from datetime import datetime
from typing import Optional
import re

class Strategy:
    """
    Core Strategy entity representing an independent trading strategy
    with its own symbols, cash balance, and cooldown state.
    """
    
    def __init__(self, name: str, long_symbol: Optional[str] = None, 
                 short_symbol: Optional[str] = None, cash_balance: float = 0.0):
        """
        Initialize a new Strategy
        
        Args:
            name: URL-safe strategy name (alphanumeric + underscores)
            long_symbol: Symbol to buy for long signals (nullable)
            short_symbol: Symbol to buy for short signals (nullable) 
            cash_balance: Initial cash balance for this strategy
        """
        if not self._is_valid_strategy_name(name):
            raise ValueError(f"Invalid strategy name: {name}. Must be alphanumeric + underscores, 3-50 chars")
        
        self.name = name.lower()  # Store in lowercase for consistency
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
        from datetime import timedelta
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
        """Add API call to this strategy's history"""
        if timestamp is None:
            timestamp = datetime.now()
        
        self.api_calls.append({
            "request": request,
            "response": response,
            "timestamp": timestamp.isoformat()
        })
        
        # Keep only the last 100 API calls per strategy
        if len(self.api_calls) > 100:
            self.api_calls.pop(0)
    
    def get_cooldown_info(self) -> dict:
        """Get cooldown information for this strategy"""
        if not self.in_cooldown:
            return {"active": False}
        
        if not self.cooldown_end_time:
            return {"active": False}
        
        now = datetime.now()
        remaining = self.cooldown_end_time - now
        
        if remaining.total_seconds() <= 0:
            self.stop_cooldown()
            return {"active": False}
        
        hours = int(remaining.total_seconds() // 3600)
        minutes = int((remaining.total_seconds() % 3600) // 60)
        
        return {
            "active": True,
            "end_time": self.cooldown_end_time.isoformat(),
            "remaining": {
                "hours": hours,
                "minutes": minutes
            }
        }
    
    def to_dict(self) -> dict:
        """Convert strategy to dictionary for API responses"""
        return {
            "name": self.name,
            "long_symbol": self.long_symbol,
            "short_symbol": self.short_symbol,
            "cash_balance": self.cash_balance,
            "cooldown": self.get_cooldown_info(),
            "is_processing": self.is_processing,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "api_calls_count": len(self.api_calls)
        }
    
    def __repr__(self):
        return f"Strategy(name='{self.name}', long='{self.long_symbol}', short='{self.short_symbol}', cash={self.cash_balance})"
