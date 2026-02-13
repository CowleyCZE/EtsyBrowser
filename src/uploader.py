#!/usr/bin/env python3
"""
Etsy Browser Bulk Uploader
Main uploader script for automated Etsy product uploads.

Usage:
    python uploader.py --mode single --headless
    python uploader.py --mode bulk --headless
    python uploader.py --mode single --product-id 1
"""

import argparse
import json
import os
import sys
import time
import random
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import (
    TimeoutException, 
    NoSuchElementException,
    ElementClickInterceptedException,
    StaleElementReferenceException
)

# Import local modules
from browser_utils import BrowserUtils
from logger import UploaderLogger


class EtsyUploader:
    """Main class for Etsy bulk uploading automation."""
    
    # Etsy selectors - these may need updating if Etsy changes their UI
    SELECTORS = {
        # Login page
        'email_input': 'input[type="email"]',
        'password_input': 'input[type="password"]',
        'signin_button': 'button[type="submit"]',
        
        # Dashboard
        'add_listing_button': 'button[data-testid="add-listing-button"], a[href*="/create/listing"]',
        'manage_link': 'a[href*="/manage"]',
        
        # Listing form
        'title_input': 'input[name="title"], input[data-testid="listing-title-input"]',
        'description_editor': 'div[data-testid="description-editor"], textarea[name="description"]',
        'price_input': 'input[name="price"], input[data-testid="price-input"]',
        'quantity_input': 'input[name="quantity"], input[data-testid="quantity-input"]',
        
        # Category
        'category_button': 'button[data-testid="category-select-button"]',
        'category_search': 'input[placeholder*="category"], input[data-testid="category-search"]',
        
        # Tags
        'tags_input': 'input[data-testid="tags-input"], input[placeholder*="tag"]',
        'add_tag_button': 'button[data-testid="add-tag-button"]',
        
        # Images
        'image_upload_area': 'input[type="file"][accept*="image"]',
        'image_dropzone': 'div[data-testid="image-dropzone"], div[class*="upload"]',
        
        # Digital settings
        'is_digital_toggle': 'input[type="checkbox"][name="is_digital"]',
        'digital_file_upload': 'input[type="file"][name="digital_file"]',
        
        # Publishing
        'publish_button': 'button[data-testid="publish-button"], button:contains("Publish")',
        'save_draft_button': 'button[data-testid="save-draft-button"]',
        
        # Bulk edit
        'bulk_edit_link': 'a[href*="bulk-edit"], a[data-testid="bulk-edit-link"]',
        'download_template_button': 'button[data-testid="download-csv-template"]',
        'upload_csv_button': 'input[type="file"][accept*="csv"]',
        
        # Status
        'success_message': 'div[data-testid="success-message"], div[class*="success"]',
        'error_message': 'div[data-testid="error-message"], div[class*="error"]',
    }
    
    # Default tags for digital prints
    DEFAULT_TAGS = [
        "digital art", "AI print", "wall decor", "modern art",
        "printable art", "digital download", "wall art", "poster art",
        "home decor", "instant download", "AI art", "contemporary art"
    ]
    
    def __init__(self, config_path: str = "config.json", headless: bool = False):
        """Initialize the uploader with configuration."""
        self.config = self._load_config(config_path)
        self.headless = headless
        self.driver: Optional[webdriver.Chrome] = None
        self.browser_utils = None
        self.logger = UploaderLogger()
        self.stats = {
            'total': 0,
            'success': 0,
            'failed': 0,
            'skipped': 0,
            'start_time': None,
            'end_time': None
        }
        
    def _load_config(self, config_path: str) -> dict:
        """Load configuration from JSON file."""
        try:
            with open(config_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"Config file {config_path} not found. Using defaults.")
            return self._default_config()
    
    def _default_config(self) -> dict:
        """Return default configuration."""
        return {
            'etsy': {
                'shop_name': 'StorkVisionArt',
                'base_url': 'https://www.etsy.com/your/shops/StorkVisionArt/manage',
                'login_url': 'https://www.etsy.com/signin'
            },
            'credentials': {
                'email': '',
                'password': ''
            },
            'settings': {
                'headless': False,
                'max_retries': 3,
                'delay_between_products': 30,
                'max_products_per_hour': 50,
                'min_delay': 2,
                'max_delay': 10,
                'screenshot_on_error': True
            },
            'defaults': {
                'quantity': 999,
                'who_made': 'AI_GENERATED',
                'is_digital': True,
                'shipping_template': 'digital_download'
            }
        }
    
    def setup_driver(self):
        """Set up Selenium WebDriver with stealth options."""
        options = Options()
        
        if self.headless:
            options.add_argument('--headless=new')
        
        # Anti-detection options
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_argument('--disable-extensions')
        options.add_argument('--disable-popup-blocking')
        options.add_argument('--ignore-certificate-errors')
        options.add_argument('--ignore-ssl-errors')
        
        # Window size
        options.add_argument('--window-size=1920,1080')
        
        # User agent
        options.add_argument(
            '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        
        # Create driver
        try:
            self.driver = webdriver.Chrome(options=options)
            self.browser_utils = BrowserUtils(self.driver)
            
            # Set timeouts
            self.driver.set_page_load_timeout(30)
            self.driver.implicitly_wait(10)
            
            print(f"✓ Chrome driver initialized (headless: {self.headless})")
        except Exception as e:
            print(f"✗ Failed to initialize driver: {e}")
            raise
    
    def login(self) -> bool:
        """Log in to Etsy."""
        print("\n📱 Logging in to Etsy...")
        
        try:
            self.driver.get(self.config['etsy']['login_url'])
            self.browser_utils.random_delay(2, 5)
            
            # Enter email
            email_input = self.browser_utils.wait_for_element(
                self.SELECTORS['email_input'], timeout=10
            )
            if email_input:
                self.browser_utils.human_type(email_input, self.config['credentials']['email'])
            
            self.browser_utils.random_delay(1, 3)
            
            # Click continue or enter password
            try:
                continue_button = self.driver.find_element(By.CSS_SELECTOR, 
                    'button[type="submit"], input[type="submit"]')
                continue_button.click()
                self.browser_utils.random_delay(2, 4)
            except:
                pass
            
            # Enter password
            password_input = self.browser_utils.wait_for_element(
                self.SELECTORS['password_input'], timeout=10
            )
            if password_input:
                self.browser_utils.human_type(password_input, self.config['credentials']['password'])
            
            self.browser_utils.random_delay(1, 2)
            
            # Click sign in
            signin_button = self.browser_utils.wait_for_element(
                self.SELECTORS['signin_button'], timeout=10
            )
            if signin_button:
                signin_button.click()
            
            # Wait for dashboard to load
            self.browser_utils.random_delay(3, 6)
            
            # Check if login was successful
            if 'signin' not in self.driver.current_url.lower():
                print("✓ Login successful!")
                return True
            else:
                print("✗ Login may have failed. Please check manually.")
                return False
                
        except Exception as e:
            print(f"✗ Login error: {e}")
            self.logger.save_screenshot(self.driver, "login_error")
            return False
    
    def navigate_to_add_listing(self) -> bool:
        """Navigate to the add listing page."""
        print("\n📝 Navigating to Add Listing...")
        
        try:
            self.driver.get(self.config['etsy']['base_url'] + '/create/listing')
            self.browser_utils.random_delay(2, 5)
            return True
        except Exception as e:
            print(f"✗ Navigation error: {e}")
            return False
    
    def upload_single_product(self, product: dict, retry_count: int = 0) -> bool:
        """Upload a single product to Etsy."""
        max_retries = self.config['settings']['max_retries']
        
        try:
            print(f"\n  📦 Processing: {product.get('title', 'Unknown')[:50]}...")
            
            # Navigate to add listing
            if not self.navigate_to_add_listing():
                return self._handle_retry(product, retry_count, max_retries)
            
            # Fill title
            self._fill_title(product.get('title', ''))
            
            # Fill description
            self._fill_description(product.get('description', ''))
            
            # Fill price
            self._fill_price(product.get('price', 0))
            
            # Fill quantity
            self._fill_quantity(product.get('quantity', 999))
            
            # Select category
            self._select_category(product.get('category_path', ''))
            
            # Add tags
            self._add_tags(product.get('tags', ''))
            
            # Upload images
            self._upload_images(product.get('image_paths', ''))
            
            # Set digital product options
            self._set_digital_options()
            
            # Publish
            if self._publish_listing():
                print(f"  ✓ Published: {product.get('title', '')[:30]}...")
                return True
            else:
                return self._handle_retry(product, retry_count, max_retries)
                
        except Exception as e:
            print(f"  ✗ Error: {e}")
            self.logger.save_screenshot(self.driver, f"error_{product.get('title', 'unknown')}")
            
            if retry_count < max_retries:
                return self._handle_retry(product, retry_count, max_retries)
            
            return False
    
    def _handle_retry(self, product: dict, retry_count: int, max_retries: int) -> bool:
        """Handle retry logic for failed uploads."""
        if retry_count < max_retries:
            print(f"  ⚠ Retrying ({retry_count + 1}/{max_retries})...")
            self.browser_utils.random_delay(5, 10)
            return self.upload_single_product(product, retry_count + 1)
        return False
    
    def _fill_title(self, title: str) -> bool:
        """Fill in the product title."""
        try:
            title_input = self.browser_utils.wait_for_element(
                self.SELECTORS['title_input'], timeout=5
            )
            if title_input:
                self.browser_utils.human_type(title_input, title)
                self.browser_utils.random_delay(0.5, 1.5)
                return True
        except Exception as e:
            print(f"    ✗ Title error: {e}")
        return False
    
    def _fill_description(self, description: str) -> bool:
        """Fill in the product description."""
        try:
            desc_input = self.browser_utils.wait_for_element(
                self.SELECTORS['description_editor'], timeout=5
            )
            if desc_input:
                self.browser_utils.human_type(desc_input, description)
                self.browser_utils.random_delay(0.5, 1.5)
                return True
        except Exception as e:
            print(f"    ✗ Description error: {e}")
        return False
    
    def _fill_price(self, price: float) -> bool:
        """Fill in the product price."""
        try:
            price_input = self.browser_utils.wait_for_element(
                self.SELECTORS['price_input'], timeout=5
            )
            if price_input:
                price_input.clear()
                self.browser_utils.human_type(price_input, str(price))
                self.browser_utils.random_delay(0.5, 1)
                return True
        except Exception as e:
            print(f"    ✗ Price error: {e}")
        return False
    
    def _fill_quantity(self, quantity: int) -> bool:
        """Fill in the product quantity."""
        try:
            qty_input = self.browser_utils.wait_for_element(
                self.SELECTORS['quantity_input'], timeout=5
            )
            if qty_input:
                qty_input.clear()
                qty_input.send_keys(str(quantity))
                self.browser_utils.random_delay(0.3, 0.8)
                return True
        except Exception as e:
            print(f"    ✗ Quantity error: {e}")
        return False
    
    def _select_category(self, category_path: str) -> bool:
        """Select product category."""
        try:
            if not category_path:
                category_path = self.config['categories']['digital_print']
            
            # Click category button
            cat_button = self.browser_utils.wait_for_element(
                self.SELECTORS['category_button'], timeout=5
            )
            if cat_button:
                cat_button.click()
                self.browser_utils.random_delay(1, 2)
            
            # Search for category
            cat_search = self.browser_utils.wait_for_element(
                self.SELECTORS['category_search'], timeout=5
            )
            if cat_search:
                self.browser_utils.human_type(cat_search, category_path.split(':')[-1])
                self.browser_utils.random_delay(1, 2)
                
                # Select first result
                first_result = self.driver.find_element(By.CSS_SELECTOR, 
                    'div[data-testid="category-result"], li[class*="category"]')
                if first_result:
                    first_result.click()
                    
            return True
        except Exception as e:
            print(f"    ⚠ Category: {e}")
        return False
    
    def _add_tags(self, tags: str) -> bool:
        """Add product tags."""
        try:
            # Parse tags
            if isinstance(tags, str):
                tag_list = [t.strip() for t in tags.split(',')]
            else:
                tag_list = tags if isinstance(tags, list) else []
            
            # Add default tags if none provided
            if not tag_list:
                tag_list = self.DEFAULT_TAGS[:13]
            
            # Limit to 13 tags (Etsy max)
            tag_list = tag_list[:13]
            
            for tag in tag_list:
                try:
                    tag_input = self.browser_utils.wait_for_element(
                        self.SELECTORS['tags_input'], timeout=3
                    )
                    if tag_input:
                        tag_input.send_keys(tag)
                        self.browser_utils.random_delay(0.3, 0.7)
                        
                        # Press enter to add tag
                        tag_input.send_keys('\n')
                        self.browser_utils.random_delay(0.3, 0.5)
                except:
                    pass
                    
            return True
        except Exception as e:
            print(f"    ⚠ Tags error: {e}")
        return False
    
    def _upload_images(self, image_paths: str) -> bool:
        """Upload product images."""
        try:
            if not image_paths:
                return True
                
            # Parse image paths
            if isinstance(image_paths, str):
                paths = [p.strip() for p in image_paths.split(';') if p.strip()]
            else:
                paths = image_paths if isinstance(image_paths, list) else []
            
            if not paths:
                return True
                
            # Find file input
            file_input = self.driver.find_element(By.CSS_SELECTOR, 
                self.SELECTORS['image_upload_area'])
            
            if file_input:
                # Upload up to 10 images
                for path in paths[:10]:
                    full_path = os.path.abspath(path)
                    if os.path.exists(full_path):
                        file_input.send_keys(full_path)
                        self.browser_utils.random_delay(1, 2)
                
                print(f"    ✓ Uploaded {len(paths)} image(s)")
                return True
                
        except Exception as e:
            print(f"    ⚠ Image upload: {e}")
        return False
    
    def _set_digital_options(self) -> bool:
        """Set digital product options."""
        try:
            # Check if digital toggle exists
            digital_toggles = self.driver.find_elements(By.CSS_SELECTOR, 
                self.SELECTORS['is_digital_toggle'])
            
            for toggle in digital_toggles:
                if not toggle.is_selected():
                    toggle.click()
                    
            self.browser_utils.random_delay(0.5, 1)
            return True
        except Exception as e:
            print(f"    ⚠ Digital options: {e}")
        return False
    
    def _publish_listing(self) -> bool:
        """Publish the listing."""
        try:
            # Try to find publish button
            publish_buttons = self.driver.find_elements(By.CSS_SELECTOR, 
                self.SELECTORS['publish_button'])
            
            for button in publish_buttons:
                if button.is_enabled():
                    button.click()
                    self.browser_utils.random_delay(2, 4)
                    return True
                    
            # Try save draft as fallback
            draft_buttons = self.driver.find_elements(By.CSS_SELECTOR,
                self.SELECTORS['save_draft_button'])
            for button in draft_buttons:
                if button.is_enabled():
                    button.click()
                    self.browser_utils.random_delay(2, 4)
                    return True
                    
        except Exception as e:
            print(f"    ✗ Publish error: {e}")
            
        return False
    
    def load_products_csv(self, csv_path: str) -> list:
        """Load products from CSV file."""
        try:
            df = pd.read_csv(csv_path)
            print(f"\n📊 Loaded {len(df)} products from {csv_path}")
            return df.to_dict('records')
        except Exception as e:
            print(f"✗ Failed to load CSV: {e}")
            return []
    
    def upload_bulk(self, csv_path: str = "products.csv", start_index: int = 0):
        """Upload multiple products from CSV."""
        print(f"\n🚀 Starting bulk upload from {csv_path}")
        
        products = self.load_products_csv(csv_path)
        
        if not products:
            print("✗ No products to upload")
            return
        
        self.stats['total'] = len(products)
        self.stats['start_time'] = datetime.now()
        
        # Set up driver
        self.setup_driver()
        
        # Login
        if not self.login():
            print("✗ Login failed. Exiting.")
            self.cleanup()
            return
        
        # Upload each product
        for i, product in enumerate(products[start_index:], start=start_index):
            print(f"\n[{i+1}/{self.stats['total']}] Processing...")
            
            success = self.upload_single_product(product)
            
            if success:
                self.stats['success'] += 1
            else:
                self.stats['failed'] += 1
            
            # Delay between products
            if i < len(products) - 1:
                delay = self.config['settings']['delay_between_products']
                print(f"  ⏳ Waiting {delay}s before next product...")
                time.sleep(delay)
        
        self.stats['end_time'] = datetime.now()
        self._print_summary()
        self.cleanup()
    
    def upload_single(self, product_id: int = 0):
        """Upload a single product by ID."""
        print(f"\n🚀 Starting single product upload (ID: {product_id})")
        
        products = self.load_products_csv("products.csv")
        
        if not products or product_id >= len(products):
            print("✗ Product not found")
            return
        
        self.stats['total'] = 1
        self.stats['start_time'] = datetime.now()
        
        # Set up driver
        self.setup_driver()
        
        # Login
        if not self.login():
            print("✗ Login failed. Exiting.")
            self.cleanup()
            return
        
        # Upload the product
        success = self.upload_single_product(products[product_id])
        
        if success:
            self.stats['success'] += 1
        else:
            self.stats['failed'] += 1
        
        self.stats['end_time'] = datetime.now()
        self._print_summary()
        self.cleanup()
    
    def _print_summary(self):
        """Print upload summary."""
        duration = self.stats['end_time'] - self.stats['start_time']
        
        print("\n" + "="*50)
        print("📈 UPLOAD SUMMARY")
        print("="*50)
        print(f"  Total:     {self.stats['total']}")
        print(f"  Success:   ✓ {self.stats['success']}")
        print(f"  Failed:    ✗ {self.stats['failed']}")
        print(f"  Duration:  {duration}")
        print("="*50)
    
    def cleanup(self):
        """Clean up resources."""
        if self.driver:
            self.driver.quit()
            print("\n✓ Browser closed")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Etsy Browser Bulk Uploader')
    parser.add_argument('--mode', choices=['single', 'bulk'], default='bulk',
                        help='Upload mode: single or bulk')
    parser.add_argument('--headless', action='store_true',
                        help='Run browser in headless mode')
    parser.add_argument('--product-id', type=int, default=0,
                        help='Product ID for single mode (0-indexed)')
    parser.add_argument('--csv', default='products.csv',
                        help='Path to CSV file')
    parser.add_argument('--start-index', type=int, default=0,
                        help='Starting index for bulk upload')
    parser.add_argument('--config', default='config.json',
                        help='Path to config file')
    
    args = parser.parse_args()
    
    # Check config
    if not os.path.exists(args.config):
        print(f"✗ Config file not found: {args.config}")
        print("  Please create config.json from config.example.json")
        sys.exit(1)
    
    # Create uploader
    uploader = EtsyUploader(args.config, headless=args.headless)
    
    # Run in appropriate mode
    if args.mode == 'single':
        uploader.upload_single(args.product_id)
    else:
        uploader.upload_bulk(args.csv, args.start_index)


if __name__ == '__main__':
    main()
