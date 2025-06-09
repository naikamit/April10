# config.py - Configuration and environment variables
import os
from dotenv import load_dotenv

# Load environment variables from .env file (for local development)
load_dotenv()

# Signal Stack API configuration
SIGNAL_STACK_WEBHOOK_URL = os.getenv("SIGNAL_STACK_WEBHOOK_URL", "")
API_TIMEOUT = int(os.getenv("API_TIMEOUT", "180"))  # 3 minutes in seconds
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "0"))
RETRY_DELAY = float(os.getenv("RETRY_DELAY", "1"))  # seconds - changed to float to support decimal values

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
