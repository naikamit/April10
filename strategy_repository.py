# strategy_repository.py - Strategy CRUD operations and in-memory storage
import threading
import logging
from typing import Dict, List, Optional
from strategy import Strategy

logger = logging.getLogger(__name__)

class StrategyRepository:
    """
    Repository for managing Strategy entities with thread-safe CRUD operations.
    Uses in-memory storage with dictionary {strategy_name: Strategy}.
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(StrategyRepository, cls).__new__(cls)
                cls._instance._initialize()
            return cls._instance
    
    def _initialize(self):
        """Initialize the repository with empty strategy storage"""
        self.strategies: Dict[str, Strategy] = {}
        self._storage_lock = threading.Lock()
        logger.info("🔥 STRATEGY REPOSITORY: initialized")
    
    def create_strategy(self, name: str, long_symbol: Optional[str] = None, 
                       short_symbol: Optional[str] = None, cash_balance: float = 0.0) -> Strategy:
        """
        Create a new strategy
        
        Args:
            name: URL-safe strategy name
            long_symbol: Symbol for long signals (optional)
            short_symbol: Symbol for short signals (optional)
            cash_balance: Initial cash balance
            
        Returns:
            Created Strategy instance
            
        Raises:
            ValueError: If strategy name is invalid or already exists
        """
        normalized_name = name.lower()
        
        with self._storage_lock:
            if normalized_name in self.strategies:
                raise ValueError(f"Strategy '{name}' already exists")
            
            strategy = Strategy(name, long_symbol, short_symbol, cash_balance)
            self.strategies[normalized_name] = strategy
            
            logger.info(f"🔥 STRATEGY CREATED: name={strategy.name} display_name={strategy.display_name} "
                       f"long={strategy.long_symbol} short={strategy.short_symbol} cash={strategy.cash_balance}")
            
            return strategy
    
    def get_strategy(self, name: str) -> Optional[Strategy]:
        """
        Get a strategy by name
        
        Args:
            name: Strategy name (case insensitive)
            
        Returns:
            Strategy instance or None if not found
        """
        normalized_name = name.lower()
        
        with self._storage_lock:
            return self.strategies.get(normalized_name)
    
    def get_all_strategies(self) -> List[Strategy]:
        """
        Get all strategies ordered by creation date
        
        Returns:
            List of all Strategy instances ordered by creation_at
        """
        with self._storage_lock:
            strategies = list(self.strategies.values())
            # Sort by creation date as per PRD
            strategies.sort(key=lambda s: s.created_at)
            return strategies
    
    def update_strategy(self, name: str, long_symbol: Optional[str] = None,
                       short_symbol: Optional[str] = None, cash_balance: Optional[float] = None) -> Optional[Strategy]:
        """
        Update an existing strategy
        
        Args:
            name: Strategy name
            long_symbol: New long symbol (if provided)
            short_symbol: New short symbol (if provided)
            cash_balance: New cash balance (if provided)
            
        Returns:
            Updated Strategy instance or None if not found
        """
        normalized_name = name.lower()
        
        with self._storage_lock:
            strategy = self.strategies.get(normalized_name)
            if not strategy:
                return None
            
            # Track what's being updated for logging
            updates = []
            
            if long_symbol is not None:
                old_long = strategy.long_symbol
                strategy.update_symbols(long_symbol=long_symbol)
                updates.append(f"long_symbol: {old_long} -> {strategy.long_symbol}")
            
            if short_symbol is not None:
                old_short = strategy.short_symbol
                strategy.update_symbols(short_symbol=short_symbol)
                updates.append(f"short_symbol: {old_short} -> {strategy.short_symbol}")
            
            if cash_balance is not None:
                old_cash = strategy.cash_balance
                strategy.update_cash_balance(cash_balance)
                updates.append(f"cash_balance: {old_cash} -> {strategy.cash_balance}")
            
            if updates:
                logger.info(f"🔥 STRATEGY UPDATED: name={strategy.name} changes={', '.join(updates)}")
            
            return strategy
    
    def delete_strategy(self, name: str) -> bool:
        """
        Delete a strategy
        
        Args:
            name: Strategy name
            
        Returns:
            True if strategy was deleted, False if not found
        """
        normalized_name = name.lower()
        
        with self._storage_lock:
            if normalized_name in self.strategies:
                strategy = self.strategies.pop(normalized_name)
                logger.info(f"🔥 STRATEGY DELETED: name={strategy.name} display_name={strategy.display_name}")
                return True
            return False
    
    def strategy_exists(self, name: str) -> bool:
        """
        Check if a strategy exists
        
        Args:
            name: Strategy name (case insensitive)
            
        Returns:
            True if strategy exists, False otherwise
        """
        normalized_name = name.lower()
        with self._storage_lock:
            return normalized_name in self.strategies
    
    def get_strategy_names(self) -> List[str]:
        """
        Get list of all strategy names
        
        Returns:
            List of strategy names (lowercase)
        """
        with self._storage_lock:
            return list(self.strategies.keys())
