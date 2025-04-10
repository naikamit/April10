# logging_config.py
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from typing import Dict, Any

from config import Config

def setup_logging() -> None:
    """
    Configure application logging with both console and file handlers.
    Implements log rotation to prevent excessive log file sizes.
    """
    config = Config()
    log_level_str = config.get("LOG_LEVEL", "INFO")
    
    # Convert string log level to logging constant
    log_level = getattr(logging, log_level_str.upper(), logging.INFO)
    
    # Create logs directory if it doesn't exist
    logs_dir = "logs"
    if not os.path.exists(logs_dir):
        os.makedirs(logs_dir)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Clear any existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Create formatters
    verbose_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
    )
    
    console_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # Console handler (INFO and above)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)
    
    # File handler with rotation (all levels)
    # Keep 5 files of 10MB each
    file_handler = RotatingFileHandler(
        f"{logs_dir}/webhook_service.log", 
        maxBytes=10*1024*1024,  # 10 MB
        backupCount=5
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(verbose_formatter)
    root_logger.addHandler(file_handler)
    
    # Error file handler (ERROR and above)
    error_file_handler = RotatingFileHandler(
        f"{logs_dir}/error.log", 
        maxBytes=10*1024*1024,  # 10 MB
        backupCount=5
    )
    error_file_handler.setLevel(logging.ERROR)
    error_file_handler.setFormatter(verbose_formatter)
    root_logger.addHandler(error_file_handler)
    
    # Set httpx and uvicorn loggers to WARNING to reduce noise
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    
    logging.info(f"Logging initialized with level: {log_level_str}")

def get_log_context(additional_context: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Create a context dictionary for structured logging.
    
    Args:
        additional_context (Dict[str, Any], optional): Additional context to include
        
    Returns:
        Dict[str, Any]: Complete context dictionary
    """
    context = {
        "service": "webhook_service",
    }
    
    if additional_context:
        context.update(additional_context)
    
    return context
