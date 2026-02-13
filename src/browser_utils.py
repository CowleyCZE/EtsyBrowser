#!/usr/bin/env python3
"""
Browser Utilities for Human-like Automation
Handles random delays, mouse movements, typing simulation, etc.
"""

import random
import time
from typing import Optional, Union

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    StaleElementReferenceException
)


class BrowserUtils:
    """Utilities for human-like browser automation."""
    
    def __init__(self, driver: webdriver.Chrome):
        self.driver = driver
        self.actions = ActionChains(driver)
        self.wait = WebDriverWait(driver, 10)
    
    def random_delay(self, min_seconds: float = 1, max_seconds: float = 3):
        """Add random delay between actions."""
        delay = random.uniform(min_seconds, max_seconds)
        time.sleep(delay)
    
    def human_type(self, element, text: str, char_delay: tuple = (0.05, 0.2)):
        """Type text with human-like delays."""
        element.clear()
        for char in text:
            element.send_keys(char)
            time.sleep(random.uniform(*char_delay))
    
    def human_click(self, element, retry: int = 3):
        """Click with human-like behavior and retry logic."""
        for attempt in range(retry):
            try:
                # Scroll element into view
                self.driver.execute_script(
                    "arguments[0].scrollIntoView({block: 'center'});", 
                    element
                )
                self.random_delay(0.3, 0.8)
                
                # Move mouse to element with offset
                self._human_move_to_element(element)
                
                # Click
                element.click()
                self.random_delay(0.2, 0.5)
                return True
                
            except Exception as e:
                if attempt < retry - 1:
                    self.random_delay(1, 2)
                else:
                    # Try JavaScript click as fallback
                    try:
                        self.driver.execute_script("arguments[0].click();", element)
                        return True
                    except:
                        pass
        return False
    
    def _human_move_to_element(self, element, offset_x: int = 0, offset_y: int = 0):
        """Move mouse to element with human-like path."""
        # Get element location
        location = element.location
        size = element.size
        
        # Calculate center with random offset
        center_x = location['x'] + size['width'] // 2 + random.randint(-10, 10) + offset_x
        center_y = location['y'] + size['height'] // 2 + random.randint(-10, 10) + offset_y
        
        # Move to element with multiple steps
        current_pos = self.driver.get_window_size()
        
        # Start from random position
        start_x = random.randint(0, current_pos['width'])
        start_y = random.randint(0, current_pos['height'])
        
        # Move in bezier-like curve (multiple intermediate points)
        for i in range(3):
            progress = (i + 1) / 3
            x = int(start_x + (center_x - start_x) * progress + random.randint(-20, 20))
            y = int(start_y + (center_y - start_y) * progress + random.randint(-20, 20))
            
            self.actions.move_by_offset(x, y).perform()
            self.random_delay(0.1, 0.3)
    
    def human_scroll(self, direction: str = 'down', amount: int = None):
        """Scroll with human-like behavior."""
        if amount is None:
            amount = random.randint(300, 800)
        
        if direction == 'down':
            script = f"window.scrollBy(0, {amount});"
        else:
            script = f"window.scrollBy(0, -{amount});"
        
        self.driver.execute_script(script)
        self.random_delay(0.3, 0.8)
    
    def scroll_to_element(self, element):
        """Scroll element into view smoothly."""
        self.driver.execute_script(
            "arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});",
            element
        )
        self.random_delay(0.5, 1)
    
    def wait_for_element(self, selector: str, by: By = By.CSS_SELECTOR, 
                          timeout: int = 10) -> Optional[webdriver.remote.webelement.WebElement]:
        """Wait for element to be present and return it."""
        try:
            element = WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((by, selector))
            )
            return element
        except TimeoutException:
            return None
    
    def wait_for_clickable(self, selector: str, by: By = By.CSS_SELECTOR,
                           timeout: int = 10) -> Optional[webdriver.remote.webelement.WebElement]:
        """Wait for element to be clickable."""
        try:
            element = WebDriverWait(self.driver, timeout).until(
                EC.element_to_be_clickable((by, selector))
            )
            return element
        except TimeoutException:
            return None
    
    def wait_for_visible(self, selector: str, by: By = By.CSS_SELECTOR,
                         timeout: int = 10) -> Optional[webdriver.remote.webelement.WebElement]:
        """Wait for element to be visible."""
        try:
            element = WebDriverWait(self.driver, timeout).until(
                EC.visibility_of_element_located((by, selector))
            )
            return element
        except TimeoutException:
            return None
    
    def safe_find(self, selector: str, by: By = By.CSS_SELECTOR) -> list:
        """Safely find multiple elements."""
        try:
            return self.driver.find_elements(by, selector)
        except:
            return []
    
    def safe_click(self, selector: str, by: By = By.CSS_SELECTOR) -> bool:
        """Safely click an element."""
        try:
            element = self.driver.find_element(by, selector)
            return self.human_click(element)
        except:
            return False
    
    def random_mouse_movements(self, count: int = 3):
        """Perform random mouse movements to avoid detection."""
        for _ in range(count):
            x = random.randint(100, 800)
            y = random.randint(100, 600)
            self.actions.move_by_offset(x, y).perform()
            self.random_delay(0.1, 0.3)
    
    def simulate_thinking(self):
        """Simulate thinking/reading time."""
        self.random_delay(1, 3)
    
    def hover_element(self, element):
        """Hover over an element."""
        try:
            self.actions.move_to_element(element).perform()
            self.random_delay(0.3, 0.7)
        except:
            pass
    
    def double_click(self, element):
        """Double click an element."""
        try:
            self.actions.double_click(element).perform()
            self.random_delay(0.2, 0.5)
        except:
            pass
    
    def right_click(self, element):
        """Right click an element."""
        try:
            self.actions.context_click(element).perform()
            self.random_delay(0.2, 0.5)
        except:
            pass
    
    def drag_and_drop(self, source, target):
        """Drag and drop element."""
        try:
            self.actions.drag_and_drop(source, target).perform()
            self.random_delay(0.5, 1)
        except:
            pass
    
    def switch_to_iframe(self, iframe_selector: str):
        """Switch to iframe."""
        try:
            iframe = self.wait_for_element(iframe_selector)
            if iframe:
                self.driver.switch_to.frame(iframe)
                return True
        except:
            pass
        return False
    
    def switch_to_default_content(self):
        """Switch back to default content."""
        self.driver.switch_to.default_content()
    
    def get_element_text(self, selector: str, by: By = By.CSS_SELECTOR) -> str:
        """Get element text safely."""
        try:
            element = self.driver.find_element(by, selector)
            return element.text
        except:
            return ""
    
    def is_element_present(self, selector: str, by: By = By.CSS_SELECTOR) -> bool:
        """Check if element is present."""
        try:
            self.driver.find_element(by, selector)
            return True
        except:
            return False
    
    def is_element_visible(self, selector: str, by: By = By.CSS_SELECTOR) -> bool:
        """Check if element is visible."""
        try:
            element = self.driver.find_element(by, selector)
            return element.is_displayed()
        except:
            return False
    
    def take_screenshot(self, name: str = "screenshot") -> str:
        """Take a screenshot and return the path."""
        from datetime import datetime
        import os
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{name}_{timestamp}.png"
        filepath = os.path.join("logs", filename)
        
        # Ensure logs directory exists
        os.makedirs("logs", exist_ok=True)
        
        self.driver.save_screenshot(filepath)
        return filepath


class AntiDetection:
    """Additional anti-detection measures."""
    
    @staticmethod
    def patch_webdriver(driver):
        """Patch WebDriver to avoid detection."""
        # Hide webdriver property
        driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
            'source': '''
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                })
            '''
        })
    
    @staticmethod
    def set_permissions(driver, permission: str = 'default'):
        """Set permissions."""
        driver.execute_cdp_cmd('Browser.setPermission', {
            'permission': permission,
            'setting': 'default'
        })
    
    @staticmethod
    def add_plugins(driver):
        """Add fake plugins."""
        driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
            'source': '''
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5]
                })
            '''
        })
    
    @staticmethod
    def add_languages(driver):
        """Add fake languages."""
        driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
            'source': '''
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['en-US', 'en']
                })
            '''
        })
