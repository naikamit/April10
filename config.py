# config.py - Configuration and environment variables - User management via environment variables
import os
import re
from typing import Dict, List
from dotenv import load_dotenv

# Load environment variables from .env file (for local development)
load_dotenv()

# Signal Stack API configuration
SIGNAL_STACK_WEBHOOK_URL = os.getenv("SIGNAL_STACK_WEBHOOK_URL", "")
API_TIMEOUT = int(os.getenv("API_TIMEOUT", "180"))  # 3 minutes in seconds
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "0"))
RETRY_DELAY = float(os.getenv("RETRY_DELAY", "1"))  # seconds - changed to float to support decimal values

# User management based on environment variables
def get_valid_users() -> List[str]:
    """
    Get list of valid users based on environment variables
    
    Returns:
        List of user IDs extracted from SIGNAL_STACK_WEBHOOK_URL_* env vars
    """
    valid_users = []
    webhook_pattern = re.compile(r'^SIGNAL_STACK_WEBHOOK_URL_(.+)$')
    
    for key in os.environ:
        match = webhook_pattern.match(key)
        if match and os.environ[key].strip():  # Only include non-empty URLs
            user_id = match.group(1).lower()  # Normalize to lowercase
            valid_users.append(user_id)
    
    return valid_users

def is_valid_user(user_id: str) -> bool:
    """
    Check if a user ID is valid based on environment variables
    
    Args:
        user_id: User ID to check
        
    Returns:
        True if valid user, False otherwise
    """
    user_id_upper = user_id.upper()
    webhook_url = os.getenv(f"SIGNAL_STACK_WEBHOOK_URL_{user_id_upper}", "")
    return bool(webhook_url.strip())

# User-specific webhook URLs helper function
def get_user_webhook_url(user_id: str) -> str:
    """
    Get the Signal Stack webhook URL for a specific user
    
    Args:
        user_id: User identifier
        
    Returns:
        URL string for the user's Signal Stack webhook or empty string if not found
    """
    # Normalize user_id for environment variable lookup
    user_id_upper = user_id.upper()
    
    # Get user-specific URL
    user_url = os.getenv(f"SIGNAL_STACK_WEBHOOK_URL_{user_id_upper}", "")
    
    # We don't fall back to default URL anymore - if no URL is configured for user, return empty
    return user_url.strip()

# Get all user webhook URLs
def get_all_webhook_urls() -> Dict[str, str]:
    """
    Get all configured webhook URLs for all users
    
    Returns:
        Dictionary mapping user IDs to their webhook URLs
    """
    webhook_urls = {}
    webhook_pattern = re.compile(r'^SIGNAL_STACK_WEBHOOK_URL_(.+)$')
    
    for key in os.environ:
        match = webhook_pattern.match(key)
        if match and os.environ[key].strip():  # Only include non-empty URLs
            user_id = match.group(1).lower()  # Normalize to lowercase
            webhook_urls[user_id] = os.environ[key].strip()
    
    return webhook_urls

# Trading symbols
LONG_SYMBOL = os.getenv("LONG_SYMBOL", "")
SHORT_SYMBOL = os.getenv("SHORT_SYMBOL", "")

# Trading parameters
MINIMUM_CASH_BALANCE = float(os.getenv("MINIMUM_CASH_BALANCE", "5"))
BUY_RETRY_REDUCTION_PERCENT = float(os.getenv("BUY_RETRY_REDUCTION_PERCENT", "0.1"))
MAX_BUY_RETRIES = int(os.getenv("MAX_BUY_RETRIES", "20"))
COOLDOWN_PERIOD_HOURS = int(os.getenv("COOLDOWN_PERIOD_HOURS", "12"))

# Dashboard settings
DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", "8000"))
