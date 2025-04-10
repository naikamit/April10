# error_handler.py
import logging
import traceback
from typing import Dict, Any, Callable, Awaitable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)

class ErrorHandler:
    """
    Centralized error handling for the application.
    Configures exception handlers for FastAPI.
    """
    
    @staticmethod
    def configure(app: FastAPI) -> None:
        """
        Configure exception handlers for the FastAPI application.
        
        Args:
            app (FastAPI): The FastAPI application
        """
        @app.exception_handler(StarletteHTTPException)
        async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
            """Handle HTTP exceptions."""
            return ErrorHandler._handle_http_exception(request, exc)
        
        @app.exception_handler(RequestValidationError)
        async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
            """Handle request validation errors."""
            return ErrorHandler._handle_validation_exception(request, exc)
        
        @app.exception_handler(Exception)
        async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
            """Handle all other exceptions."""
            return ErrorHandler._handle_general_exception(request, exc)
        
        logger.info("Error handlers configured")
    
    @staticmethod
    def _handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        """
        Handle HTTP exceptions.
        
        Args:
            request (Request): The request that caused the exception
            exc (StarletteHTTPException): The exception
            
        Returns:
            JSONResponse: JSON response with error details
        """
        logger.warning(f"HTTP exception: {exc.status_code} - {exc.detail}")
        
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "status": "error",
                "code": exc.status_code,
                "message": exc.detail
            }
        )
    
    @staticmethod
    def _handle_validation_exception(request: Request, exc: RequestValidationError) -> JSONResponse:
        """
        Handle request validation errors.
        
        Args:
            request (Request): The request that caused the exception
            exc (RequestValidationError): The exception
            
        Returns:
            JSONResponse: JSON response with error details
        """
        # Extract error details from the validation error
        error_details = []
        for error in exc.errors():
            error_details.append({
                "location": error["loc"],
                "message": error["msg"],
                "type": error["type"]
            })
        
        logger.warning(f"Validation error: {error_details}")
        
        return JSONResponse(
            status_code=422,
            content={
                "status": "error",
                "code": 422,
                "message": "Request validation failed",
                "details": error_details
            }
        )
    
    @staticmethod
    def _handle_general_exception(request: Request, exc: Exception) -> JSONResponse:
        """
        Handle all other exceptions.
        
        Args:
            request (Request): The request that caused the exception
            exc (Exception): The exception
            
        Returns:
            JSONResponse: JSON response with error details
        """
        # Log the full exception with traceback
        logger.error(f"Unhandled exception: {str(exc)}")
        logger.error(traceback.format_exc())
        
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "code": 500,
                "message": "An internal server error occurred"
            }
        )
    
    @staticmethod
    def try_execute(func: Callable) -> Any:
        """
        Execute a function with exception handling.
        For non-async functions.
        
        Args:
            func (Callable): The function to execute
            
        Returns:
            Any: The result of the function or None on exception
        """
        try:
            return func()
        except Exception as e:
            logger.error(f"Exception in function execution: {str(e)}")
            logger.error(traceback.format_exc())
            return None
    
    @staticmethod
    async def try_execute_async(func: Callable[..., Awaitable[Any]], *args, **kwargs) -> Any:
        """
        Execute an async function with exception handling.
        
        Args:
            func (Callable): The async function to execute
            *args: Positional arguments for the function
            **kwargs: Keyword arguments for the function
            
        Returns:
            Any: The result of the function or None on exception
        """
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Exception in async function execution: {str(e)}")
            logger.error(traceback.format_exc())
            return None
