"""Browser utilities for Etsy Browser Bulk Uploader."""

import random
import time
from typing import Optional

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium_stealth import stealth

from src.logger import setup_logger

logger = setup_logger("browser_utils")


def create_driver(headless: bool = False) -> webdriver.Chrome:
    """Create Chrome WebDriver with stealth settings.
    
    Args:
        headless: Run browser in headless mode
        
    Returns:
        Configured Chrome WebDriver instance
    """
    options = Options()
    
    if headless:
        options.add_argument("--headless=new")
    
    # Essential options for stealth
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-gpu")
    
    # Window size
    options.add_argument("--window-size=1920,1080")
    
    # User agent
    user_agent = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
    options.add_argument(f"user-agent={user_agent}")
    
    # Create driver with webdriver-manager
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    
    # Apply selenium-stealth
    stealth(
        driver,
        languages=["en-US", "en"],
        vendor="Google Inc.",
        platform="Win32",
        webgl_vendor="Intel Inc.",
        renderer="Intel Iris OpenGL Engine",
        fix_hairline=True,
    )
    
    logger.info("Chrome driver created successfully")
    return driver


def random_delay(min_seconds: float = 2, max_seconds: float = 10) -> None:
    """Wait for random duration to mimic human behavior.
    
    Args:
        min_seconds: Minimum delay in seconds
        max_seconds: Maximum delay in seconds
    """
    delay = random.uniform(min_seconds, max_seconds)
    time.sleep(delay)


def human_like_scroll(driver, direction: str = "down", steps: int = 3) -> None:
    """Scroll in a human-like manner.
    
    Args:
        driver: Selenium WebDriver instance
        direction: "up" or "down"
        steps: Number of scroll steps
    """
    scroll_amount = random.randint(200, 500)
    
    for _ in range(steps):
        if direction == "down":
            driver.execute_script(f"window.scrollBy(0, {scroll_amount});")
        else:
            driver.execute_script(f"window.scrollBy(0, -{scroll_amount});")
        time.sleep(random.uniform(0.3, 0.8))


def human_like_mouse_move(driver, element=None) -> None:
    """Move mouse in human-like pattern.
    
    Args:
        driver: Selenium WebDriver instance
        element: Optional element to move to
    """
    actions = ActionChains(driver)
    
    # Random starting position
    start_x = random.randint(100, 500)
    start_y = random.randint(100, 500)
    
    # Move to starting position
    actions.move_by_offset(start_x, start_y)
    
    if element:
        # Move to element with offset
        actions.move_to_element_with_offset(
            element, 
            random.randint(-10, 10), 
            random.randint(-10, 10)
        )
    
    actions.perform()


def wait_for_element(
    driver,
    selector: str,
    by: By = By.CSS_SELECTOR,
    timeout: int = 10,
    clickable: bool = False
) -> Optional[WebDriverWait]:
    """Wait for element to be present or clickable.
    
    Args:
        driver: Selenium WebDriver instance
        selector: Element selector
        by: Selector type (CSS, XPATH, etc.)
        timeout: Wait timeout in seconds
        clickable: Wait for element to be clickable
        
    Returns:
        WebDriverWait instance or None
    """
    wait = WebDriverWait(driver, timeout)
    
    try:
        if clickable:
            wait.until(EC.element_to_be_clickable((by, selector)))
        else:
            wait.until(EC.presence_of_element_located((by, selector)))
        return wait
    except Exception as e:
        logger.error(f"Element not found: {selector} - {e}")
        return None


def safe_click(driver, element, retry_count: int = 3) -> bool:
    """Click element with retry logic.
    
    Args:
        driver: Selenium WebDriver instance
        element: Element to click
        retry_count: Number of retry attempts
        
    Returns:
        True if click successful, False otherwise
    """
    for attempt in range(retry_count):
        try:
            # Try regular click first
            element.click()
            return True
        except Exception as e:
            logger.warning(f"Click attempt {attempt + 1} failed: {e}")
            # Try JavaScript click as fallback
            try:
                driver.execute_script("arguments[0].click();", element)
                return True
            except Exception as js_e:
                logger.error(f"JavaScript click failed: {js_e}")
                random_delay(1, 2)
    
    return False


def upload_file(driver, file_input_selector: str, file_path: str) -> bool:
    """Upload file using file input.
    
    Args:
        driver: Selenium WebDriver instance
        file_input_selector: CSS selector for file input
        file_path: Path to file to upload
        
    Returns:
        True if upload successful, False otherwise
    """
    try:
        file_input = driver.find_element(By.CSS_SELECTOR, file_input_selector)
        file_input.send_keys(file_path)
        logger.info(f"File uploaded: {file_path}")
        return True
    except Exception as e:
        logger.error(f"File upload failed: {e}")
        return False
