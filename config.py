# config.py - Configuration and environment variables with user management
import os
from dotenv import load_dotenv
from typing import Dict, List

# Load environment variables from .env file (for local development)
load_dotenv()

# Environment-based user management
def get_users_from_environment() -> Dict[str, str]:
    """
    Get all users and their webhook URLs from environment variables.
    Looks for variables like SIGNAL_STACK_WEBHOOK_URL_AMIT, SIGNAL_STACK_WEBHOOK_URL_JOHN, etc.
    
    Returns:
        Dictionary mapping username -> webhook_url
    """
    users = {}
    prefix = "SIGNAL_STACK_WEBHOOK_URL_"
    
    for key, value in os.environ.items():
        if key.startswith(prefix) and len(key) > len(prefix):
            # Extract username from environment variable name
            username = key[len(prefix):].lower()
            if value and value.strip():  # Only include if URL is not empty
                users[username] = value.strip()
    
    return users

def get_webhook_url_for_user(username: str) -> str:
    """
    Get the SignalStack webhook URL for a specific user
    
    Args:
        username: Username to get webhook URL for
        
    Returns:
        Webhook URL for the user, or empty string if not found
    """
    env_var_name = f"SIGNAL_STACK_WEBHOOK_URL_{username.upper()}"
    return os.getenv(env_var_name, "")

def get_available_users() -> List[str]:
    """
    Get list of all available users (those with webhook URLs defined)
    
    Returns:
        List of usernames
    """
    return list(get_users_from_environment().keys())

def user_exists(username: str) -> bool:
    """
    Check if a user exists (has a webhook URL defined)
    
    Args:
        username: Username to check
        
    Returns:
        True if user exists, False otherwise
    """
    return username.lower() in get_users_from_environment()

# Legacy webhook URL (for backward compatibility)
SIGNAL_STACK_WEBHOOK_URL = os.getenv("SIGNAL_STACK_WEBHOOK_URL", "")

# API configuration
API_TIMEOUT = int(os.getenv("API_TIMEOUT", "180"))  # 3 minutes in seconds
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "0"))
RETRY_DELAY = float(os.getenv("RETRY_DELAY", "1"))  # seconds - changed to float to support decimal values

# Trading symbols (legacy - now per-strategy)
LONG_SYMBOL = os.getenv("LONG_SYMBOL", "")
SHORT_SYMBOL = os.getenv("SHORT_SYMBOL", "")

# Trading parameters
MINIMUM_CASH_BALANCE = float(os.getenv("MINIMUM_CASH_BALANCE", "5"))
BUY_RETRY_REDUCTION_PERCENT = float(os.getenv("BUY_RETRY_REDUCTION_PERCENT", "0.1"))
MAX_BUY_RETRIES = int(os.getenv("MAX_BUY_RETRIES", "20"))
COOLDOWN_PERIOD_HOURS = int(os.getenv("COOLDOWN_PERIOD_HOURS", "12"))

# Dashboard settings
DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", "8000"))
