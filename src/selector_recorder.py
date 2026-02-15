#!/usr/bin/env python3
"""Selector Recorder - Interaktivní nástroj pro zaznamenávání CSS selektorů z Etsy.

Umožňuje automatickou i interaktivní detekci elementů na stránce Etsy
pro hromadné nahrávání produktů bez použití API.

Použití:
    python src/selector_recorder.py --url "URL" --mode auto|interactive|both
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

# Přidat src do cesty pro import
sys.path.insert(0, str(Path(__file__).parent.parent))

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium_stealth import stealth

from src.logger import setup_logger

logger = setup_logger("selector_recorder")


# Definice běžných Etsy elementů s více možnostmi hledání
COMMON_ETSY_ELEMENTS = {
    "login_email": [
        'input[type="email"]',
        'input[id="email"]',
        'input[name="email"]',
        'input[placeholder*="email" i]',
    ],
    "login_password": [
        'input[type="password"]',
        'input[id="password"]',
        'input[name="password"]',
    ],
    "login_button": [
        'button[type="submit"]',
        'button[data-testid="submit-button"]',
        'button:contains("Sign in")',
    ],
    "add_listing": [
        'a[href*="/listings/new"]',
        'button:contains("Add a listing")',
        'a[data-testid="add-listing"]',
    ],
    "title_input": [
        'input[name="title"]',
        'input[placeholder*="title" i]',
        'input[id*="title" i]',
        'input[data-testid*="title" i]',
        'input[aria-label*="title" i]',
    ],
    "description_editor": [
        'div[contenteditable="true"]',
        'div[data-input="description"]',
        'div[data-testid="description"]',
        'div[aria-label*="Description"]',
        'textarea[name="description"]',
        'div.ck-editor__editable',
    ],
    "price_input": [
        'input[name="price"]',
        'input[placeholder*="price" i]',
        'input[id*="price" i]',
        'input[data-testid*="price" i]',
        'input[aria-label*="price" i]',
    ],
    "quantity_input": [
        'input[name="quantity"]',
        'input[id*="quantity" i]',
        'input[data-testid*="quantity" i]',
    ],
    "image_upload": [
        'input[type="file"][accept*="image"]',
        'input[data-testid="image-upload"]',
        'input[name="images"]',
    ],
    "image_dropzone": [
        'div[data-upload-area]',
        'div[data-testid="image-dropzone"]',
        'div[class*="upload"]',
    ],
    "tags_input": [
        'input[data-tag-input]',
        'input[placeholder*="tag" i]',
        'input[name="tags"]',
        'input[data-testid="tags"]',
    ],
    "digital_checkbox": [
        'input[name="is_digital"]',
        'input[type="checkbox"][value="digital"]',
        'label:contains("Digital")',
    ],
    "category_button": [
        'button[data-category]',
        'button:contains("Category")',
        'button[data-testid="category"]',
    ],
    "publish_button": [
        'button:contains("Publish")',
        'button[data-testid="publish"]',
        'button[type="submit"]:contains("Publish")',
    ],
    "save_draft_button": [
        'button:contains("Save draft")',
        'button[data-testid="save-draft"]',
        'button:contains("Save as draft")',
    ],
    "shop_section_select": [
        'select[name="shop_section_id"]',
        'select[data-testid="shop-section"]',
    ],
}


def create_driver(headless: bool = False, user_data_dir: Optional[str] = None) -> webdriver.Chrome:
    """Vytvoří Chrome WebDriver se stealth nastavením.
    
    Args:
        headless: Spustit prohlížeč bez GUI
        user_data_dir: Cesta k profilu prohlížeče (pro přihlášení)
        
    Returns:
        Nakonfigurovaný Chrome WebDriver
    """
    options = Options()
    
    if headless:
        options.add_argument("--headless=new")
    
    # Důležité option pro stealth
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    
    # User agent
    user_agent = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
    options.add_argument(f"user-agent={user_agent}")
    
    # Použít existující profil pokud je zadán
    if user_data_dir:
        options.add_argument(f"--user-data-dir={user_data_dir}")
    
    # Vytvořit driver
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    
    # Aplikovat selenium-stealth
    stealth(
        driver,
        languages=["en-US", "en"],
        vendor="Google Inc.",
        platform="Win32",
        webgl_vendor="Intel Inc.",
        renderer="Intel Iris OpenGL Engine",
        fix_hairline=True,
    )
    
    logger.info("Chrome driver vytvořen")
    return driver


def generate_css_selectors(element) -> list:
    """Generuje seznam možných CSS selektorů pro element.
    
    Args:
        element: Selenium WebElement
        
    Returns:
        Seznam možných CSS selektorů seřazených od nejspolehlivějšího
    """
    selectors = []
    tag_name = element.tag_name
    element_id = element.get_attribute("id")
    element_name = element.get_attribute("name")
    element_class = element.get_attribute("class")
    placeholder = element.get_attribute("placeholder")
    aria_label = element.get_attribute("aria-label")
    data_testid = element.get_attribute("data-testid")
    data_input = element.get_attribute("data-input")
    type_attr = element.get_attribute("type")
    
    # 1. ID (nejvyšší priorita)
    if element_id:
        selectors.append(f"#{element_id}")
    
    # 2. Name atribut
    if element_name:
        selectors.append(f'{tag_name}[name="{element_name}"]')
    
    # 3. Data-testid
    if data_testid:
        selectors.append(f'{tag_name}[data-testid="{data_testid}"]')
    
    # 4. Data-input
    if data_input:
        selectors.append(f'{tag_name}[data-input="{data_input}"]')
    
    # 5. Type atribut (pro input prvky)
    if type_attr and tag_name == "input":
        selectors.append(f'input[type="{type_attr}"]')
    
    # 6. Placeholder (case insensitive)
    if placeholder:
        selectors.append(f'{tag_name}[placeholder*="{placeholder}" i]')
    
    # 7. Aria-label (case insensitive)
    if aria_label:
        selectors.append(f'{tag_name}[aria-label*="{aria_label}" i]')
    
    # 8. Class (jen první třídu)
    if element_class:
        first_class = element_class.split()[0] if element_class else None
        if first_class:
            selectors.append(f'.{first_class}')
    
    return selectors


def generate_xpath(element) -> str:
    """Generuje XPath pro element.
    
    Args:
        element: Selenium WebElement
        
    Returns:
        Relativní XPath řetězec
    """
    # Zkusit atributy
    element_id = element.get_attribute("id")
    element_name = element.get_attribute("name")
    element_class = element.get_attribute("class")
    placeholder = element.get_attribute("placeholder")
    aria_label = element.get_attribute("aria-label")
    
    if element_id:
        return f'//*[@id="{element_id}"]'
    
    if element_name:
        return f'//*[@name="{element_name}"]'
    
    if placeholder:
        return f'//*[contains(@placeholder, "{placeholder}")]'
    
    if aria_label:
        return f'//*[contains(@aria-label, "{aria_label}")]'
    
    if element_class:
        first_class = element_class.split()[0]
        return f'//*[contains(@class, "{first_class}")]'
    
    # Fallback - relativní cesta
    tag = element.tag_name
    return f'//{tag}'


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
        except:
            continue
    return None


class SelectorRecorder:
    """Třída pro zaznamenávání selektorů z Etsy stránek."""
    
    def __init__(self, url: str, headless: bool = False, user_data_dir: Optional[str] = None):
        """Inicializuje recorder.
        
        Args:
            url: Cílová URL
            headless: Spustit bez GUI
            user_data_dir: Cesta k profilu prohlížeče
        """
        self.url = url
        self.headless = headless
        self.user_data_dir = user_data_dir
        self.driver = None
        self.selectors = {}  # Zaznamenané selektory
        self.interactive_mappings = {}  # Mapování typu -> zaznamenaný selektor
        
    def start(self):
        """Spustí recorder a driver."""
        self.driver = create_driver(self.headless, self.user_data_dir)
        self.driver.get(self.url)
        logger.info(f"Otevřeno: {self.url}")
        time.sleep(2)
        
    def stop(self):
        """Zavře recorder a driver."""
        if self.driver:
            self.driver.quit()
            
    def save_selectors(self, output_path: str = "src/selectors.json"):
        """Uloží zaznamenané selektory do JSON souboru.
        
        Args:
            output_path: Cesta k výstupnímu souboru
        """
        # Převést na správný formát
        output_data = {}
        for key, value in self.selectors.items():
            if isinstance(value, dict):
                output_data[key] = value
            else:
                output_data[key] = {
                    "primary": value,
                    "fallback": [],
                    "xpath": ""
                }
        
        # Uložit
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Selektory uloženy do: {output_path}")
        
    def run_auto_mode(self) -> dict:
        """Spustí automatický režim - skenuje stránku pro běžné elementy.
        
        Returns:
            Slovník nalezených/ nenalezených elementů
        """
        logger.info("=" * 50)
        logger.info("AUTO MODE - Automatická detekce elementů")
        logger.info("=" * 50)
        
        results = {
            "found": [],
            "not_found": []
        }
        
        for element_name, possible_selectors in COMMON_ETSY_ELEMENTS.items():
            logger.info(f"Hledám: {element_name}")
            
            element = find_element_by_any_selector(self.driver, possible_selectors)
            
            if element:
                # Generovat všechny možné selektory
                all_selectors = generate_css_selectors(element)
                xpath = generate_xpath(element)
                
                # Najít úspěšný selektor
                primary = None
                for sel in possible_selectors:
                    try:
                        self.driver.find_element(By.CSS_SELECTOR, sel)
                        primary = sel
                        break
                    except:
                        continue
                
                self.selectors[element_name] = {
                    "primary": primary or all_selectors[0] if all_selectors else "",
                    "fallback": [s for s in all_selectors if s != primary],
                    "xpath": xpath,
                    "tag": element.tag_name,
                    "text": element.get_attribute("innerText")[:50] if element.get_attribute("innerText") else ""
                }
                
                results["found"].append(element_name)
                logger.info(f"  ✓ NALEZEN: {primary}")
            else:
                results["not_found"].append(element_name)
                logger.warning(f"  ✗ NENALEZEN")
                
            time.sleep(0.5)
        
        logger.info("=" * 50)
        logger.info(f"AUTO MODE DOKONČEN")
        logger.info(f"Nalezeno: {len(results['found'])}/{len(COMMON_ETSY_ELEMENTS)}")
        logger.info("=" * 50)
        
        return results
    
    def run_interactive_mode(self):
        """Spustí interaktivní režim - uživatel kliká na elementy."""
        logger.info("=" * 50)
        logger.info("INTERAKTIVNÍ REŽIM")
        logger.info("=" * 50)
        
        print_instructions()
        
        # Přidat JavaScript listener pro sledování kliknutí
        self.setup_click_listener()
        
        # Seznam typů elementů pro rychlou volbu
        element_types = list(COMMON_ETSY_ELEMENTS.keys())
        
        # Hlavní smyčka
        running = True
        while running:
            print("\n" + "=" * 50)
            print("AKTUÁLNÍ STAV:")
            for key, val in self.selectors.items():
                if isinstance(val, dict):
                    print(f"  [{key}]: {val.get('primary', 'N/A')[:40]}")
                else:
                    print(f"  [{key}]: {val[:40]}")
            print("=" * 50)
            
            print("\nMožnosti:")
            print("  [1-9,0] - Zaznamenat jako konkrétní typ")
            print("  [a-z]   - Zaznamenat jako vlastní název")
            print("  [Enter] - Zaznamenat jako další volný typ")
            print("  [l]     - List dostupných typů")
            print("  [d]     - Smazat poslední záznam")
            print("  [s]     - Uložit a ukončit")
            print("  [q]     - Ukončit bez uložení")
            print("  [h]     - Nápověda")
            print("\nStiskněte klávesu...")
            
            try:
                key = input("\n> ").strip().lower()
            except (KeyboardInterrupt, EOFError):
                key = 'q'
            
            if key == 'q':
                running = False
                print("Ukončeno bez uložení.")
                
            elif key == 's':
                self.save_selectors()
                running = False
                print("Selektory uloženy!")
                
            elif key == 'h':
                print_instructions()
                
            elif key == 'l':
                print("\n dostupné typy elementů:")
                for i, etype in enumerate(element_types):
                    status = "✓" if etype in self.selectors else " "
                    print(f"  {i+1:2}. [{status}] {etype}")
                    
            elif key == 'd':
                if self.selectors:
                    last_key = list(self.selectors.keys())[-1]
                    del self.selectors[last_key]
                    print(f"Smazáno: {last_key}")
                else:
                    print("Nic ke smazání.")
                    
            elif key in ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0']:
                idx = int(key) - 1 if key != '0' else 9
                if idx < len(element_types):
                    element_type = element_types[idx]
                    self.record_current_element(element_type)
                    
            elif len(key) == 1 and key.isalpha():
                # Zaznamenat jako vlastní název
                self.record_current_element(key)
                
            elif key == '':
                # Najít první volný typ
                for etype in element_types:
                    if etype not in self.selectors:
                        self.record_current_element(etype)
                        break
                else:
                    print("Všechny typy jsou již zaznamenány!")
            else:
                print(f"Neznámý příkaz: {key}")
    
    def setup_click_listener(self):
        """Nastaví JavaScript listener pro sledování kliknutí."""
        script = """
        window.__lastClickedElement = null;
        
        document.addEventListener('click', function(e) {
            window.__lastClickedElement = {
                tagName: e.target.tagName,
                id: e.target.id,
                className: e.target.className,
                name: e.target.getAttribute('name'),
                placeholder: e.target.getAttribute('placeholder'),
                ariaLabel: e.target.getAttribute('aria-label'),
                dataTestid: e.target.getAttribute('data-testid'),
                dataInput: e.target.getAttribute('data-input'),
                type: e.target.getAttribute('type'),
                innerText: e.target.innerText ? e.target.innerText.substring(0, 100) : ''
            };
            
            // Přidat vizuální indikátor
            e.target.style.outline = '3px solid #ff0000';
            e.target.style.outlineOffset = '2px';
            
            setTimeout(function() {
                e.target.style.outline = '';
            }, 3000);
        }, true);
        """
        self.driver.execute_script(script)
        
    def record_current_element(self, element_type: str):
        """Zaznamená aktuálně kliknutý element jako specifický typ."""
        try:
            # Získat data z JavaScript listeneru
            element_data = self.driver.execute_script("return window.__lastClickedElement;")
            
            if not element_data:
                print("⚠ Nekliknuto na žádný element! Nejprve klikněte na element na stránce.")
                return
            
            # Najít element
            if element_data.get('id'):
                selector = f"#{element_data['id']}"
            elif element_data.get('name'):
                selector = f"{element_data['tagName'].lower()}[name=\"{element_data['name']}\"]"
            elif element_data.get('dataTestid'):
                selector = f"{element_data['tagName'].lower()}[data-testid=\"{element_data['dataTestid']}\"]"
            elif element_data.get('dataInput'):
                selector = f"{element_data['tagName'].lower()}[data-input=\"{element_data['dataInput']}\"]"
            elif element_data.get('placeholder'):
                selector = f"{element_data['tagName'].lower()}[placeholder*=\"{element_data['placeholder']}\" i]"
            else:
                # Fallback - použít tag
                selector = f"{element_data['tagName'].lower()}"
            
            # Generovat fallback selektory
            all_selectors = []
            if element_data.get('id'):
                all_selectors.append(f"#{element_data['id']}")
            if element_data.get('name'):
                all_selectors.append(f"{element_data['tagName'].lower()}[name=\"{element_data['name']}\"]")
            if element_data.get('dataTestid'):
                all_selectors.append(f"{element_data['tagName'].lower()}[data-testid=\"{element_data['dataTestid']}\"]")
            if element_data.get('placeholder'):
                all_selectors.append(f"{element_data['tagName'].lower()}[placeholder*=\"{element_data['placeholder']}\" i]")
            if element_data.get('ariaLabel'):
                all_selectors.append(f"{element_data['tagName'].lower()}[aria-label*=\"{element_data['ariaLabel']}\" i]")
                
            # XPath
            xpath = generate_xpath_from_data(element_data)
            
            # Uložit
            self.selectors[element_type] = {
                "primary": selector,
                "fallback": [s for s in all_selectors if s != selector],
                "xpath": xpath,
                "tag": element_data.get('tagName', ''),
                "text": element_data.get('innerText', '')[:50]
            }
            
            print(f"✓ Zaznamenáno: {element_type}")
            print(f"  Primary: {selector}")
            print(f"  Tag: {element_data.get('tagName')}")
            print(f"  Text: {element_data.get('innerText', '')[:30]}")
            
        except Exception as e:
            print(f"⚠ Chyba při zaznamenávání: {e}")
            
    def run(self, mode: str = "both"):
        """Spustí recorder v zadaném režimu.
        
        Args:
            mode: 'auto', 'interactive' nebo 'both'
        """
        self.start()
        
        if mode in ['auto', 'both']:
            # Nejprve zkusit auto mode
            self.run_auto_mode()
            
        if mode in ['interactive', 'both']:
            # Pak interaktivní mode
            self.run_interactive_mode()
        
        self.stop()


def generate_xpath_from_data(element_data: dict) -> str:
    """Generuje XPath z dat elementu.
    
    Args:
        element_data: Slovník s daty elementu
        
    Returns:
        XPath řetězec
    """
    tag = element_data.get('tagName', '').lower()
    
    if element_data.get('id'):
        return f'//*[@id="{element_data["id"]}"]'
    
    if element_data.get('name'):
        return f'//{tag}[@name="{element_data["name"]}"]'
    
    if element_data.get('dataTestid'):
        return f'//{tag}[@data-testid="{element_data["dataTestid"]}"]'
    
    if element_data.get('placeholder'):
        return f'//{tag}[contains(@placeholder, "{element_data["placeholder"]}")]'
    
    if element_data.get('ariaLabel'):
        return f'//{tag}[contains(@aria-label, "{element_data["ariaLabel"]}")]'
    
    return f'//{tag}'


def print_instructions():
    """Vytiskne instrukce pro interaktivní režim."""
    print("""
╔══════════════════════════════════════════════════════════════════╗
║              INTERAKTIVNÍ REŽIM - INSTRUKCE                     ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  1. OTEVŘETE PROHLÍŽEČ - měli byste vidět Etsy stránku         ║
║                                                                  ║
║  2. KIKNĚTE NA POŽADOVANÝ ELEMENT na stránce                    ║
║     (např. pole pro název produktu)                             ║
║                                                                  ║
║  3. ZADEJTE TYP ELEMENTU:                                       ║
║     [1] title_input       - Název produktu                      ║
║     [2] description_editor - Editor popisu                      ║
║     [3] price_input      - Cena                                  ║
║     [4] quantity_input   - Množství                             ║
║     [5] image_upload    - Upload obrázků                       ║
║     [6] tags_input       - Štítky                               ║
║     [7] digital_checkbox - Digitální produkt                    ║
║     [8] category_button  - Kategorie                            ║
║     [9] publish_button   - Publikovat                          ║
║     [0] save_draft_button - Uložit jako koncept                ║
║                                                                  ║
║     Nebo zadejte vlastní název (např. "moje_pole")             ║
║                                                                  ║
║  4. OPAKUJTE pro všechny potřebné elementy                     ║
║                                                                  ║
║  5. STISKNĚTE [s] pro uložení a ukončení                       ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
""")


def main():
    """Hlavní vstupní bod."""
    parser = argparse.ArgumentParser(
        description="Selector Recorder - Nástroj pro zaznamenávání Etsy selektorů",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Příklady použití:

  # Automatický režim
  python src/selector_recorder.py --url "https://www.etsy.com/your/shops/MujObchod/manage" --mode auto

  # Interaktivní režim
  python src/selector_recorder.py --url "https://www.etsy.com/your/shops/MujObchod/manage/listings/new" --mode interactive

  # Oba režimy
  python src/selector_recorder.py --url "URL" --mode both --headless

  # S použitím existujícího profilu prohlížeče (pro přihlášení)
  python src/selector_recorder.py --url "URL" --user-data-dir "C:/Users/AppData/Local/Google/Chrome/User Data"
        """
    )
    
    parser.add_argument(
        '--url', '-u',
        required=True,
        help='Cílová URL adresa Etsy'
    )
    
    parser.add_argument(
        '--mode', '-m',
        choices=['auto', 'interactive', 'both'],
        default='both',
        help='Režim: auto (automatický), interactive (interaktivní), both (oba)'
    )
    
    parser.add_argument(
        '--headless',
        action='store_true',
        help='Spustit prohlížeč bez GUI'
    )
    
    parser.add_argument(
        '--user-data-dir',
        help='Cesta k profilu Chrome (pro zachování přihlášení)'
    )
    
    parser.add_argument(
        '--output', '-o',
        default='src/selectors.json',
        help='Výstupní soubor pro selektory'
    )
    
    args = parser.parse_args()
    
    # Spustit recorder
    recorder = SelectorRecorder(
        url=args.url,
        headless=args.headless,
        user_data_dir=args.user_data_dir
    )
    
    try:
        recorder.run(args.mode)
    except KeyboardInterrupt:
        print("\n\nUkončeno uživatelem.")
    except Exception as e:
        logger.error(f"Chyba: {e}")
        import traceback
        traceback.print_exc()
    finally:
        recorder.stop()


if __name__ == "__main__":
    main()
