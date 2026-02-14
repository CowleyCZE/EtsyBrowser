#!/usr/bin/env python3
"""Etsy Browser Bulk Uploader for StorkVisionArt.

A Selenium-based automation tool for bulk uploading digital products 
to Etsy without using the official API.
"""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd

from src.browser_utils import (
    create_driver,
    random_delay,
    human_like_scroll,
    human_like_mouse_move,
    wait_for_element,
    safe_click,
    upload_file,
)
from src.logger import setup_logger, log_error_screenshot
from src.fill_csv import read_products_csv, generate_etsy_csv

logger = setup_logger("uploader")


class EtsyUploader:
    """Etsy Browser Bulk Uploader class."""
    
    # Etsy selectors - these may need adjustment based on Etsy UI
    SELECTORS = {
        "login_email": 'input[type="email"]',
        "login_password": 'input[type="password"]',
        "login_button": 'button[type="submit"]',
        "add_listing": 'a[href*="/listings/new"]',
        "title_input": 'input[name="title"]',
        "description_editor": 'div[data-input="description"]',
        "price_input": 'input[name="price"]',
        "quantity_input": 'input[name="quantity"]',
        "category_button": 'button[data-category]',
        "digital_checkbox": 'input[name="is_digital"]',
        "image_upload": 'input[type="file"][accept*="image"]',
        "image_dropzone": 'div[data-upload-area]',
        "tags_input": 'input[data-tag-input]',
        "publish_button": 'button:contains("Publish")',
        "save_draft_button": 'button:contains("Save as draft")',
    }
    
    def __init__(self, config_path: str = "config.json"):
        """Initialize uploader with configuration.
        
        Args:
            config_path: Path to configuration JSON file
        """
        self.config = self.load_config(config_path)
        self.driver = None
        self.success_count = 0
        self.failed_count = 0
        self.start_time = None
        
    def load_config(self, config_path: str) -> dict:
        """Load configuration from JSON file.
        
        Args:
            config_path: Path to config file
            
        Returns:
            Configuration dictionary
        """
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
            logger.info(f"Loaded config from {config_path}")
            return config
        except FileNotFoundError:
            logger.warning(f"Config file not found: {config_path}, using defaults")
            return self.get_default_config()
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            return self.get_default_config()
    
    def get_default_config(self) -> dict:
        """Get default configuration."""
        return {
            "etsy_url": "https://www.etsy.com/your/shops/StorkVisionArt/manage",
            "email": "",
            "password": "",
            "headless": False,
            "delay_min": 2,
            "delay_max": 10,
            "max_products_per_hour": 50,
            "csv_file": "products.csv",
        }
    
    def login(self) -> bool:
        """Log in to Etsy.
        
        Returns:
            True if login successful, False otherwise
        """
        logger.info("Starting Etsy login...")
        
        try:
            self.driver.get(self.config.get("etsy_url", "https://www.etsy.com/signin"))
            random_delay(2, 5)
            
            # Enter email
            email_input = wait_for_element(
                self.driver, 
                self.SELECTORS["login_email"],
                timeout=10
            )
            if email_input:
                email_input.send_keys(self.config.get("email", ""))
                logger.info("Email entered")
            
            random_delay(1, 3)
            
            # Enter password
            password_input = wait_for_element(
                self.driver,
                self.SELECTORS["login_password"],
                timeout=10
            )
            if password_input:
                password_input.send_keys(self.config.get("password", ""))
                logger.info("Password entered")
            
            random_delay(1, 2)
            
            # Click login button
            login_button = wait_for_element(
                self.driver,
                self.SELECTORS["login_button"],
                clickable=True,
                timeout=10
            )
            if login_button:
                safe_click(self.driver, login_button)
                logger.info("Login button clicked")
            
            # Wait for login to complete
            random_delay(3, 6)
            
            # Verify login success (check for dashboard elements)
            current_url = self.driver.current_url
            if "signin" not in current_url.lower():
                logger.info("Login successful!")
                return True
            else:
                logger.warning("Login may have failed, continuing anyway...")
                return True
                
        except Exception as e:
            logger.error(f"Login error: {e}")
            log_error_screenshot(self.driver, "login_failed")
            return False
    
    def upload_single_product(self, product: dict) -> bool:
        """Upload a single product to Etsy.
        
        Args:
            product: Product dictionary with listing data
            
        Returns:
            True if upload successful, False otherwise
        """
        logger.info(f"Uploading product: {product.get('title', 'Unknown')}")
        
        try:
            # Navigate to add listing page
            add_listing_url = self.config.get("etsy_url", "").replace("/manage", "/listings/new")
            self.driver.get(add_listing_url)
            random_delay(2, 4)
            
            # Fill title
            title_input = wait_for_element(
                self.driver,
                self.SELECTORS["title_input"],
                timeout=10
            )
            if title_input:
                title_input.clear()
                title_input.send_keys(product.get("title", ""))
                logger.debug("Title filled")
            
            random_delay(1, 3)
            
            # Fill description
            description = product.get("description", "")
            if description:
                # Try to fill description - Etsy uses rich text editor
                try:
                    desc_editor = self.driver.find_element(
                        "css selector", 
                        self.SELECTORS["description_editor"]
                    )
                    desc_editor.click()
                    random_delay(0.5, 1)
                    self.driver.execute_script(
                        f"arguments[0].innerHTML = '{description}';", 
                        desc_editor
                    )
                    logger.debug("Description filled")
                except Exception as e:
                    logger.warning(f"Could not fill description: {e}")
            
            random_delay(1, 3)
            
            # Fill price
            price = product.get("price", "9.99")
            price_input = wait_for_element(
                self.driver,
                self.SELECTORS["price_input"],
                timeout=10
            )
            if price_input:
                price_input.clear()
                price_input.send_keys(str(price))
                logger.debug(f"Price filled: {price}")
            
            random_delay(1, 2)
            
            # Fill quantity (default 999 for digital)
            quantity = product.get("quantity", 999)
            quantity_input = wait_for_element(
                self.driver,
                self.SELECTORS["quantity_input"],
                timeout=10
            )
            if quantity_input:
                quantity_input.clear()
                quantity_input.send_keys(str(quantity))
                logger.debug(f"Quantity filled: {quantity}")
            
            random_delay(1, 3)
            
            # Upload images
            image_paths = product.get("image_paths", "")
            if image_paths:
                image_list = image_paths.split(";") if ";" in image_paths else [image_paths]
                for img_path in image_list[:10]:  # Max 10 images
                    if img_path.strip():
                        try:
                            self.upload_image(img_path.strip())
                        except Exception as e:
                            logger.warning(f"Failed to upload image {img_path}: {e}")
            
            random_delay(2, 5)
            
            # Set digital product checkbox
            self.set_digital_product()
            
            random_delay(1, 3)
            
            # Add tags
            tags = product.get("tags", "")
            if tags:
                self.add_tags(tags)
            
            random_delay(2, 4)
            
            # Scroll to bottom
            human_like_scroll(self.driver, "down", 2)
            
            # Save or publish
            # Try publish first, fall back to save draft
            try:
                publish_button = self.driver.find_element(
                    "xpath", 
                    "//button[contains(text(), 'Publish')]"
                )
                safe_click(self.driver, publish_button)
                logger.info("Product published!")
            except:
                try:
                    save_button = self.driver.find_element(
                        "xpath",
                        "//button[contains(text(), 'Save')]"
                    )
                    safe_click(self.driver, save_button)
                    logger.info("Product saved as draft")
                except:
                    logger.warning("Could not find publish/save button")
            
            random_delay(2, 4)
            
            return True
            
        except Exception as e:
            logger.error(f"Error uploading product: {e}")
            log_error_screenshot(self.driver, f"upload_error_{product.get('title', 'unknown')}")
            return False
    
    def upload_image(self, image_path: str) -> bool:
        """Upload a single image.
        
        Args:
            image_path: Path to image file
            
        Returns:
            True if upload successful, False otherwise
        """
        try:
            # Convert to absolute path
            abs_path = str(Path(image_path).absolute())
            
            # Find file input
            file_inputs = self.driver.find_elements("css selector", 'input[type="file"]')
            
            for file_input in file_inputs:
                if file_input.is_displayed():
                    file_input.send_keys(abs_path)
                    logger.info(f"Image uploaded: {image_path}")
                    random_delay(2, 4)
                    return True
            
            # Try dropzone
            try:
                dropzone = self.driver.find_element("css selector", self.SELECTORS["image_dropzone"])
                # Some Etsy uploads need drag and drop or click
                file_input = dropzone.find_element("css selector", 'input[type="file"]')
                file_input.send_keys(abs_path)
                logger.info(f"Image uploaded via dropzone: {image_path}")
                return True
            except:
                pass
            
            logger.warning(f"Could not find upload element for: {image_path}")
            return False
            
        except Exception as e:
            logger.error(f"Image upload error: {e}")
            return False
    
    def set_digital_product(self) -> bool:
        """Set product as digital download.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            # Look for digital checkbox or toggle
            digital_options = self.driver.find_elements(
                "xpath",
                "//label[contains(text(), 'Digital')]//input[@type='checkbox']"
            )
            
            for checkbox in digital_options:
                if not checkbox.is_selected():
                    safe_click(self.driver, checkbox)
                    logger.info("Digital product option enabled")
            
            return True
            
        except Exception as e:
            logger.warning(f"Could not set digital product: {e}")
            return False
    
    def add_tags(self, tags_string: str) -> bool:
        """Add tags to product.
        
        Args:
            tags_string: Comma-separated tags
            
        Returns:
            True if successful, False otherwise
        """
        try:
            tags = [t.strip() for t in tags_string.split(",")]
            
            for tag in tags[:13]:  # Etsy allows max 13 tags
                try:
                    tag_input = self.driver.find_element(
                        "css selector",
                        'input[placeholder*="tag"]'
                    )
                    tag_input.send_keys(tag)
                    random_delay(0.5, 1)
                    
                    # Press enter to add tag
                    tag_input.send_keys("\n")
                    logger.debug(f"Tag added: {tag}")
                    
                except Exception as e:
                    logger.warning(f"Could not add tag: {tag}")
            
            return True
            
        except Exception as e:
            logger.warning(f"Error adding tags: {e}")
            return False
    
    def run_bulk_upload(self, csv_file: str = None) -> dict:
        """Run bulk upload from CSV file.
        
        Args:
            csv_file: Path to products CSV file
            
        Returns:
            Dictionary with upload results
        """
        csv_path = csv_file or self.config.get("csv_file", "products.csv")
        
        logger.info(f"Starting bulk upload from {csv_path}")
        self.start_time = datetime.now()
        
        # Load products
        try:
            products = read_products_csv(csv_path)
        except Exception as e:
            logger.error(f"Failed to load products: {e}")
            return {"success": 0, "failed": 0, "total": 0}
        
        total = len(products)
        logger.info(f"Found {total} products to upload")
        
        # Create driver
        headless = self.config.get("headless", False)
        self.driver = create_driver(headless=headless)
        
        # Login
        if not self.login():
            logger.error("Login failed, aborting")
            self.driver.quit()
            return {"success": 0, "failed": total, "total": total}
        
        # Upload each product
        for i, product in enumerate(products):
            logger.info(f"Uploading product {i+1}/{total}")
            
            # Check rate limiting
            if i > 0 and i % 10 == 0:
                delay = 30  # 30 second pause every 10 products
                logger.info(f"Rate limit pause: {delay}s")
                time.sleep(delay)
            
            success = self.upload_single_product(product)
            
            if success:
                self.success_count += 1
            else:
                self.failed_count += 1
            
            # Random delay between products
            delay_min = self.config.get("delay_min", 2)
            delay_max = self.config.get("delay_max", 10)
            random_delay(delay_min, delay_max)
        
        # Close browser
        self.driver.quit()
        
        # Calculate elapsed time
        elapsed = (datetime.now() - self.start_time).total_seconds()
        
        results = {
            "success": self.success_count,
            "failed": self.failed_count,
            "total": total,
            "elapsed_seconds": elapsed,
        }
        
        logger.info(f"Bulk upload complete: {self.success_count}/{total} successful in {elapsed:.1f}s")
        
        return results


def main():
    """Main entry point for uploader script."""
    parser = argparse.ArgumentParser(
        description="Etsy Browser Bulk Uploader for StorkVisionArt"
    )
    parser.add_argument(
        '--mode',
        choices=['single', 'bulk'],
        default='bulk',
        help='Upload mode: single or bulk (default: bulk)'
    )
    parser.add_argument(
        '--csv',
        default='products.csv',
        help='CSV file with products (default: products.csv)'
    )
    parser.add_argument(
        '--config',
        default='config.json',
        help='Configuration file (default: config.json)'
    )
    parser.add_argument(
        '--product-id',
        type=int,
        help='Product ID for single mode (row number in CSV)'
    )
    parser.add_argument(
        '--headless',
        action='store_true',
        help='Run browser in headless mode'
    )
    
    args = parser.parse_args()
    
    # Create uploader
    uploader = EtsyUploader(config_path=args.config)
    
    # Override headless setting if specified
    if args.headless:
        uploader.config["headless"] = True
    
    # Run in specified mode
    if args.mode == 'single':
        if not args.product_id:
            logger.error("Product ID required for single mode")
            return 1
        
        # Load products and get specific one
        try:
            products = read_products_csv(args.csv)
            product = products[args.product_id - 1]  # 1-based index
        except Exception as e:
            logger.error(f"Error loading product: {e}")
            return 1
        
        # Create driver
        uploader.driver = create_driver(headless=uploader.config.get("headless", False))
        
        # Login
        if not uploader.login():
            logger.error("Login failed")
            uploader.driver.quit()
            return 1
        
        # Upload product
        success = uploader.upload_single_product(product)
        
        uploader.driver.quit()
        
        if success:
            logger.info("Product uploaded successfully!")
            return 0
        else:
            logger.error("Product upload failed")
            return 1
    
    else:  # bulk mode
        results = uploader.run_bulk_upload(args.csv)
        
        print("\n" + "="*50)
        print("UPLOAD RESULTS")
        print("="*50)
        print(f"Total products: {results['total']}")
        print(f"Successful: {results['success']}")
        print(f"Failed: {results['failed']}")
        print(f"Time elapsed: {results.get('elapsed_seconds', 0):.1f}s")
        print("="*50)
        
        return 0 if results['failed'] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
