# strategy_repository.py - Strategy CRUD operations with JSON file persistence
import threading
import logging
import json
import os
import asyncio
from datetime import datetime
from typing import Dict, List, Optional
from strategy import Strategy

logger = logging.getLogger(__name__)

class AsyncWriteManager:
    """Manages background writes for API call logs to avoid blocking API responses"""
    
    def __init__(self):
        self.write_queue = asyncio.Queue()
        self.background_task = None
        self.running = False
    
    async def start(self):
        """Start the background write worker"""
        if self.running:
            return
        
        self.running = True
        self.background_task = asyncio.create_task(self._background_writer())
        logger.info("🔥 PERSISTENCE: async write manager started")
    
    async def stop(self):
        """Stop the background write worker gracefully"""
        if not self.running:
            return
        
        self.running = False
        if self.background_task:
            # Add a stop signal to queue
            await self.write_queue.put(None)
            try:
                await asyncio.wait_for(self.background_task, timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("🔥 PERSISTENCE: background writer timeout during shutdown")
                self.background_task.cancel()
        
        logger.info("🔥 PERSISTENCE: async write manager stopped")
    
    async def queue_api_log_write(self, strategy_name: str, api_calls: List[dict]):
        """Queue an API log write (non-blocking)"""
        if not self.running:
            await self.start()
        
        try:
            await self.write_queue.put(('api_log', strategy_name, api_calls.copy()))
        except Exception as e:
            logger.error(f"🔥 ERROR: failed to queue API log write for {strategy_name}: {str(e)}")
    
    async def _background_writer(self):
        """Background coroutine that processes the write queue"""
        logger.info("🔥 PERSISTENCE: background writer started")
        
        while self.running:
            try:
                # Wait for write tasks with timeout
                write_task = await asyncio.wait_for(self.write_queue.get(), timeout=1.0)
                
                # Check for stop signal
                if write_task is None:
                    break
                
                write_type, strategy_name, data = write_task
                
                if write_type == 'api_log':
                    try:
                        api_log_file = f'/app/data/api_logs/{strategy_name}.json'
                        _atomic_write_json(data, api_log_file)
                        logger.debug(f"🔥 PERSISTENCE: API logs written for {strategy_name}")
                    except Exception as e:
                        logger.error(f"🔥 ERROR: background API log write failed for {strategy_name}: {str(e)}")
                
            except asyncio.TimeoutError:
                # Normal timeout, continue loop
                continue
            except Exception as e:
                logger.error(f"🔥 ERROR: background writer error: {str(e)}")
        
        logger.info("🔥 PERSISTENCE: background writer stopped")

def _ensure_data_directory():
    """Ensure data directories exist, create if needed"""
    try:
        os.makedirs('/app/data', exist_ok=True)
        os.makedirs('/app/data/api_logs', exist_ok=True)
        return True
    except Exception as e:
        logger.error(f"🔥 ERROR: failed to create data directories: {str(e)}")
        return False

def _atomic_write_json(data, file_path: str):
    """Write JSON data atomically using temp file + rename"""
    temp_path = f"{file_path}.tmp"
    
    try:
        # Ensure parent directory exists
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        # Write to temp file
        with open(temp_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        # Atomic rename (POSIX guarantees atomicity)
        os.rename(temp_path, file_path)
        
    except Exception as e:
        # Clean up temp file if it exists
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except:
                pass
        raise e

def _load_json_file(file_path: str, default_value=None):
    """Load JSON file with error handling and fallback"""
    if not os.path.exists(file_path):
        return default_value if default_value is not None else {}
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data
    except json.JSONDecodeError as e:
        logger.error(f"🔥 ERROR: corrupted JSON file {file_path}: {str(e)}")
        return default_value if default_value is not None else {}
    except Exception as e:
        logger.error(f"🔥 ERROR: failed to read file {file_path}: {str(e)}")
        return default_value if default_value is not None else {}

class StrategyRepository:
    """
    Repository for managing Strategy entities with JSON file persistence.
    Uses /app/data/strategies.json for strategy data and /app/data/api_logs/ for API call logs.
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
        """Initialize the repository and load data from disk"""
        self.strategies: Dict[str, Strategy] = {}
        self._storage_lock = threading.Lock()
        self._async_write_manager = AsyncWriteManager()
        self._disk_available = False
        
        # Check if disk is available and load data
        self._disk_available = _ensure_data_directory()
        
        if self._disk_available:
            self._load_strategies_from_disk()
            logger.info(f"🔥 PERSISTENCE: repository initialized with disk storage, loaded {len(self.strategies)} strategies")
        else:
            logger.warning("🔥 PERSISTENCE: disk not available, using memory-only mode")
    
    def _load_strategies_from_disk(self):
        """Load all strategies and their API logs from disk"""
        strategies_file = '/app/data/strategies.json'
        
        # Load strategy configurations
        strategies_data = _load_json_file(strategies_file, {})
        
        for strategy_name, strategy_data in strategies_data.items():
            try:
                # Handle backward compatibility - if no owner field, use 'default'
                owner = strategy_data.get('owner', 'default')
                
                # Create strategy object from saved data
                strategy = Strategy(
                    name=strategy_data.get('name', strategy_name),
                    owner=owner,
                    long_symbol=strategy_data.get('long_symbol'),
                    short_symbol=strategy_data.get('short_symbol'),
                    cash_balance=strategy_data.get('cash_balance', 0.0)
                )
                
                # Restore timestamps
                if 'created_at' in strategy_data:
                    try:
                        strategy.created_at = datetime.fromisoformat(strategy_data['created_at'].replace('Z', '+00:00'))
                    except:
                        pass  # Keep default if parse fails
                
                if 'updated_at' in strategy_data:
                    try:
                        strategy.updated_at = datetime.fromisoformat(strategy_data['updated_at'].replace('Z', '+00:00'))
                    except:
                        pass  # Keep default if parse fails
                
                # Restore cooldown state
                if strategy_data.get('in_cooldown', False) and 'cooldown_end_time' in strategy_data:
                    try:
                        cooldown_end = datetime.fromisoformat(strategy_data['cooldown_end_time'].replace('Z', '+00:00'))
                        if datetime.now() < cooldown_end:
                            strategy.in_cooldown = True
                            strategy.cooldown_end_time = cooldown_end
                        else:
                            # Cooldown expired, clear it
                            strategy.in_cooldown = False
                            strategy.cooldown_end_time = None
                    except:
                        # Invalid cooldown time, clear it
                        strategy.in_cooldown = False
                        strategy.cooldown_end_time = None
                
                # Load API call logs
                api_log_file = f'/app/data/api_logs/{strategy_name}.json'
                api_calls = _load_json_file(api_log_file, [])
                strategy.api_calls = api_calls[-100:]  # Keep only last 100
                
                self.strategies[strategy_name.lower()] = strategy
                logger.debug(f"🔥 PERSISTENCE: loaded strategy {strategy.name} (owner: {strategy.owner}) with {len(strategy.api_calls)} API calls")
                
            except Exception as e:
                logger.error(f"🔥 ERROR: failed to load strategy {strategy_name}: {str(e)}")
                continue
    
    def _save_strategies_to_disk(self):
        """Save all strategy configurations to disk (synchronous)"""
        if not self._disk_available:
            logger.debug("🔥 PERSISTENCE: disk not available, skipping strategy save")
            return
        
        strategies_file = '/app/data/strategies.json'
        
        try:
            # Convert strategies to JSON-serializable format
            strategies_data = {}
            for strategy_name, strategy in self.strategies.items():
                strategies_data[strategy_name] = {
                    'name': strategy.name,
                    'display_name': getattr(strategy, 'display_name', strategy.name),
                    'owner': strategy.owner,
                    'long_symbol': strategy.long_symbol,
                    'short_symbol': strategy.short_symbol,
                    'cash_balance': strategy.cash_balance,
                    'in_cooldown': strategy.in_cooldown,
                    'cooldown_end_time': strategy.cooldown_end_time.isoformat() if strategy.cooldown_end_time else None,
                    'created_at': strategy.created_at.isoformat(),
                    'updated_at': strategy.updated_at.isoformat()
                }
            
            _atomic_write_json(strategies_data, strategies_file)
            logger.debug(f"🔥 PERSISTENCE: saved {len(strategies_data)} strategies to disk")
            
        except Exception as e:
            logger.error(f"🔥 ERROR: failed to save strategies to disk: {str(e)}")
    
    async def _save_api_logs_async(self, strategy_name: str, api_calls: List[dict]):
        """Save API logs asynchronously (non-blocking)"""
        if not self._disk_available:
            return
        
        await self._async_write_manager.queue_api_log_write(strategy_name, api_calls)
    
    def create_strategy(self, name: str, owner: str, long_symbol: Optional[str] = None, 
                       short_symbol: Optional[str] = None, cash_balance: float = 0.0) -> Strategy:
        """
        Create a new strategy with immediate disk persistence
        
        Args:
            name: URL-safe strategy name
            owner: Username who owns this strategy
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
            
            # Create strategy object
            strategy = Strategy(name, owner, long_symbol, short_symbol, cash_balance)
            
            # Add to memory
            self.strategies[normalized_name] = strategy
            
            # Save to disk immediately (blocking for data integrity)
            self._save_strategies_to_disk()
            
            # Create empty API log file
            if self._disk_available:
                try:
                    api_log_file = f'/app/data/api_logs/{normalized_name}.json'
                    _atomic_write_json([], api_log_file)
                except Exception as e:
                    logger.error(f"🔥 ERROR: failed to create API log file for {name}: {str(e)}")
            
            logger.info(f"🔥 STRATEGY CREATED: name={strategy.name} owner={strategy.owner} display_name={getattr(strategy, 'display_name', strategy.name)} "
                       f"long={strategy.long_symbol} short={strategy.short_symbol} cash={strategy.cash_balance}")
            
            return strategy
    
    def get_strategy(self, name: str) -> Optional[Strategy]:
        """
        Get a strategy by name (from memory)
        
        Args:
            name: Strategy name (case insensitive)
            
        Returns:
            Strategy instance or None if not found
        """
        normalized_name = name.lower()
        
        with self._storage_lock:
            strategy = self.strategies.get(normalized_name)
            if strategy and not hasattr(strategy, 'display_name'):
                strategy.display_name = strategy.name
                logger.debug(f"🔥 STRATEGY MIGRATION: added display_name to {strategy.name}")
            return strategy
    
    def get_strategy_by_owner_and_name(self, owner: str, name: str) -> Optional[Strategy]:
        """
        Get a specific strategy by owner and name (for user-specific webhooks)
        
        Args:
            owner: Username who owns the strategy
            name: Strategy name (case insensitive)
            
        Returns:
            Strategy instance or None if not found
        """
        normalized_owner = owner.lower()
        normalized_name = name.lower()
        
        with self._storage_lock:
            strategy = self.strategies.get(normalized_name)
            if strategy and strategy.owner == normalized_owner:
                if not hasattr(strategy, 'display_name'):
                    strategy.display_name = strategy.name
                    logger.debug(f"🔥 STRATEGY MIGRATION: added display_name to {strategy.name}")
                return strategy
            return None
    
    def get_strategies_by_name(self, name: str) -> List[Strategy]:
        """
        Get all strategies with the same name across all users (for broadcast webhooks)
        
        Args:
            name: Strategy name to search for (case insensitive)
            
        Returns:
            List of Strategy instances with that name
        """
        normalized_name = name.lower()
        
        with self._storage_lock:
            matching_strategies = []
            for strategy_key, strategy in self.strategies.items():
                if strategy.name == normalized_name:
                    if not hasattr(strategy, 'display_name'):
                        strategy.display_name = strategy.name
                        logger.debug(f"🔥 STRATEGY MIGRATION: added display_name to {strategy.name}")
                    matching_strategies.append(strategy)
            
            # Sort by owner for consistent ordering
            matching_strategies.sort(key=lambda s: s.owner)
            return matching_strategies
    
    def get_all_strategies(self) -> List[Strategy]:
        """
        Get all strategies ordered by creation date (from memory)
        
        Returns:
            List of all Strategy instances ordered by creation_at
        """
        with self._storage_lock:
            strategies = list(self.strategies.values())
            # Sort by creation date as per PRD
            strategies.sort(key=lambda s: s.created_at)
            return strategies
    
    def get_strategies_by_owner(self, owner: str) -> List[Strategy]:
        """
        Get all strategies for a specific owner ordered by creation date
        
        Args:
            owner: Username to filter by
            
        Returns:
            List of Strategy instances for that owner ordered by creation_at
        """
        normalized_owner = owner.lower()
        
        with self._storage_lock:
            strategies = [s for s in self.strategies.values() if s.owner == normalized_owner]
            # Sort by creation date
            strategies.sort(key=lambda s: s.created_at)
            return strategies
    
    def get_all_owners(self) -> List[str]:
        """
        Get list of all unique strategy owners
        
        Returns:
            List of unique owner usernames
        """
        with self._storage_lock:
            owners = set(s.owner for s in self.strategies.values())
            return sorted(list(owners))
    
    def update_strategy(self, name: str, long_symbol: Optional[str] = None,
                       short_symbol: Optional[str] = None, cash_balance: Optional[float] = None) -> Optional[Strategy]:
        """
        Update an existing strategy with immediate disk persistence
        
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
                # Save to disk immediately (blocking for data integrity)
                self._save_strategies_to_disk()
                logger.info(f"🔥 STRATEGY UPDATED: name={strategy.name} owner={strategy.owner} changes={', '.join(updates)}")
            
            return strategy
    
    def update_strategy_symbols_both(self, name: str, long_symbol: Optional[str], short_symbol: Optional[str]) -> Optional[Strategy]:
        """
        Update both symbols for a strategy (used by update-symbols endpoint)
        Always updates both symbols regardless of None values
        
        Args:
            name: Strategy name
            long_symbol: New long symbol (can be None to clear)
            short_symbol: New short symbol (can be None to clear)
            
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
            
            # Always update both symbols directly (bypass conditional logic)
            old_long = strategy.long_symbol
            old_short = strategy.short_symbol
            
            # Set symbols directly to force update (even to None)
            strategy.long_symbol = long_symbol
            strategy.short_symbol = short_symbol
            strategy.updated_at = datetime.now()
            
            updates.append(f"long_symbol: {old_long} -> {strategy.long_symbol}")
            updates.append(f"short_symbol: {old_short} -> {strategy.short_symbol}")
            
            # Save to disk immediately (blocking for data integrity)
            self._save_strategies_to_disk()
            logger.info(f"🔥 STRATEGY UPDATED: name={strategy.name} owner={strategy.owner} changes={', '.join(updates)}")
            
            return strategy
    
    def delete_strategy(self, name: str) -> bool:
        """
        Delete a strategy with immediate disk persistence
        
        Args:
            name: Strategy name
            
        Returns:
            True if strategy was deleted, False if not found
        """
        normalized_name = name.lower()
        
        with self._storage_lock:
            if normalized_name in self.strategies:
                strategy = self.strategies.pop(normalized_name)
                
                # Save to disk immediately (blocking for data integrity)
                self._save_strategies_to_disk()
                
                # Delete API log file
                if self._disk_available:
                    try:
                        api_log_file = f'/app/data/api_logs/{normalized_name}.json'
                        if os.path.exists(api_log_file):
                            os.remove(api_log_file)
                    except Exception as e:
                        logger.error(f"🔥 ERROR: failed to delete API log file for {name}: {str(e)}")
                
                logger.info(f"🔥 STRATEGY DELETED: name={strategy.name} owner={strategy.owner} display_name={getattr(strategy, 'display_name', strategy.name)}")
                return True
            return False
    
    def strategy_exists(self, name: str) -> bool:
        """
        Check if a strategy exists (from memory)
        
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
        Get list of all strategy names (from memory)
        
        Returns:
            List of strategy names (lowercase)
        """
        with self._storage_lock:
            return list(self.strategies.keys())
    
    async def add_api_call_async(self, strategy: Strategy, request: dict, response: dict, timestamp: Optional[datetime] = None):
        """
        Add API call to strategy's history with async disk write
        
        Args:
            strategy: Strategy instance
            request: API request data
            response: API response data
            timestamp: Optional timestamp (defaults to now)
        """
        if timestamp is None:
            timestamp = datetime.now()
        
        # Add to memory immediately
        api_call_entry = {
            "request": request,
            "response": response,
            "timestamp": timestamp.isoformat()
        }
        
        strategy.api_calls.append(api_call_entry)
        
        # Keep only the last 100 API calls per strategy
        if len(strategy.api_calls) > 100:
            strategy.api_calls.pop(0)
        
        # Queue background write (non-blocking)
        await self._save_api_logs_async(strategy.name, strategy.api_calls)
    
    def add_api_call_sync(self, strategy: Strategy, request: dict, response: dict, timestamp: Optional[datetime] = None):
        """
        Synchronous wrapper for add_api_call_async for backwards compatibility
        
        Args:
            strategy: Strategy instance
            request: API request data
            response: API response data
            timestamp: Optional timestamp (defaults to now)
        """
        if timestamp is None:
            timestamp = datetime.now()
        
        # Add to memory immediately
        api_call_entry = {
            "request": request,
            "response": response,
            "timestamp": timestamp.isoformat()
        }
        
        strategy.api_calls.append(api_call_entry)
        
        # Keep only the last 100 API calls per strategy
        if len(strategy.api_calls) > 100:
            strategy.api_calls.pop(0)
        
        # For sync calls, we'll start a task if event loop is available
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Create task for background write
                loop.create_task(self._save_api_logs_async(strategy.name, strategy.api_calls))
            else:
                # No event loop running, skip async write
                logger.debug("🔥 PERSISTENCE: no event loop available for async API log write")
        except RuntimeError:
            # No event loop available, skip async write
            logger.debug("🔥 PERSISTENCE: no event loop available for async API log write")
    
    async def shutdown(self):
        """Gracefully shutdown the repository and background workers"""
        logger.info("🔥 PERSISTENCE: shutting down repository")
        await self._async_write_manager.stop()
