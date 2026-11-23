"""Browser utilities for Etsy Browser Bulk Uploader."""

import os
import random
import time
from pathlib import Path
from typing import Optional

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.remote.webelement import WebElement
from selenium.common.exceptions import TimeoutException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager
from selenium_stealth import stealth

from src.logger import setup_logger

logger = setup_logger("browser_utils")


def _fix_driver_path(path: str) -> str:
    """Opraví cestu od webdriver-manageru.

    Verze 4.0.1 u balíčků Chrome for Testing někdy vrátí první soubor z archivu
    (např. THIRD_PARTY_NOTICES.chromedriver) místo samotného programu `chromedriver`.
    """
    p = Path(path)
    if p.name in ("chromedriver", "chromedriver.exe"):
        return path
    for candidate in (p.parent / "chromedriver", p.parent / "chromedriver.exe"):
        if candidate.is_file():
            if os.name == "posix":
                candidate.chmod(candidate.stat().st_mode | 0o111)
            return str(candidate)
    return path


def build_user_agent(browser_version: str) -> str:
    """Sestaví user agent s hlavní verzí skutečného Chrome (např. '158.0.8127.36' -> Chrome/158.0.0.0)."""
    major = (browser_version or "").split(".")[0]
    if not major.isdigit():
        major = "120"
    return (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        f"Chrome/{major}.0.0.0 Safari/537.36"
    )


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
    
    # User agent se nastavuje až po startu (podle skutečné verze Chrome), viz níže
    
    # Primárně Selenium Manager (součást Selenium, vybere ovladač podle nainstalovaného Chromu),
    # záložně webdriver-manager s opravenou cestou k ovladači.
    try:
        driver = webdriver.Chrome(options=options)
    except (WebDriverException, OSError) as exc:
        logger.warning(f"Selenium Manager selhal ({exc}), zkouším webdriver-manager")
        service = Service(_fix_driver_path(ChromeDriverManager().install()))
        driver = webdriver.Chrome(service=service, options=options)
    
    # User agent podle skutečné hlavní verze Chrome (pevná stará verze by s ovladačem neseděla).
    # Musí se předat i do stealth(): ten jinak UA znovu přepíše (původním UA prohlížeče, na Linuxu
    # s "X11; Linux" a platformou Win32), čímž by předchozí přepis přestal platit.
    user_agent = None
    try:
        user_agent = build_user_agent(driver.capabilities.get("browserVersion", ""))
        driver.execute_cdp_cmd("Network.setUserAgentOverride", {"userAgent": user_agent, "platform": "Win32"})
    except Exception as exc:  # noqa: BLE001 - bez přepisu UA poběží i další
        logger.warning(f"Nepodařilo se nastavit user agent: {exc}")
        user_agent = None

    # Apply selenium-stealth
    stealth(
        driver,
        user_agent=user_agent,
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
) -> Optional[WebElement]:
    """Wait for element to be present or clickable.
    
    Args:
        driver: Selenium WebDriver instance
        selector: Element selector
        by: Selector type (CSS, XPATH, etc.)
        timeout: Wait timeout in seconds
        clickable: Wait for element to be clickable
        
    Returns:
        Nalezený WebElement nebo None, pokud se element do timeoutu neobjevil
    """
    wait = WebDriverWait(driver, timeout)
    
    try:
        if clickable:
            return wait.until(EC.element_to_be_clickable((by, selector)))
        return wait.until(EC.presence_of_element_located((by, selector)))
    except (TimeoutException, WebDriverException) as e:
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


def find_element_by_any_selector(driver, selectors: list) -> Optional[webdriver.remote.webelement.WebElement]:
    """Najde element pomocí libovolného ze zadaných selektorů.
    
    Args:
        driver: Selenium WebDriver
        selectors: Seznam CSS selektorů
        
    Returns:
        Nalezený element nebo None
    """
    for selector in selectors:
        try:
            element = driver.find_element(By.CSS_SELECTOR, selector)
            if element and element.is_displayed():
                return element
        except WebDriverException:
            continue
    return None
