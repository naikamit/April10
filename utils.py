# utils.py
import asyncio
import functools
import inspect
import logging
import time
from typing import Any, Callable, TypeVar, cast, Optional

logger = logging.getLogger(__name__)

T = TypeVar('T')

def async_retry(
    max_retries: int = 3,
    retry_delay: float = 1.0,
    backoff_factor: float = 2.0,
    exception_types: tuple = (Exception,)
) -> Callable:
    """
    Decorator for async functions to implement retry logic with exponential backoff.
    
    Args:
        max_retries (int): Maximum number of retry attempts
        retry_delay (float): Initial delay between retries in seconds
        backoff_factor (float): Factor by which the delay increases with each retry
        exception_types (tuple): Exception types that trigger a retry
        
    Returns:
        Callable: Decorated function
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception = None
            current_delay = retry_delay
            
            for attempt in range(max_retries + 1):
                try:
                    if attempt > 0:
                        logger.info(f"Retry attempt {attempt}/{max_retries} for {func.__name__}")
                    
                    return await func(*args, **kwargs)
                
                except exception_types as e:
                    last_exception = e
                    
                    if attempt == max_retries:
                        logger.error(f"Function {func.__name__} failed after {max_retries} retries: {str(e)}")
                        raise
                    
                    logger.warning(f"Function {func.__name__} failed on attempt {attempt + 1}/{max_retries + 1}: {str(e)}")
                    logger.warning(f"Retrying in {current_delay:.2f} seconds...")
                    
                    await asyncio.sleep(current_delay)
                    current_delay *= backoff_factor
            
            # This should never be reached, but just in case
            assert last_exception is not None
            raise last_exception
        
        return wrapper
    
    return decorator

def timed_execution(func: Callable[..., T]) -> Callable[..., T]:
    """
    Decorator to measure and log the execution time of a function.
    Works with both sync and async functions.
    
    Args:
        func (Callable): The function to be timed
        
    Returns:
        Callable: Decorated function
    """
    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        start_time = time.time()
        result = func(*args, **kwargs)
        execution_time = time.time() - start_time
        logger.info(f"Function {func.__name__} executed in {execution_time:.4f} seconds")
        return result
    
    @functools.wraps(func)
    async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
        start_time = time.time()
        result = await func(*args, **kwargs)
        execution_time = time.time() - start_time
        logger.info(f"Async function {func.__name__} executed in {execution_time:.4f} seconds")
        return result
    
    if inspect.iscoroutinefunction(func):
        return cast(Callable[..., T], async_wrapper)
    return cast(Callable[..., T], wrapper)

def validate_payload(payload: Any, required_fields: list) -> Optional[str]:
    """
    Validate a payload has all required fields and they're not empty.
    
    Args:
        payload (Any): The payload to validate
        required_fields (list): List of required field names
        
    Returns:
        Optional[str]: Error message if validation fails, None if successful
    """
    if not isinstance(payload, dict):
        return "Payload must be a JSON object"
    
    for field in required_fields:
        if field not in payload:
            return f"Missing required field: {field}"
        
        if payload[field] is None or (isinstance(payload[field], str) and not payload[field].strip()):
            return f"Field cannot be empty: {field}"
    
    return None

def calculate_max_shares(cash_balance: float, price: float, safety_margin: float = 0.98) -> int:
    """
    Calculate the maximum number of whole shares that can be purchased.
    
    Args:
        cash_balance (float): Available cash balance
        price (float): Current price per share
        safety_margin (float): Safety margin to account for price fluctuations
        
    Returns:
        int: Maximum number of whole shares
    """
    if price <= 0:
        return 0
    
    max_shares = int(cash_balance * safety_margin / price)
    return max(0, max_shares)
