# strategy_repository.py - Strategy CRUD operations with JSON file persistence - With environment-based user validation
import threading
import logging
import json
import os
import asyncio
from datetime import datetime
from typing import Dict, List, Optional
from strategy import Strategy
from config import get_valid_users, is_valid_user, get_all_webhook_urls

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
    
    async def queue_api_log_write(self, file_path: str, api_calls: List[dict]):
        """Queue an API log write (non-blocking)"""
        if not self.running:
            await self.start()
        
        try:
            await self.write_queue.put(('api_log', file_path, api_calls.copy()))
        except Exception as e:
            logger.error(f"🔥 ERROR: failed to queue API log write for {file_path}: {str(e)}")
    
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
                
                write_type, file_path, data = write_task
                
                if write_type == 'api_log':
                    try:
                        _atomic_write_json(data, file_path)
                        logger.debug(f"🔥 PERSISTENCE: API logs written to {file_path}")
                    except Exception as e:
                        logger.error(f"🔥 ERROR: background API log write failed for {file_path}: {str(e)}")
                
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
        self.strategies = {}  # Dict of {user_id: {strategy_name: Strategy}}
        self._storage_lock = threading.Lock()
        self._async_write_manager = AsyncWriteManager()
        self._disk_available = False
        
        # Get valid users from environment variables
        self.valid_users = get_valid_users()
        logger.info(f"🔥 USER MANAGEMENT: found {len(self.valid_users)} users in environment variables")
        
        # Check if disk is available and load data
        self._disk_available = _ensure_data_directory()
        
        if self._disk_available:
            self._load_strategies_from_disk()
            # Count total strategies across all users
            total_strategies = sum(len(strategies) for strategies in self.strategies.values())
            logger.info(f"🔥 PERSISTENCE: repository initialized with disk storage, loaded {total_strategies} strategies across {len(self.strategies)} users")
        else:
            logger.warning("🔥 PERSISTENCE: disk not available, using memory-only mode")
    
    def _load_strategies_from_disk(self):
        """Load all strategies and their API logs from disk"""
        strategies_file = '/app/data/strategies.json'
        
        # Load strategy configurations
        strategies_data = _load_json_file(strategies_file, {})
        
        for strategy_key, strategy_data in strategies_data.items():
            try:
                # Extract user_id or default to "default" for backward compatibility
                user_id = strategy_data.get('user_id', 'default').lower()
                
                # Skip strategies for users that don't exist in environment variables
                if user_id not in self.valid_users and user_id != 'default':
                    logger.warning(f"🔥 USER MANAGEMENT: skipping strategy {strategy_key} - user {user_id} not found in environment variables")
                    continue
                
                # Strategy name is either from the data or extracted from the key
                if 'name' in strategy_data:
                    strategy_name = strategy_data.get('name')
                else:
                    # For backward compatibility, if key doesn't have user_id, use key as name
                    if '_' in strategy_key:
                        parts = strategy_key.split('_', 1)
                        if len(parts) == 2:
                            user_id, strategy_name = parts
                        else:
                            strategy_name = strategy_key
                    else:
                        strategy_name = strategy_key
                
                # Create strategy object from saved data
                strategy = Strategy(
                    name=strategy_name,
                    user_id=user_id,
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
                api_log_file = f'/app/data/api_logs/{user_id}_{strategy_name}.json'
                api_calls = _load_json_file(api_log_file, [])
                strategy.api_calls = api_calls[-100:]  # Keep only last 100
                
                # Ensure user_id dictionary exists
                if user_id not in self.strategies:
                    self.strategies[user_id] = {}
                    
                self.strategies[user_id][strategy_name.lower()] = strategy
                logger.debug(f"🔥 PERSISTENCE: loaded user={user_id} strategy={strategy.name} with {len(strategy.api_calls)} API calls")
                
            except Exception as e:
                logger.error(f"🔥 ERROR: failed to load strategy {strategy_key}: {str(e)}")
                continue
    
    def _save_strategies_to_disk(self):
        """Save all strategy configurations to disk (synchronous)"""
        if not self._disk_available:
            logger.debug("🔥 PERSISTENCE: disk not available, skipping strategy save")
            return
        
        strategies_file = '/app/data/strategies.json'
        
        try:
            # Convert all strategies to JSON-serializable format
            strategies_data = {}
            
            for user_id, user_strategies in self.strategies.items():
                for strategy_name, strategy in user_strategies.items():
                    # Use a composite key with user_id and strategy_name
                    strategy_key = f"{user_id}_{strategy_name}"
                    
                    strategies_data[strategy_key] = {
                        'name': strategy.name,
                        'user_id': strategy.user_id,
                        'display_name': getattr(strategy, 'display_name', strategy.name),
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
    
    async def _save_api_logs_async(self, strategy: Strategy, api_calls: List[dict]):
        """Save API logs asynchronously (non-blocking)"""
        if not self._disk_available:
            return
        
        # Use user_id in the filename
        api_log_file = f'/app/data/api_logs/{strategy.user_id}_{strategy.name}.json'
        await self._async_write_manager.queue_api_log_write(api_log_file, api_calls)
    
    def refresh_valid_users(self):
        """
        Refresh the list of valid users from environment variables
        Call this if environment variables change during runtime
        """
        with self._storage_lock:
            self.valid_users = get_valid_users()
            logger.info(f"🔥 USER MANAGEMENT: refreshed users from environment variables - found {len(self.valid_users)} users")
            
            # Remove strategies for users that no longer exist
            users_to_remove = []
            for user_id in self.strategies.keys():
                if user_id not in self.valid_users and user_id != 'default':
                    users_to_remove.append(user_id)
            
            for user_id in users_to_remove:
                del self.strategies[user_id]
                logger.info(f"🔥 USER MANAGEMENT: removed user {user_id} and all strategies - user no longer exists in environment variables")
            
            # Save to disk
            self._save_strategies_to_disk()
    
    def get_strategy(self, name: str, user_id: str = "default") -> Optional[Strategy]:
        """
        Get a strategy by name and user_id (from memory)
        
        Args:
            name: Strategy name (case insensitive)
            user_id: User identifier (case insensitive)
            
        Returns:
            Strategy instance or None if not found
        """
        normalized_name = name.lower()
        normalized_user_id = user_id.lower()
        
        # If user doesn't exist in environment variables and not default, return None
        if normalized_user_id != 'default' and normalized_user_id not in self.valid_users:
            return None
        
        with self._storage_lock:
            user_strategies = self.strategies.get(normalized_user_id, {})
            strategy = user_strategies.get(normalized_name)
            if strategy and not hasattr(strategy, 'display_name'):
                strategy.display_name = strategy.name
                logger.debug(f"🔥 STRATEGY MIGRATION: added display_name to {strategy.name}")
            return strategy
    
    def get_all_strategies(self) -> List[Strategy]:
        """
        Get all strategies across all users ordered by creation date (from memory)
        Only includes strategies for valid users (from env vars) and default user
        
        Returns:
            List of all Strategy instances ordered by creation_at
        """
        with self._storage_lock:
            all_strategies = []
            for user_id, user_strategies in self.strategies.items():
                # Only include valid users and default user
                if user_id in self.valid_users or user_id == 'default':
                    all_strategies.extend(user_strategies.values())
            # Sort by creation date
            all_strategies.sort(key=lambda s: s.created_at)
            return all_strategies
    
    def get_user_strategies(self, user_id: str) -> List[Strategy]:
        """
        Get all strategies for a specific user ordered by creation date
        
        Args:
            user_id: User identifier
            
        Returns:
            List of Strategy instances for this user ordered by creation_at
        """
        normalized_user_id = user_id.lower()
        
        # If user doesn't exist in environment variables and not default, return empty list
        if normalized_user_id != 'default' and normalized_user_id not in self.valid_users:
            return []
        
        with self._storage_lock:
            user_strategies = list(self.strategies.get(normalized_user_id, {}).values())
            user_strategies.sort(key=lambda s: s.created_at)
            return user_strategies
    
    def get_all_users(self) -> List[str]:
        """
        Get list of all valid users from environment variables plus default
        
        Returns:
            List of user IDs
        """
        users = self.valid_users.copy()
        if 'default' not in users:
            users.append('default')
        return users
    
    def get_active_users(self) -> List[str]:
        """
        Get list of users who have strategies
        
        Returns:
            List of user IDs who have at least one strategy
        """
        with self._storage_lock:
            return [user_id for user_id in self.strategies.keys() 
                   if self.strategies[user_id] and (user_id in self.valid_users or user_id == 'default')]
    
    def get_users_with_strategy(self, strategy_name: str) -> List[str]:
        """
        Get list of valid users who have a specific strategy
        
        Args:
            strategy_name: Strategy name to look for
            
        Returns:
            List of user IDs who have this strategy
        """
        normalized_name = strategy_name.lower()
        
        with self._storage_lock:
            users_with_strategy = []
            for user_id, user_strategies in self.strategies.items():
                # Only include valid users
                if (user_id in self.valid_users or user_id == 'default') and normalized_name in user_strategies:
                    users_with_strategy.append(user_id)
            return users_with_strategy
    
    def create_strategy(self, name: str, user_id: str = "default", long_symbol: Optional[str] = None, 
                      short_symbol: Optional[str] = None, cash_balance: float = 0.0) -> Strategy:
        """
        Create a new strategy with immediate disk persistence
        
        Args:
            name: URL-safe strategy name
            user_id: User identifier
            long_symbol: Symbol for long signals (optional)
            short_symbol: Symbol for short signals (optional)
            cash_balance: Initial cash balance
            
        Returns:
            Created Strategy instance
            
        Raises:
            ValueError: If strategy name is invalid, user doesn't exist, or strategy exists
        """
        normalized_name = name.lower()
        normalized_user_id = user_id.lower()
        
        # Validate user exists in environment variables (unless it's default)
        if normalized_user_id != 'default' and normalized_user_id not in self.valid_users:
            raise ValueError(f"User '{user_id}' does not exist. Users can only be created via environment variables.")
        
        with self._storage_lock:
            # Ensure user_id dictionary exists
            if normalized_user_id not in self.strategies:
                self.strategies[normalized_user_id] = {}
                
            if normalized_name in self.strategies[normalized_user_id]:
                raise ValueError(f"Strategy '{name}' already exists for user '{user_id}'")
            
            # Create strategy object
            strategy = Strategy(name, normalized_user_id, long_symbol, short_symbol, cash_balance)
            
            # Add to memory
            self.strategies[normalized_user_id][normalized_name] = strategy
            
            # Save to disk immediately (blocking for data integrity)
            self._save_strategies_to_disk()
            
            # Create empty API log file
            if self._disk_available:
                try:
                    api_log_file = f'/app/data/api_logs/{normalized_user_id}_{normalized_name}.json'
                    _atomic_write_json([], api_log_file)
                except Exception as e:
                    logger.error(f"🔥 ERROR: failed to create API log file for user={user_id} strategy={name}: {str(e)}")
            
            logger.info(f"🔥 STRATEGY CREATED: user={strategy.user_id} name={strategy.name} display_name={getattr(strategy, 'display_name', strategy.name)} "
                       f"long={strategy.long_symbol} short={strategy.short_symbol} cash={strategy.cash_balance}")
            
            return strategy
    
    def update_strategy(self, name: str, user_id: str = "default", long_symbol: Optional[str] = None,
                       short_symbol: Optional[str] = None, cash_balance: Optional[float] = None) -> Optional[Strategy]:
        """
        Update an existing strategy with immediate disk persistence
        
        Args:
            name: Strategy name
            user_id: User identifier
            long_symbol: New long symbol (if provided)
            short_symbol: New short symbol (if provided)
            cash_balance: New cash balance (if provided)
            
        Returns:
            Updated Strategy instance or None if not found
        """
        normalized_name = name.lower()
        normalized_user_id = user_id.lower()
        
        # Validate user exists in environment variables (unless it's default)
        if normalized_user_id != 'default' and normalized_user_id not in self.valid_users:
            return None
        
        with self._storage_lock:
            # Ensure user_id dictionary exists
            if normalized_user_id not in self.strategies:
                return None
                
            strategy = self.strategies[normalized_user_id].get(normalized_name)
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
                logger.info(f"🔥 STRATEGY UPDATED: user={strategy.user_id} name={strategy.name} changes={', '.join(updates)}")
            
            return strategy
    
    def update_strategy_symbols_both(self, name: str, user_id: str = "default", 
                                    long_symbol: Optional[str] = None, 
                                    short_symbol: Optional[str] = None) -> Optional[Strategy]:
        """
        Update both symbols for a strategy (used by update-symbols endpoint)
        Always updates both symbols regardless of None values
        
        Args:
            name: Strategy name
            user_id: User identifier
            long_symbol: New long symbol (can be None to clear)
            short_symbol: New short symbol (can be None to clear)
            
        Returns:
            Updated Strategy instance or None if not found
        """
        normalized_name = name.lower()
        normalized_user_id = user_id.lower()
        
        # Validate user exists in environment variables (unless it's default)
        if normalized_user_id != 'default' and normalized_user_id not in self.valid_users:
            return None
        
        with self._storage_lock:
            # Ensure user_id dictionary exists
            if normalized_user_id not in self.strategies:
                return None
            
            strategy = self.strategies[normalized_user_id].get(normalized_name)
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
            logger.info(f"🔥 STRATEGY UPDATED: user={strategy.user_id} name={strategy.name} changes={', '.join(updates)}")
            
            return strategy
    
    def delete_strategy(self, name: str, user_id: str = "default") -> bool:
        """
        Delete a strategy with immediate disk persistence
        
        Args:
            name: Strategy name
            user_id: User identifier
            
        Returns:
            True if strategy was deleted, False if not found
        """
        normalized_name = name.lower()
        normalized_user_id = user_id.lower()
        
        # Validate user exists in environment variables (unless it's default)
        if normalized_user_id != 'default' and normalized_user_id not in self.valid_users:
            return False
        
        with self._storage_lock:
            # Ensure user_id dictionary exists
            if normalized_user_id not in self.strategies:
                return False
            
            if normalized_name in self.strategies[normalized_user_id]:
                strategy = self.strategies[normalized_user_id].pop(normalized_name)
                
                # If user has no strategies left, remove the user
                if not self.strategies[normalized_user_id]:
                    self.strategies.pop(normalized_user_id)
                
                # Save to disk immediately (blocking for data integrity)
                self._save_strategies_to_disk()
                
                # Delete API log file
                if self._disk_available:
                    try:
                        api_log_file = f'/app/data/api_logs/{normalized_user_id}_{normalized_name}.json'
                        if os.path.exists(api_log_file):
                            os.remove(api_log_file)
                    except Exception as e:
                        logger.error(f"🔥 ERROR: failed to delete API log file for user={user_id} strategy={name}: {str(e)}")
                
                logger.info(f"🔥 STRATEGY DELETED: user={strategy.user_id} name={strategy.name} display_name={getattr(strategy, 'display_name', strategy.name)}")
                return True
            return False
    
    def get_strategy_names(self, user_id: str = "default") -> List[str]:
        """
        Get list of all strategy names for a user (from memory)
        
        Args:
            user_id: User identifier
            
        Returns:
            List of strategy names (lowercase)
        """
        normalized_user_id = user_id.lower()
        
        # Validate user exists in environment variables (unless it's default)
        if normalized_user_id != 'default' and normalized_user_id not in self.valid_users:
            return []
            
        with self._storage_lock:
            if normalized_user_id in self.strategies:
                return list(self.strategies[normalized_user_id].keys())
            return []
    
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
        await self._save_api_logs_async(strategy, strategy.api_calls)
    
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
                loop.create_task(self._save_api_logs_async(strategy, strategy.api_calls))
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
