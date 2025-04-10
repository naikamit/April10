# config.py - Configuration and environment variables
import os
from dotenv import load_dotenv

# Load environment variables from .env file (for local development)
load_dotenv()

# Signal Stack API configuration
SIGNAL_STACK_WEBHOOK_URL = os.getenv("SIGNAL_STACK_WEBHOOK_URL", "https://app.signalstack.com/hook/eL6vejLLAiy1cDd888gevK")
API_TIMEOUT = int(os.getenv("API_TIMEOUT", "180"))  # 3 minutes in seconds
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "5"))
RETRY_DELAY = int(os.getenv("RETRY_DELAY", "5"))  # seconds

# Trading symbols
LONG_SYMBOL = os.getenv("LONG_SYMBOL", "MSTU")
SHORT_SYMBOL = os.getenv("SHORT_SYMBOL", "MSTZ")

# Trading parameters
MINIMUM_CASH_BALANCE = float(os.getenv("MINIMUM_CASH_BALANCE", "50"))
BUY_RETRY_REDUCTION_PERCENT = float(os.getenv("BUY_RETRY_REDUCTION_PERCENT", "2"))
MAX_BUY_RETRIES = int(os.getenv("MAX_BUY_RETRIES", "3"))
COOLDOWN_PERIOD_HOURS = int(os.getenv("COOLDOWN_PERIOD_HOURS", "12"))

# Dashboard settings
DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", "8000"))
