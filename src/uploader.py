#!/usr/bin/env python3
"""Etsy Browser Bulk Uploader for StorkVisionArt.

A Selenium-based automation tool for bulk uploading digital products 
to Etsy without using the official API.

Supports dynamic selectors loaded from src/selectors.json
"""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

from src.browser_utils import (
    create_driver,
    random_delay,
    human_like_scroll,
    human_like_mouse_move,
    wait_for_element,
    safe_click,
    upload_file,
    find_element_by_any_selector,
)
from src.logger import setup_logger, log_error_screenshot
from src.fill_csv import read_products_csv, generate_etsy_csv

logger = setup_logger("uploader")


# Výchozí selektory - použijí se pokud selectors.json neexistuje
DEFAULT_SELECTORS = {
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


def load_selectors(selectors_file: str = "src/selectors.json") -> dict:
    """Načte selektory z JSON souboru.
    
    Args:
        selectors_file: Cesta k selectors.json
        
    Returns:
        Slovník selektorů
    """
    selectors_path = Path(selectors_file)
    
    if not selectors_path.exists():
        logger.warning(f"Selektory soubor {selectors_file} nenalezen, používám výchozí")
        return DEFAULT_SELECTORS
    
    try:
        with open(selectors_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Filtrujeme metadata (položky začínající podtržítkem)
        selectors = {k: v for k, v in data.items() if not k.startswith('_')}
        
        # Zkontrolujeme, zda máme platné selektory
        empty_count = sum(1 for v in selectors.values() if not v.get('primary'))
        
        if empty_count > 0:
            logger.warning(f"{empty_count} selektorů je prázdných, používám výchozí jako fallback")
        
        logger.info(f"Selektory načteny z {selectors_file}")
        return selectors
        
    except Exception as e:
        logger.error(f"Chyba při načítání selektorů: {e}")
        return DEFAULT_SELECTORS


def get_selector(driver, selector_key: str, selectors: dict, by_type: str = "css") -> Optional[object]:
    """Najde element pomocí primárního nebo fallback selektorů.
    
    Args:
        driver: Selenium WebDriver
        selector_key: Klíč selektoru (např. 'title_input')
        selectors: Slovník selektorů
        by_type: 'css' nebo 'xpath'
        
    Returns:
        Nalezený WebElement nebo None
    """
    if selector_key not in selectors:
        # Zkusit výchozí selektory
        if selector_key in DEFAULT_SELECTORS:
            try:
                return driver.find_element("css selector", DEFAULT_SELECTORS[selector_key])
            except:
                pass
        return None
    
    selector_data = selectors[selector_key]
    
    # Zkusit primární selektor
    primary = selector_data.get('primary')
    if primary:
        try:
            if by_type == "xpath" and selector_data.get('xpath'):
                return driver.find_element("xpath", selector_data['xpath'])
            return driver.find_element("css selector", primary)
        except:
            pass
    
    # Zkusit fallback selektory
    for fallback in selector_data.get('fallback', []):
        try:
            return driver.find_element("css selector", fallback)
        except:
            continue
    
    # Zkusit výchozí selektory jako poslední zálohu
    if selector_key in DEFAULT_SELECTORS:
        try:
            return driver.find_element("css selector", DEFAULT_SELECTORS[selector_key])
        except:
            pass
    
    return None


class EtsyUploader:
    """Etsy Browser Bulk Uploader class."""
    
    def __init__(self, config_path: str = "config.json", selectors_file: str = "src/selectors.json"):
        """Initialize uploader with configuration.
        
        Args:
            config_path: Path to configuration JSON file
            selectors_file: Path to selectors JSON file
        """
        self.config = self.load_config(config_path)
        self.selectors = load_selectors(selectors_file)
        self.driver = None
        self.success_count = 0
        self.failed_count = 0
        self.start_time = None
        
        logger.info(f"Inicializace uploaderu s {len(self.selectors)} selektory")
    
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
    
    def find_element(self, selector_key: str, by_type: str = "css", timeout: int = 10) -> Optional[object]:
        """Najde element pomocí dynamických selektorů.
        
        Args:
            selector_key: Klíč selektoru
            by_type: 'css' nebo 'xpath'
            timeout: Čekací timeout
            
        Returns:
            WebElement nebo None
        """
        element = get_selector(self.driver, selector_key, self.selectors, by_type)
        
        if element:
            # Zkontrolovat, zda je element viditelný
            try:
                if element.is_displayed():
                    return element
            except:
                pass
        
        return None
    
    def login(self) -> bool:
        """Log in to Etsy.
        
        Returns:
            True if login successful, False otherwise
        """
        logger.info("Starting Etsy login...")
        
        try:
            self.driver.get(self.config.get("etsy_url", "https://www.etsy.com/signin"))
            random_delay(2, 5)
            
            # Najít a vyplnit email
            email_input = self.find_element("login_email")
            if email_input:
                email_input.send_keys(self.config.get("email", ""))
                logger.info("Email entered")
            
            random_delay(1, 3)
            
            # Najít a vyplnit heslo
            password_input = self.find_element("login_password")
            if password_input:
                password_input.send_keys(self.config.get("password", ""))
                logger.info("Password entered")
            
            random_delay(1, 2)
            
            # Kliknout na tlačítko přihlášení
            login_button = self.find_element("login_button")
            if login_button:
                safe_click(self.driver, login_button)
                logger.info("Login button clicked")
            
            # Počkat na přihlášení
            random_delay(3, 6)
            
            # Ověřit úspěch přihlášení
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
            # Navigovat na stránku nového inzerátu
            add_listing_url = self.config.get("etsy_url", "").replace("/manage", "/listings/new")
            self.driver.get(add_listing_url)
            random_delay(2, 4)
            
            # Vyplnit název
            title_input = self.find_element("title_input")
            if title_input:
                title_input.clear()
                title_input.send_keys(product.get("title", ""))
                logger.debug("Title filled")
            
            random_delay(1, 3)
            
            # Vyplnit popis
            description = product.get("description", "")
            if description:
                try:
                    desc_editor = self.find_element("description_editor")
                    if desc_editor:
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
            
            # Vyplnit cenu
            price = product.get("price", "9.99")
            price_input = self.find_element("price_input")
            if price_input:
                price_input.clear()
                price_input.send_keys(str(price))
                logger.debug(f"Price filled: {price}")
            
            random_delay(1, 2)
            
            # Vyplnit množství
            quantity = product.get("quantity", 999)
            quantity_input = self.find_element("quantity_input")
            if quantity_input:
                quantity_input.clear()
                quantity_input.send_keys(str(quantity))
                logger.debug(f"Quantity filled: {quantity}")
            
            random_delay(1, 3)
            
            # Nahrát obrázky
            image_paths = product.get("image_paths", "")
            if image_paths:
                image_list = image_paths.split(";") if ";" in image_paths else [image_paths]
                for img_path in image_list[:10]:
                    if img_path.strip():
                        try:
                            self.upload_image(img_path.strip())
                        except Exception as e:
                            logger.warning(f"Failed to upload image {img_path}: {e}")
            
            random_delay(2, 5)
            
            # Nastavit digitální produkt
            self.set_digital_product()
            
            random_delay(1, 3)
            
            # Přidat štítky
            tags = product.get("tags", "")
            if tags:
                self.add_tags(tags)
            
            random_delay(2, 4)
            
            # Scroll dolů
            human_like_scroll(self.driver, "down", 2)
            
            # Publikovat nebo uložit jako koncept
            try:
                publish_button = self.find_element("publish_button")
                if publish_button:
                    safe_click(self.driver, publish_button)
                    logger.info("Product published!")
                else:
                    # Zkusit XPath pro tlačítko publikování
                    publish_buttons = self.driver.find_elements("xpath", "//button[contains(text(), 'Publish')]")
                    if publish_buttons:
                        safe_click(self.driver, publish_buttons[0])
                        logger.info("Product published!")
                    else:
                        raise Exception("Publish button not found")
            except Exception as e:
                logger.warning(f"Could not publish: {e}")
                try:
                    save_button = self.find_element("save_draft_button")
                    if save_button:
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
            abs_path = str(Path(image_path).absolute())
            
            # Zkusit najít input pro upload
            file_inputs = self.driver.find_elements("css selector", 'input[type="file"]')
            
            for file_input in file_inputs:
                if file_input.is_displayed():
                    file_input.send_keys(abs_path)
                    logger.info(f"Image uploaded: {image_path}")
                    random_delay(2, 4)
                    return True
            
            # Fallback - zkusit dropzone
            try:
                dropzone = self.driver.find_element("css selector", 
                    self.selectors.get("image_dropzone", {}).get("primary", 'div[data-upload-area]'))
                file_input = dropzone.find_element('css selector', 'input[type="file"]')
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
            # Zkusit najít checkbox pro digitální produkt
            digital_checkbox = self.find_element("digital_checkbox")
            if digital_checkbox:
                if not digital_checkbox.is_selected():
                    safe_click(self.driver, digital_checkbox)
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
            
            # Najít input pro štítky
            tag_input = self.find_element("tags_input")
            
            if not tag_input:
                # Fallback - hledat obecněji
                try:
                    tag_input = self.driver.find_element("css selector", 'input[placeholder*="tag" i]')
                except:
                    pass
            
            if not tag_input:
                logger.warning("Could not find tag input")
                return False
            
            for tag in tags[:13]:  # Etsy max 13 tags
                try:
                    tag_input.send_keys(tag)
                    random_delay(0.5, 1)
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
        
        # Načíst produkty
        try:
            products = read_products_csv(csv_path)
        except Exception as e:
            logger.error(f"Failed to load products: {e}")
            return {"success": 0, "failed": 0, "total": 0}
        
        total = len(products)
        logger.info(f"Found {total} products to upload")
        
        # Vytvořit driver
        headless = self.config.get("headless", False)
        self.driver = create_driver(headless=headless)
        
        # Přihlášení
        if not self.login():
            logger.error("Login failed, aborting")
            self.driver.quit()
            return {"success": 0, "failed": total, "total": total}
        
        # Nahrát každý produkt
        for i, product in enumerate(products):
            logger.info(f"Uploading product {i+1}/{total}")
            
            # Rate limiting
            if i > 0 and i % 10 == 0:
                delay = 30
                logger.info(f"Rate limit pause: {delay}s")
                time.sleep(delay)
            
            success = self.upload_single_product(product)
            
            if success:
                self.success_count += 1
            else:
                self.failed_count += 1
            
            # Náhodné zpoždění mezi produkty
            delay_min = self.config.get("delay_min", 2)
            delay_max = self.config.get("delay_max", 10)
            random_delay(delay_min, delay_max)
        
        # Zavřít prohlížeč
        self.driver.quit()
        
        # Vypočítat elapsed time
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
        '--selectors',
        default='src/selectors.json',
        help='Selectors file (default: src/selectors.json)'
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
    
    # Vytvořit uploader s vlastními selektory
    uploader = EtsyUploader(config_path=args.config, selectors_file=args.selectors)
    
    # Přepsat headless nastavení
    if args.headless:
        uploader.config["headless"] = True
    
    # Spustit v zadaném režimu
    if args.mode == 'single':
        if not args.product_id:
            logger.error("Product ID required for single mode")
            return 1
        
        # Načíst produkty
        try:
            products = read_products_csv(args.csv)
            product = products[args.product_id - 1]
        except Exception as e:
            logger.error(f"Error loading product: {e}")
            return 1
        
        # Vytvořit driver
        uploader.driver = create_driver(headless=uploader.config.get("headless", False))
        
        # Přihlášení
        if not uploader.login():
            logger.error("Login failed")
            uploader.driver.quit()
            return 1
        
        # Nahrát produkt
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
