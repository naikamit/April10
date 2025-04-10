# config.py
import os
from typing import Dict, Any, Optional

# Default configuration
DEFAULT_CONFIG = {
    "LONG_SYMBOL": "MSTU",
    "SHORT_SYMBOL": "MSTZ",
    "SIGNAL_STACK_API_URL": "https://app.signalstack.com/hook/eL6vejLLAiy1cDd888gevK",
    "COOLDOWN_PERIOD_HOURS": 12,
    "RETRY_MAX_ATTEMPTS": 5,
    "RETRY_BACKOFF_FACTOR": 2,
    "BUY_RETRY_PERCENTAGE_REDUCTION": 2,
    "MAX_BUY_RETRIES": 5,
    "HOST": "0.0.0.0",
    "PORT": 8000,
    "INITIAL_CASH_BALANCE": 10000.0,
    "LOG_LEVEL": "INFO",
}

class Config:
    """Configuration manager for the webhook service."""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Config, cls).__new__(cls)
            cls._instance._load_config()
        return cls._instance
    
    def _load_config(self) -> None:
        """Load configuration from environment variables with defaults."""
        self._config = {}
        
        for key, default_value in DEFAULT_CONFIG.items():
            env_value = os.environ.get(key)
            
            if env_value is not None:
                # Convert to appropriate type based on default value
                if isinstance(default_value, bool):
                    self._config[key] = env_value.lower() in ('true', '1', 'yes')
                elif isinstance(default_value, int):
                    self._config[key] = int(env_value)
                elif isinstance(default_value, float):
                    self._config[key] = float(env_value)
                else:
                    self._config[key] = env_value
            else:
                self._config[key] = default_value
    
    def get(self, key: str, default: Optional[Any] = None) -> Any:
        """Get a configuration value."""
        return self._config.get(key, default)
    
    def get_all(self) -> Dict[str, Any]:
        """Get all configuration values."""
        return self._config.copy()
