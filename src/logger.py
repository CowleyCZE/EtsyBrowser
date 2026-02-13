#!/usr/bin/env python3
"""
Logger Module for Etsy Uploader
Handles logging, screenshots, and error tracking.
"""

import os
import sys
import logging
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

import colorlog


class UploaderLogger:
    """Logger for Etsy uploader with file and console output."""
    
    def __init__(self, log_dir: str = "logs"):
        self.log_dir = log_dir
        self._setup_directories()
        self._setup_logger()
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.error_log_path = os.path.join(log_dir, f"errors_{self.session_id}.log")
        self.upload_log_path = os.path.join(log_dir, f"upload_{self.session_id}.log")
        
    def _setup_directories(self):
        """Create log directories if they don't exist."""
        Path(self.log_dir).mkdir(parents=True, exist_ok=True)
        
    def _setup_logger(self):
        """Set up the logger with colorized console output."""
        # Create logger
        self.logger = logging.getLogger('etsy_uploader')
        self.logger.setLevel(logging.DEBUG)
        
        # Clear existing handlers
        self.logger.handlers = []
        
        # Console handler with colors
        console_handler = colorlog.StreamHandler()
        console_handler.setLevel(logging.INFO)
        
        # Color scheme
        console_formatter = colorlog.ColoredFormatter(
            '%(log_color)s%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%H:%M:%S',
            log_colors={
                'DEBUG': 'cyan',
                'INFO': 'green',
                'WARNING': 'yellow',
                'ERROR': 'red',
                'CRITICAL': 'red,bg_white',
            }
        )
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)
        
        # File handler
        file_handler = logging.FileHandler(
            os.path.join(self.log_dir, f"uploader_{self.session_id}.log")
        )
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(file_formatter)
        self.logger.addHandler(file_handler)
    
    def debug(self, message: str):
        """Log debug message."""
        self.logger.debug(message)
        
    def info(self, message: str):
        """Log info message."""
        self.logger.info(message)
        
    def warning(self, message: str):
        """Log warning message."""
        self.logger.warning(message)
        
    def error(self, message: str):
        """Log error message."""
        self.logger.error(message)
        
    def critical(self, message: str):
        """Log critical message."""
        self.logger.critical(message)
    
    def save_screenshot(self, driver, prefix: str = "error") -> Optional[str]:
        """Save a screenshot of the current browser state."""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{prefix}_{timestamp}.png"
            filepath = os.path.join(self.log_dir, filename)
            
            driver.save_screenshot(filepath)
            self.logger.info(f"Screenshot saved: {filename}")
            return filepath
        except Exception as e:
            self.logger.error(f"Failed to save screenshot: {e}")
            return None
    
    def log_error(self, error_type: str, message: str, details: Dict[str, Any] = None):
        """Log an error to the error log file."""
        try:
            error_entry = {
                'timestamp': datetime.now().isoformat(),
                'type': error_type,
                'message': message,
                'details': details or {}
            }
            
            with open(self.error_log_path, 'a') as f:
                f.write(json.dumps(error_entry) + '\n')
                
        except Exception as e:
            self.logger.error(f"Failed to log error: {e}")
    
    def log_upload_result(self, product_title: str, success: bool, 
                          listing_id: str = None, error: str = None):
        """Log upload result to the upload log file."""
        try:
            result = {
                'timestamp': datetime.now().isoformat(),
                'product': product_title,
                'success': success,
                'listing_id': listing_id,
                'error': error
            }
            
            with open(self.upload_log_path, 'a') as f:
                f.write(json.dumps(result) + '\n')
                
        except Exception as e:
            self.logger.error(f"Failed to log upload result: {e}")
    
    def log_product_data(self, product: Dict[str, Any]):
        """Log product data for debugging."""
        try:
            product_entry = {
                'timestamp': datetime.now().isoformat(),
                'product': product
            }
            
            with open(os.path.join(self.log_dir, f"products_{self.session_id}.json"), 'a') as f:
                f.write(json.dumps(product_entry) + '\n')
                
        except Exception as e:
            self.logger.error(f"Failed to log product data: {e}")
    
    def get_session_summary(self) -> Dict[str, Any]:
        """Get summary of the current session."""
        try:
            # Count uploads
            success_count = 0
            failed_count = 0
            
            if os.path.exists(self.upload_log_path):
                with open(self.upload_log_path, 'r') as f:
                    for line in f:
                        try:
                            entry = json.loads(line)
                            if entry.get('success'):
                                success_count += 1
                            else:
                                failed_count += 1
                        except:
                            pass
            
            return {
                'session_id': self.session_id,
                'success_count': success_count,
                'failed_count': failed_count,
                'total_count': success_count + failed_count,
                'error_log': self.error_log_path,
                'upload_log': self.upload_log_path
            }
            
        except Exception as e:
            self.logger.error(f"Failed to get session summary: {e}")
            return {}


class ErrorTracker:
    """Track and analyze errors."""
    
    def __init__(self, log_dir: str = "logs"):
        self.log_dir = log_dir
        self.errors = []
        
    def add_error(self, error_type: str, message: str, context: Dict[str, Any] = None):
        """Add an error to the tracker."""
        error = {
            'timestamp': datetime.now().isoformat(),
            'type': error_type,
            'message': message,
            'context': context or {}
        }
        self.errors.append(error)
        
    def get_error_summary(self) -> Dict[str, int]:
        """Get summary of errors by type."""
        summary = {}
        for error in self.errors:
            error_type = error['type']
            summary[error_type] = summary.get(error_type, 0) + 1
        return summary
    
    def get_recent_errors(self, count: int = 10) -> list:
        """Get most recent errors."""
        return self.errors[-count:]
    
    def save_errors(self, filename: str = None):
        """Save errors to file."""
        if filename is None:
            filename = f"errors_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        filepath = os.path.join(self.log_dir, filename)
        
        try:
            with open(filepath, 'w') as f:
                json.dump(self.errors, f, indent=2)
            return filepath
        except Exception as e:
            print(f"Failed to save errors: {e}")
            return None


def setup_logging(log_level: str = "INFO") -> UploaderLogger:
    """Set up logging for the application."""
    logger = UploaderLogger()
    
    # Set level
    level = getattr(logging, log_level.upper(), logging.INFO)
    logger.logger.setLevel(level)
    
    return logger
