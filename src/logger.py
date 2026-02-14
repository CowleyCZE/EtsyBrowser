"""Logger module for Etsy Browser Bulk Uploader."""

import logging
import os
from datetime import datetime
from pathlib import Path


def setup_logger(name: str = "etsy_uploader", log_dir: str = "logs") -> logging.Logger:
    """Set up logger with file and console handlers.
    
    Args:
        name: Logger name
        log_dir: Directory for log files
        
    Returns:
        Configured logger instance
    """
    # Create logs directory if it doesn't exist
    log_path = Path(log_dir)
    log_path.mkdir(exist_ok=True)
    
    # Create logger
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    
    # Avoid duplicate handlers
    if logger.handlers:
        return logger
    
    # File handler - detailed logs
    log_file = log_path / f"etsy_uploader_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_format = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    file_handler.setFormatter(file_format)
    
    # Console handler - info level
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_format = logging.Formatter('%(levelname)s: %(message)s')
    console_handler.setFormatter(console_format)
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger


def log_error_screenshot(driver, error_name: str, log_dir: str = "logs") -> str:
    """Save error screenshot.
    
    Args:
        driver: Selenium WebDriver instance
        error_name: Name for the error/screenshot
        log_dir: Directory for screenshots
        
    Returns:
        Path to saved screenshot
    """
    log_path = Path(log_dir)
    log_path.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    screenshot_name = f"error_{error_name}_{timestamp}.png"
    screenshot_path = log_path / screenshot_name
    
    try:
        driver.save_screenshot(str(screenshot_path))
        return str(screenshot_path)
    except Exception as e:
        logging.error(f"Failed to save screenshot: {e}")
        return ""
