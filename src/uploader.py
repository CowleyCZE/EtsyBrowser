#!/usr/bin/env python3
"""Etsy Browser Bulk Uploader for StorkVisionArt.

A Selenium-based automation tool for bulk uploading digital products 
to Etsy without using the official API.

Supports dynamic selectors loaded from src/selectors.json
"""

import argparse
import json
import os
import re
import sys
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Optional

from selenium.common.exceptions import WebDriverException

from src.browser_utils import (
    create_driver,
    random_delay,
    human_like_scroll,
    safe_click,
)
from src import progress
from src.logger import setup_logger, log_error_screenshot
from src.fill_csv import read_products_csv, generate_etsy_csv

logger = setup_logger("uploader")


# Výchozí selektory - použijí se pokud selectors.json neexistuje
DEFAULT_SELECTORS = {
    "login_email": 'input[type="email"]',
    "login_password": 'input[type="password"]',
    "login_button": 'button[type="submit"]',
    "add_listing": 'a[href*="/listings/new"]',
    "title_input": '#listing-title-input, textarea[name="title"], input[name="title"]',
    "description_editor": 'textarea#listing-description-textarea, textarea[name="description"], div[data-input="description"]',
    "price_input": 'input#listing-price-input, input[name="price"]',
    "quantity_input": 'input#listing-quantity-input, input[name="quantity"]',
    "category_button": 'button[data-category]',
    "digital_checkbox": 'input[name="is_digital"]',
    "image_upload": 'input[type="file"][accept*="image"]',
    "image_dropzone": 'div[data-upload-area]',
    "tags_input": 'input#listing-tags-input, input[data-tag-input]',
    "tags_add_button": 'button#listing-tags-button',
    # :contains() neni platny CSS selektor - Selenium ho odmitne.
    # Publish/Save tlacitka resi upload_single_product primo pres XPath (//button[contains(., ...)]).
    "publish_button": "",
    "save_draft_button": "button#shop-manager--listing-save",
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
            except WebDriverException:
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
        except WebDriverException:
            pass
    
    # Zkusit fallback selektory
    for fallback in selector_data.get('fallback', []):
        try:
            return driver.find_element("css selector", fallback)
        except WebDriverException:
            continue
    
    # Zkusit výchozí selektory jako poslední zálohu
    if selector_key in DEFAULT_SELECTORS:
        try:
            return driver.find_element("css selector", DEFAULT_SELECTORS[selector_key])
        except WebDriverException:
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
            with open(config_path, 'r', encoding='utf-8') as f:
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
            "email": os.getenv("ETSY_EMAIL", ""),
            "password": os.getenv("ETSY_PASSWORD", ""),
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
        # Čekáme na element až do timeoutu (po redirectu se formulář načítá postupně)
        deadline = time.monotonic() + max(timeout, 0)
        while True:
            element = get_selector(self.driver, selector_key, self.selectors, by_type)
            if element is not None:
                try:
                    if element.is_displayed():
                        return element
                except WebDriverException:
                    pass  # stale element - zkusíme znovu
            if time.monotonic() >= deadline:
                break
            time.sleep(0.5)
        
        logger.debug(f"Element '{selector_key}' nenalezen do {timeout}s")
        
        return None
    
    def _wait_for_manual_verification(self, markers, timeout: int = 300) -> bool:
        """Čeká, až uživatel v okně prohlížeče dokončí 2FA/captchu (URL přestane obsahovat značky výzvy)."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            progress.check_cancel()
            try:
                url = self.driver.current_url.lower()
            except WebDriverException:
                return False
            if not any(marker in url for marker in markers):
                return True
            time.sleep(3)
        return False

    # --- Přihlášení (vícekrokové: cookies -> e-mail -> heslo -> kód 2FA) ---
    LOGIN_PAGE_MARKERS = ("signin", "sign-in", "login", "tfa", "challenge", "captcha", "security", "verify", "two-factor")

    def _visible(self, css_list):
        """První viditelný element z několika CSS selektorů, jinak None."""
        for css in css_list:
            try:
                for el in self.driver.find_elements("css selector", css):
                    if el.is_displayed():
                        return el
            except WebDriverException:
                continue
        return None

    def _accept_cookies(self) -> None:
        """Potíření cookies lišta (pokud je zobrazena)."""
        xpaths = [
            "//button[@data-gdpr-single-choice-accept]",
            "//button[contains(., 'Accept')]",
            "//button[contains(., 'Přijmout')]",
        ]
        for xp in xpaths:
            try:
                for el in self.driver.find_elements("xpath", xp):
                    if el.is_displayed():
                        safe_click(self.driver, el)
                        logger.info("Cookies přijaty")
                        random_delay(1, 2)
                        return
            except WebDriverException:
                continue

    def _is_logged_in(self) -> bool:
        try:
            url = self.driver.current_url.lower()
        except WebDriverException:
            return False
        return "etsy.com" in url and not any(m in url for m in self.LOGIN_PAGE_MARKERS)

    def login(self) -> bool:
        """Přihlásí se na Etsy. E-mail a heslo vyplní sám, kód 2FA/captchu zadej ručně v okně
        (okno se nezavře, dokud se přihlášení nedokončí, max. 5 minut)."""
        logger.info("Starting Etsy login...")
        email = self.config.get("email") or os.getenv("ETSY_EMAIL", "")
        password = self.config.get("password") or os.getenv("ETSY_PASSWORD", "")
        headless = bool(self.config.get("headless", False))
        timeout = 60 if headless else 300
        email_css = ['input[type="email"]', 'input[name="email"]', '#join_neu_email_field']
        pass_css = ['input[type="password"]', 'input[name="password"]', '#join_neu_password_field']
        try:
            self.driver.get(self.config.get("login_url", "https://www.etsy.com/signin"))
            random_delay(2, 4)
            deadline = time.monotonic() + timeout
            email_done = password_done = False
            manual_hint = False
            while time.monotonic() < deadline:
                progress.check_cancel()
                self._accept_cookies()
                if self._is_logged_in():
                    logger.info(f"Login successful (url: {self.driver.current_url})")
                    return True
                pass_el = self._visible(pass_css)
                email_el = self._visible(email_css)
                if pass_el is not None and not password_done and password and (email_el is None or email_done or not email):
                    pass_el.send_keys(password)
                    password_done = True
                    logger.info("Password entered")
                    random_delay(1, 2)
                    btn = self._visible(['button[type="submit"]'])
                    if btn:
                        safe_click(self.driver, btn)
                elif email_el is not None and not email_done and email:
                    email_el.send_keys(email)
                    email_done = True
                    logger.info("Email entered")
                    random_delay(1, 2)
                    if self._visible(pass_css) is None:  # dvoukrokový formulář: nejdřív Continue
                        btn = self._visible(['button[type="submit"]'])
                        if btn:
                            safe_click(self.driver, btn)
                elif (email_done or password_done) and not manual_hint:
                    if headless:
                        logger.error("Etsy vyžaduje další ověření (2FA/captcha), které v režimu bez okna nejde dokončit. Spusť upload s viditelným oknem.")
                        log_error_screenshot(self.driver, "login_2fa")
                        return False
                    logger.warning("Zadej kód 2FA / vyřeš captchu ručně v okně Chrome, čekám až 5 minut.")
                    manual_hint = True
                time.sleep(2)
            logger.error("Přihlášení nebylo dokončeno v limitu.")
            log_error_screenshot(self.driver, "login_timeout")
            return False
        except progress.Cancelled:
            raise
        except Exception as e:
            logger.error(f"Login error: {e}")
            log_error_screenshot(self.driver, "login_failed")
            return False

    def _login_legacy(self) -> bool:
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
                email_input.send_keys(
                    self.config.get("email") or os.getenv("ETSY_EMAIL", "")
                )
                logger.info("Email entered")
            
            random_delay(1, 3)
            
            # Najít a vyplnit heslo
            password_input = self.find_element("login_password")
            if password_input:
                password_input.send_keys(self.config.get("password") or os.getenv("ETSY_PASSWORD", ""))
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
            random_delay(1, 2)
            current_url = self.driver.current_url

            # 1) Detekce 2FA / captchy
            two_fa_markers = ["sign-in/tfa", "challenge", "captcha", "security-check"]
            if any(marker in current_url.lower() for marker in two_fa_markers):
                log_error_screenshot(self.driver, "login_2fa")
                if self.config.get("headless", False):
                    logger.error("Etsy vyžaduje 2FA/captchu a v režimu bez okna ji nelze vyřešit. Spusť upload s viditelným oknem.")
                    return False
                logger.warning("Etsy vyžaduje 2FA/captchu. Dokonči ověření ručně v okně Chrome, čekám až 5 minut.")
                if not self._wait_for_manual_verification(two_fa_markers):
                    logger.error("Ruční ověření nebylo dokončeno včas.")
                    return False
                logger.info("Ruční ověření dokončeno, pokračuji.")
                return True

            # 2) Je stále viditelný formulář pro přihlášení? Pak přihlášení selhalo.
            still_on_form = self.driver.find_elements("css selector", 'input[type="password"]')
            visible_form = [el for el in still_on_form if el.is_displayed()]
            if visible_form and "signin" in current_url.lower():
                logger.error("Login selhal - přihlašovací formulář je stále zobrazen (špatné údaje?).")
                log_error_screenshot(self.driver, "login_failed")
                return False

            # 3) Pozitivní kontrola: jsme na manage stránce obchodu a BEZ login formuláře
            logger.info(f"Login successful (url: {current_url})")
            return True
                
        except Exception as e:
            logger.error(f"Login error: {e}")
            log_error_screenshot(self.driver, "login_failed")
            return False
    
    def build_new_listing_url(self) -> str:
        """Sestaví adresu formuláře nového inzerátu z etsy_url (…/your/shops/<obchod>/manage)."""
        import re
        match = re.search(r"/your/shops/([^/]+)", self.config.get("etsy_url", ""))
        shop = match.group(1) if match else "me"
        shop = "me"  # alias aktuálně přihlášeného obchodu; nezávisí na případné chybě v názvu
        return f"https://www.etsy.com/your/shops/{shop}/tools/listings/create"

    def _ensure_standard_form(self) -> None:
        """Etsy nabízí průvodce "Quick list" (fotky -> Continue -> popis). Přepne na standardní formulář s poli na jedné stránce."""
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            self._accept_cookies()
            if self._visible(['#listing-title-input', 'textarea[name="title"]', 'input[name="title"]']):
                return  # už je standardní formulář
            for xp in ("//button[contains(., 'Switch to standard list')]", "//a[contains(., 'Switch to standard list')]"):
                for el in self.driver.find_elements("xpath", xp):
                    if el.is_displayed():
                        safe_click(self.driver, el)
                        logger.info("Přepnuto na standardní formulář (Switch to standard list)")
                        random_delay(3, 5)
                        for xp in ("//button[contains(., 'Discard and switch')]",):
                            time.sleep(1)
                            confirm = self._find_any([xp])
                            if confirm is not None:
                                safe_click(self.driver, confirm)
                                random_delay(2, 4)
                        return
            time.sleep(1)

    def _dump_form(self, label: str) -> None:
        """Uloží seznam prvků formuláře (id, name, placeholder, text) pro ladění selektorů do logs/."""
        script = ("return Array.from(document.querySelectorAll('input,textarea,select,button,[role=radio],[role=combobox]'))"
                  ".map(e=>({tag:e.tagName.toLowerCase(),id:e.id,name:e.getAttribute('name'),type:e.getAttribute('type'),"
                  "value:(e.getAttribute('value')||'').slice(0,40),placeholder:e.getAttribute('placeholder'),"
                  "aria:e.getAttribute('aria-label'),text:(e.innerText||'').trim().slice(0,60),visible:!!(e.offsetWidth||e.offsetHeight)}));")
        try:
            items = self.driver.execute_script(script)
            Path("logs").mkdir(exist_ok=True)
            out = Path("logs") / f"form_dump_{label}_{datetime.now():%Y%m%d_%H%M%S}.json"
            out.write_text(json.dumps({"url": self.driver.current_url, "elements": items}, indent=1, ensure_ascii=False), encoding="utf-8")
            logger.info(f"Seznam prvků formuláře uložen do {out}")
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Nepodařilo se uložit seznam prvků formuláře: {exc}")

    def upload_single_product(self, product: dict) -> bool:
        """Nahraje jeden produkt přes standardní formulář Etsy (selektory ověřené v selectors_found.json).

        Veřejný původní postup (selektory z DEFAULT_SELECTORS) zůstává jako `_upload_single_product_legacy`.
        Klíče v config.json: publish_listings (false = jen koncept, výchozí), etsy_category_inline_id
        (výchozí 6844 = Clip Art & Image Files), ai_generated (výchozí true).
        """
        title = product.get("title", "Unknown")
        logger.info(f"Uploading product: {title}")
        try:
            url = self.config.get("new_listing_url") or self.build_new_listing_url()
            logger.info(f"Otevírám formulář nového inzerátu: {url}")
            self.driver.get(url)
            random_delay(2, 4)
            if "page you were looking for was not found" in self.driver.page_source.lower()[:200000]:
                logger.error(f"Etsy vrátil 404 pro {url}.")
                log_error_screenshot(self.driver, "upload_404")
                return False
            self._ensure_standard_form()
            self._close_overlays()

            title_el = self._wait_any(self.F_TITLE, 30)
            if title_el is None:
                self._dump_form("title_missing")
                logger.error("Title input nenalezen. Produkt přeskočen.")
                log_error_screenshot(self.driver, f"upload_noform_{title}")
                return False

            # 1) Fotky
            self._upload_photos(product.get("image_paths", ""))
            # 2) Kategorie (digitální kategorie aktivuje sekci digitálních souborů a dotaz na AI)
            self._choose_category()
            # 3) Textová pole
            self._type(self._wait_any(self.F_TITLE, 10), title[:140])
            desc = re.sub(r"<[^>]+>", "", product.get("description", "") or "")
            if desc:
                self._type(self._wait_any(self.F_DESC, 5), desc)
            self._add_tags_v2(product.get("tags", ""))
            price = product.get("price") or self.config.get("prices", {}).get("single", 5.90)
            self._type(self._wait_any(self.F_PRICE, 5), str(price))
            self._type(self._wait_any(self.F_QTY, 5), str(product.get("quantity") or 999))
            # 4) Radia a výběry
            self._click_first_radio("whoMade", "#field-whoMade")
            self._click_first_radio("isSupply", "#field-isSupply")
            self._select_when_made()
            ai_value = "ai_gen" if self.config.get("ai_generated", True) else "original"
            what = self._find_any([f"input[name='whatContent'][value='{ai_value}']"], visible=False)
            if what is not None:
                self._js_click(what)
                logger.info(f"Typ obsahu: {ai_value}")
            else:
                logger.warning("Dotaz 'How is this digital content created?' nenalezen (kategorie není digitální?)")
            # 5) Digitální soubory (volitelný sloupec digital_files v CSV; pro koncept není povinný)
            self._upload_digital_files(product.get("digital_files", ""))
            human_like_scroll(self.driver, "down", 2)
            self._dump_form("before_save")  # stav formuláře (vyžadované atributy apod.) pro ladění

            # 6) Uložení konceptu / publikace
            publish = bool(self.config.get("publish_listings", False))
            if publish:
                btn = self._find_any(self.F_PUBLISH)
                if btn is None:
                    logger.error("Tlačítko Publish nenalezeno.")
                    log_error_screenshot(self.driver, f"upload_nopublish_{title}")
                    return False
                safe_click(self.driver, btn)
                random_delay(1, 2)
                confirm = self._wait_any(self.F_PUBLISH_CONFIRM, 8)
                if confirm is not None:
                    safe_click(self.driver, confirm)
            else:
                btn = self._find_any(self.F_SAVE_DRAFT)
                if btn is None:
                    logger.error("Tlačítko Save as draft nenalezeno.")
                    log_error_screenshot(self.driver, f"upload_nosave_{title}")
                    return False
                safe_click(self.driver, btn)

            if self._wait_save_result(30):
                self.last_result = "published" if publish else "saved_as_draft"
                logger.info(f"Výsledek: {self.last_result}")
                random_delay(2, 4)
                return True
            errors = [e.text.strip() for e in self.driver.find_elements("css selector", ".wt-validation__message, [role='alert']") if e.text.strip()]
            logger.error(f"Uložení nebylo potvrzeno. Chyby formuláře: {errors[:5] or 'nenalezeny'}")
            self._dump_form("after_save_failed")
            log_error_screenshot(self.driver, f"upload_savefail_{title}")
            return False
        except progress.Cancelled:
            raise
        except Exception as e:
            logger.error(f"Error uploading product: {e}")
            log_error_screenshot(self.driver, f"upload_error_{title}")
            return False

    # --- Selektory formuláře (CSS; položky začínající "//" jsou XPath) ---
    F_TITLE = ["#listing-title-input", "textarea[name='title']"]
    F_DESC = ["#listing-description-textarea", "textarea[name='description']"]
    F_PRICE = ["#listing-price-input", "input[name='variations.configuration.price']"]
    F_QTY = ["#listing-quantity-input", "input[name='quantity']"]
    F_TAGS = ["#listing-tags-input"]
    F_TAGS_ADD = ["#listing-tags-button"]
    F_PHOTO_INPUT = [".le-video-multiple-upload-area input[type='file']", "div[data-clg-id='WtUploadArea'] input[type='file']"]
    F_PHOTO_THUMB = [".le-photo-card", "[data-clg-id='WtUploadArea'] img"]
    F_DIGITAL_INPUT = ["#field-digitalFiles input[type='file']", "div[id='field-digitalFiles'] input"]
    F_DIGITAL_DONE = ["#field-digitalFiles [role='listitem']", "#field-digitalFiles div[draggable='true']"]
    F_PUBLISH = ["button[data-testid='publish']", "//div[contains(@class,'le-footer__actions')]//button[normalize-space()='Publish']"]
    F_PUBLISH_CONFIRM = ["#confirmPublishOverlay__container button#shop-manager--listing-publish",
                         "//div[@id='confirmPublishOverlay__container']//button[normalize-space()='Publish']"]
    F_SAVE_DRAFT = ["#shop-manager--listing-save", "//button[normalize-space()='Save as draft']"]

    def _find_any(self, candidates, visible: bool = True):
        """První element z kandidátů (CSS, nebo XPath začínající '//'); volitelně jen viditelný."""
        for cand in candidates:
            by = "xpath" if cand.startswith("//") else "css selector"
            try:
                for el in self.driver.find_elements(by, cand):
                    if not visible or el.is_displayed():
                        return el
            except WebDriverException:
                continue
        return None

    def _wait_any(self, candidates, timeout: float = 10, visible: bool = True):
        deadline = time.monotonic() + timeout
        while True:
            el = self._find_any(candidates, visible)
            if el is not None or time.monotonic() >= deadline:
                return el
            time.sleep(0.5)

    def _count(self, candidates) -> int:
        for cand in candidates:
            by = "xpath" if cand.startswith("//") else "css selector"
            try:
                n = len(self.driver.find_elements(by, cand))
            except WebDriverException:
                continue
            if n:
                return n
        return 0

    def _js_click(self, el) -> None:
        self.driver.execute_script("arguments[0].scrollIntoView({block:'center'}); arguments[0].click();", el)

    def _type(self, el, text: str) -> None:
        """Nahradí obsah pole (React pole nereagují na clear())."""
        if el is None:
            logger.warning("Pole formuláře nenalezeno, přeskočeno")
            return
        from selenium.webdriver.common.keys import Keys
        self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
        el.click()
        el.send_keys(Keys.CONTROL, "a")
        el.send_keys(Keys.DELETE)
        el.send_keys(text)
        random_delay(0.5, 1.5)

    def _close_overlays(self) -> None:
        for xp in ("//button[normalize-space()='Got it']",):
            el = self._find_any([xp])
            if el is not None:
                safe_click(self.driver, el)
                random_delay(0.5, 1)

    def _resolve_path(self, raw: str) -> Optional[str]:
        p = Path(raw.strip())
        for cand in (p, Path.cwd() / p, Path(__file__).resolve().parent.parent / p):
            if cand.is_file():
                return str(cand.resolve())
        logger.error(f"Soubor neexistuje: {raw}")
        return None

    def _upload_photos(self, image_paths: str) -> None:
        paths = [self._resolve_path(p) for p in (image_paths or "").split(";") if p.strip()]
        paths = [p for p in paths if p][:20]
        if not paths:
            logger.warning("Žádné existující fotky k nahrání")
            return
        for path in paths:
            inp = self._wait_any(self.F_PHOTO_INPUT, 15, visible=False)
            if inp is None:
                logger.error("Input pro fotky nenalezen")
                return
            before = self._count(self.F_PHOTO_THUMB)
            inp.send_keys(path)
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline and self._count(self.F_PHOTO_THUMB) <= before:
                time.sleep(1)
            logger.info(f"Fotka nahrána: {os.path.basename(path)}")
            random_delay(1, 2)

    def _choose_category(self) -> None:
        """Vybere kategorii podle textu (config: etsy_category_search, výchozí 'Digital Prints') a podí ni
        podtyp (etsy_category_subtype, výchozí 'Digital'). 'Clip Art & Image Files' se záměrně nepoužívá:
        vynucuje povinný atribut Craft type. Pokud je etsy_category_inline_id nastaven, použije se místo toho."""
        inline_id = str(self.config.get("etsy_category_inline_id", "") or "")
        if inline_id:
            cb = self._wait_any([f"#inline-category-{inline_id}"], 10, visible=False)
            if cb is not None and not cb.is_selected():
                self._js_click(cb)
                logger.info(f"Kategorie vybrána: inline-category-{inline_id}")
            random_delay(1, 2)
            return
        query = self.config.get("etsy_category_search", "Digital Prints")
        subtype = self.config.get("etsy_category_subtype", "Digital")
        box = self._wait_any(["#listing-editor_category-search-typeahead"], 10)
        if box is None:
            logger.error("Vyhledávání kategorie nenalezeno")
            return
        self._type(box, query)
        time.sleep(2)
        label_xp = ("//*[self::li or self::label or self::button or self::a or @role='option']"
                    f"[contains(normalize-space(.), '{query}')][not(.//li)][not(.//label)][not(.//button)]")
        item = self._wait_any([label_xp], 10)
        if item is None:
            logger.error(f"Návrh kategorie '{query}' nenalezen; vyber kategorii ručně")
            self._dump_form("category_missing")
            return
        self._js_click(item)
        logger.info(f"Kategorie vybrána: {query}")
        random_delay(2, 3)
        if subtype:
            self._choose_subtype(subtype)
        self._dump_form("after_category")
        if self._wait_any(["#field-digitalFiles"], 10, visible=False) is None:
            logger.warning("Sekce digitálních souborů se neobjevila (kategorie není digitální?)")
        random_delay(1, 2)

    def _choose_subtype(self, subtype: str) -> None:
        """Pole 'What type of item is it?' (#field-listingType): vlastní rozbalovací komponenta Etsy
        (tlačítko #category-mixed-listing-type -> ul[role=listbox] -> li[role=option]). Jako zálohu zkouší
        <select> a radio/tlačítko s textem subtype."""
        from selenium.webdriver.support.ui import Select
        trigger = self._wait_any(["#category-mixed-listing-type", "button.le-category-mixed-listing-type__trigger",
                                  "//div[@id='field-listingType']//button"], 10)
        if trigger is not None:
            self._js_click(trigger)
            option = self._wait_any([
                f"//div[@id='field-listingType']//li[@role='option'][.//p[normalize-space()='{subtype}']]",
                f"//div[@id='field-listingType']//li[@role='option'][normalize-space()='{subtype}']",
                f"//ul[@role='listbox']//li[@role='option'][normalize-space()='{subtype}']",
            ], 8)
            if option is not None:
                self._js_click(option)
                logger.info(f"Typ položky vybrán: {subtype}")
                random_delay(1, 2)
                return
            logger.warning("Seznam typů položky se otevřel, ale volba nebyla nalezena, zkouším záložní postup")
        skip = {"when-made-select", "shop-section-select"}
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            for sel in self.driver.find_elements("css selector", "select"):
                try:
                    if not sel.is_displayed() or sel.get_attribute("id") in skip:
                        continue
                    for opt in Select(sel).options:
                        if opt.text.strip().lower() == subtype.lower():
                            Select(sel).select_by_visible_text(opt.text)
                            logger.info(f"Podtyp vybrán: {opt.text}")
                            random_delay(1, 2)
                            return
                except WebDriverException:
                    continue
            el = self._find_any([f"//label[normalize-space()='{subtype}']", f"//button[normalize-space()='{subtype}']"])
            if el is not None:
                self._js_click(el)
                logger.info(f"Podtyp vybrán: {subtype}")
                random_delay(1, 2)
                return
            time.sleep(1)
        logger.warning(f"Podtyp '{subtype}' pod kategorií nenalezen; vyber ho ručně (viz form_dump_after_category)")

    def _choose_category_legacy(self) -> None:
        inline_id = str(self.config.get("etsy_category_inline_id", "6844"))
        cb = self._wait_any([f"#inline-category-{inline_id}"], 10, visible=False)
        if cb is None:
            logger.warning(f"Kategorie inline-category-{inline_id} nenalezena v návrzích; vyber kategorii ručně")
            return
        if not cb.is_selected():
            self._js_click(cb)
        logger.info(f"Kategorie vybrána: inline-category-{inline_id}")
        if self._wait_any(["#field-digitalFiles"], 15, visible=False) is None:
            logger.warning("Sekce digitálních souborů se neobjevila (kategorie není digitální?)")
        random_delay(1, 2)

    def _add_tags_v2(self, tags_string: str) -> None:
        seen, tags = set(), []
        for t in (tags_string or "").split(","):
            t = " ".join(t.split())
            if t and len(t) <= 20 and t.lower() not in seen:
                seen.add(t.lower())
                tags.append(t)
        inp = self._wait_any(self.F_TAGS, 5)
        if inp is None:
            logger.warning("Pole pro štítky nenalezeno")
            return
        from selenium.webdriver.common.keys import Keys
        for tag in tags[:13]:
            # Dolní lišta (Save as draft) zakrývá pole, proto nejdřív vycentrovat a kliknout přes JS
            inp = self._find_any(self.F_TAGS) or inp
            self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", inp)
            time.sleep(0.3)
            try:
                inp.click()
            except WebDriverException:
                self.driver.execute_script("arguments[0].focus();", inp)
            inp.send_keys(tag)
            add = self._find_any(self.F_TAGS_ADD)
            if add is not None:
                self._js_click(add)
            else:
                inp.send_keys(Keys.ENTER)
            random_delay(0.4, 0.9)
        logger.info(f"Štítky přidány: {len(tags[:13])}")

    def _click_first_radio(self, name: str, container: str) -> None:
        radios = self.driver.find_elements("css selector", f"{container} input[name='{name}']") or \
            self.driver.find_elements("css selector", f"input[name='{name}']")
        if radios:
            self._js_click(radios[0])
            logger.info(f"Radio {name}: první volba")
        else:
            logger.warning(f"Radio {name} nenalezeno")

    def _select_when_made(self) -> None:
        from selenium.webdriver.support.ui import Select
        sel = self._find_any(["#when-made-select"])
        if sel is None:
            return
        try:
            Select(sel).select_by_visible_text("2020 - 2026")
            logger.info("When made: 2020 - 2026")
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"When made nelze nastavit: {exc}")

    def _upload_digital_files(self, files: str) -> None:
        paths = [self._resolve_path(p) for p in (files or "").split(";") if p.strip()]
        paths = [p for p in paths if p][:5]
        if not paths:
            logger.warning("CSV nemá sloupec digital_files (nebo soubory chybí); digitální soubory se nenahrávají, publikace bez nich nepročte")
            return
        for path in paths:
            inp = self._wait_any(self.F_DIGITAL_INPUT, 10, visible=False)
            if inp is None:
                logger.error("Input pro digitální soubory nenalezen")
                return
            before = self._count(self.F_DIGITAL_DONE)
            inp.send_keys(path)
            deadline = time.monotonic() + 180
            while time.monotonic() < deadline and self._count(self.F_DIGITAL_DONE) <= before:
                progress.check_cancel()
                time.sleep(2)
            logger.info(f"Digitální soubor nahrán: {os.path.basename(path)}")

    def _wait_save_result(self, timeout: float) -> bool:
        """Čeká na potvrzení uložení: změna URL z /create na /edit/<id> nebo seznam inzerátů, nebo toast."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            progress.check_cancel()
            skip = self._find_any(["//button[normalize-space()='Skip and continue']"])
            if skip is not None:
                safe_click(self.driver, skip)
            url = self.driver.current_url.lower()
            if "/listing-editor/edit" in url or ("/listings" in url and "/create" not in url):
                return True
            if self._find_any([".wt-toast--success", "//div[contains(@class,'wt-toast') and contains(.,'saved')]"]):
                return True
            time.sleep(1)
        return False

    def _upload_single_product_legacy(self, product: dict) -> bool:
        """Upload a single product to Etsy.
        
        Args:
            product: Product dictionary with listing data
            
        Returns:
            True if upload successful, False otherwise
        """
        logger.info(f"Uploading product: {product.get('title', 'Unknown')}")
        
        try:
            # Navigovat na stránku nového inzerátu. Etsy nemá /listings/new (vrací 404 "Uh oh!");
            # aktuální adresa je /your/shops/<obchod>/tools/listings/create. Jde přepsat klíčem
            # "new_listing_url" v config.json.
            add_listing_url = self.config.get("new_listing_url") or self.build_new_listing_url()
            logger.info(f"Otevírám formulář nového inzerátu: {add_listing_url}")
            self.driver.get(add_listing_url)
            random_delay(2, 4)
            page_text = (self.driver.title or "").lower()
            if "page you were looking for was not found" in self.driver.page_source.lower()[:200000] or "not found" in page_text:
                logger.error(f"Etsy vrátil 404 pro {add_listing_url}. Nastav správnou adresu v config.json (new_listing_url).")
                log_error_screenshot(self.driver, "upload_404")
                return False
            self._ensure_standard_form()
            
            # Vyplnit název
            title_input = self.find_element("title_input", timeout=20)
            if not title_input:
                self._dump_form("title_missing")
                logger.error("Title input nenalezen - formular Etsy se neotešel správně. Produkt přeskočen.")
                log_error_screenshot(self.driver, f"upload_noform_{product.get('title', 'unknown')}")
                return False
            title_input.clear()
            title_input.send_keys(product.get("title", ""))
            logger.debug("Title filled")
            
            random_delay(1, 3)
            
            # Vyplnit popis
            description = product.get("description", "")
            if description:
                try:
                    desc_editor = self.find_element("description_editor", timeout=3)
                    if desc_editor:
                        desc_editor.click()
                        random_delay(0.5, 1)
                        if desc_editor.tag_name.lower() == "textarea":
                            import re as _re
                            plain = _re.sub(r"<[^>]+>", "", description)  # textarea nepodporuje HTML
                            desc_editor.clear()
                            desc_editor.send_keys(plain)
                        else:
                            self.driver.execute_script(
                                "arguments[0].innerHTML = arguments[1];",
                                desc_editor,
                                description,
                            )
                        logger.debug("Description filled")
                except Exception as e:
                    logger.warning(f"Could not fill description: {e}")
            
            random_delay(1, 3)
            
            # Vyplnit cenu (fallback: config.json -> prices.single, jinak jednotný default 5.90)
            price = product.get("price") or self.config.get("prices", {}).get("single", 5.90)
            price_input = self.find_element("price_input", timeout=3)
            if price_input:
                price_input.clear()
                price_input.send_keys(str(price))
                logger.debug(f"Price filled: {price}")
            
            random_delay(1, 2)
            
            # Vyplnit množství
            quantity = product.get("quantity", 999)
            quantity_input = self.find_element("quantity_input", timeout=3)
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
            published = False
            saved_as_draft = False
            try:
                publish_button = self.find_element("publish_button", timeout=3)
                if publish_button:
                    safe_click(self.driver, publish_button)
                    published = True
                    logger.info("Product published!")
                else:
                    # Zkusit XPath pro tlačítko publikování
                    publish_buttons = self.driver.find_elements("xpath", "//button[contains(text(), 'Publish')]")
                    if publish_buttons:
                        safe_click(self.driver, publish_buttons[0])
                        published = True
                        logger.info("Product published!")
                    else:
                        raise Exception("Publish button not found")
            except Exception as e:
                logger.warning(f"Could not publish: {e}")
                try:
                    save_button = self.find_element("save_draft_button", timeout=3)
                    if not save_button:
                        xpath_buttons = self.driver.find_elements(
                            "xpath",
                            "//button[contains(., 'Save as draft') or contains(., 'Save draft')]",
                        )
                        save_button = xpath_buttons[0] if xpath_buttons else None
                    if save_button:
                        safe_click(self.driver, save_button)
                        saved_as_draft = True
                        logger.info("Product saved as draft")
                except Exception as exc:
                    logger.warning(f"Could not find publish/save-draft button: {exc}")

            if not published and not saved_as_draft:
                logger.error("Produkt nebyl publikován ani uložen jako koncept - počítám jako FAIL.")
                log_error_screenshot(self.driver, f"upload_nopublish_{product.get('title', 'unknown')}")
                random_delay(2, 4)
                return False
            
            self.last_result = "published" if published else "saved_as_draft"
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
            
            if not os.path.exists(abs_path):
                logger.error(f"Obrázek neexistuje na disku: {abs_path}")
                return False
            
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
            except WebDriverException as exc:
                logger.debug(f"Dropzone fallback selhal: {exc}")
            
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
            digital_checkbox = self.find_element("digital_checkbox", timeout=3)
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
            tag_input = self.find_element("tags_input", timeout=3)
            
            if not tag_input:
                # Fallback - hledat obecněji
                try:
                    tag_input = self.driver.find_element("css selector", 'input[placeholder*="tag" i]')
                except WebDriverException:
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
        
        # Rate limiting: sliding window podle max_products_per_hour z configu
        max_per_hour = int(self.config.get("max_products_per_hour", 0) or 0)
        window = deque()  # časy upload pokusů za poslední hodinu

        # Nahrát každý produkt
        for i, product in enumerate(products):
            progress.check_cancel()
            progress.report(100.0 * i / max(total, 1),
                            f"Produkt {i+1}/{total}: {(product.get('title') or '')[:60]}")
            logger.info(f"Uploading product {i+1}/{total}")

            # Rate limiting
            if max_per_hour > 0:
                now_ts = time.time()
                while window and now_ts - window[0] >= 3600:
                    window.popleft()
                if len(window) >= max_per_hour:
                    wait_s = max(5.0, 3600 - (time.time() - window[0]) + 5)
                    logger.info(
                        f"Rate limit: dosaženo {max_per_hour} produktů/hod, "
                        f"čekám {wait_s:.0f}s (v okně zbývá 0, ve frontě {total - i})"
                    )
                    deadline = time.monotonic() + wait_s
                    while time.monotonic() < deadline:
                        progress.check_cancel()
                        time.sleep(min(5.0, max(0.0, deadline - time.monotonic())))
                    now_ts = time.time()
                    while window and now_ts - window[0] >= 3600:
                        window.popleft()

            success = self.upload_single_product(product)
            
            if success:
                self.success_count += 1
            else:
                self.failed_count += 1
            if max_per_hour > 0:
                window.append(time.time())
            
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

