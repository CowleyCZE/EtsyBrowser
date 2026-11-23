import os
import time
import random
import requests
import urllib.parse
import json
import re
import subprocess
import sys
from groq import Groq
from PIL import Image, ImageOps, ImageFilter, ImageEnhance
from datetime import datetime
import io
import numpy as np
from dotenv import load_dotenv

import http.server
import socketserver
import webbrowser
import zipfile
import contextlib

# Načtení environment proměnných (očekává POLLINATIONS_API_KEY, GROQ_API_KEY, ...)
load_dotenv()

# Import modulu Etsy a enumu (robustně nezávisle na pracovním adresáři)
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
for _p in (_THIS_DIR, os.path.dirname(_THIS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    from etsy_api import EtsyClient
except ImportError:
    try:
        from automation.etsy_api import EtsyClient
    except ImportError:
        EtsyClient = None

from src.etsy_enums import WhoMade, WhenMade, ListingType, ListingState, AI_DISCLOSURE_TEXT
from src.progress import Cancelled, check_cancel, report  # průběh/rušení úloh (mimo GUI fronta nic nedělají)

# --- 1. KONFIGURACE ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY") 
GEMINI_GEN_API_KEY = os.getenv("GEMINI_GEN_API_KEY")

# Etsy konfigurace (tokeny řeší EtsyClient.from_env() z oauth/etsy_tokens.json)
ETSY_API_KEY = os.getenv("ETSY_API_KEY")
ETSY_SHOP_ID = os.getenv("ETSY_SHOP_ID")

# Cesty musí být definované PŘED načtením configu (jinak NameError při importu)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)        # .../EtsyBrowser/
DATA_DIR = os.path.join(PROJECT_ROOT, "data")

# --- CENY: jednotný zdroj pravdy (config.json -> sekce "prices") ---
def _load_project_config() -> dict:
    """Načte kořenový config.json (nebo data/config.json) jako jednotný zdroj nastavení."""
    for path in [os.path.join(PROJECT_ROOT, "config.json"), os.path.join(DATA_DIR, "config.json")]:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            continue
    return {}

_PROJECT_CONFIG = _load_project_config()
DEFAULT_PRICE_SINGLE = float(_PROJECT_CONFIG.get("prices", {}).get("single", 5.90))
DEFAULT_PRICE_BUNDLE = float(_PROJECT_CONFIG.get("prices", {}).get("bundle", 9.90))
MAX_ZIP_BYTES = 19.5 * 1024 * 1024  # rezerva pod limitem Etsy 20 MB na soubor

# --- GROQ: model, timeout a retry z config.json (sekce "groq") ---
_GROQ_CONFIG = _PROJECT_CONFIG.get("groq", {})
GROQ_MODEL = _GROQ_CONFIG.get("model", "openai/gpt-oss-120b")
GROQ_TIMEOUT = float(_GROQ_CONFIG.get("timeout", 60))
GROQ_MAX_RETRIES = int(_GROQ_CONFIG.get("max_retries", 3))


def make_groq_client():
    """Vytvoří Groq klienta s timeoutem a automatickým retry (backoff řeší SDK)."""
    if not GROQ_API_KEY:
        raise RuntimeError("Chybí GROQ_API_KEY v .env souboru.")
    return Groq(api_key=GROQ_API_KEY, timeout=GROQ_TIMEOUT, max_retries=GROQ_MAX_RETRIES)


# Groq vyřadil llama-3.3-70b-versatile (16. 8. 2026); náhradní modely se zkouší, když ten z configu neexistuje
GROQ_FALLBACK_MODELS = ("openai/gpt-oss-120b", "qwen/qwen3.6-27b", "openai/gpt-oss-20b")


def _is_model_missing(exc) -> bool:
    text = str(exc).lower()
    return getattr(exc, "status_code", None) == 404 or "model_not_found" in text or "decommissioned" in text


def groq_complete(client, prompt: str) -> str:
    """Jedno chat volání Groq; když model z configu neexistuje, zkusí náhradní a zapamatuje si fungující."""
    global GROQ_MODEL
    candidates = [GROQ_MODEL] + [m for m in GROQ_FALLBACK_MODELS if m != GROQ_MODEL]
    last_error = None
    for model in candidates:
        try:
            completion = client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=model,
            )
        except Exception as e:  # noqa: BLE001
            if _is_model_missing(e):
                print(f"   ⚠️ Groq model '{model}' není dostupný, zkouším další. Nastav fungující v config.json → groq.model.")
                last_error = e
                continue
            raise
        if model != GROQ_MODEL:
            print(f"   ℹ️ Použitý náhradní Groq model: {model}")
            GROQ_MODEL = model
        return completion.choices[0].message.content or ""
    raise last_error

# === STRUKTURA ADRESÁŘŮ ===
# Data a konfigurace
CONFIGS_DIR = DATA_DIR  # Přesměrováno na data
TEMPLATES_JSON_PATH = os.path.join(DATA_DIR, "mockup_templates.json")
PROMPTS_JSON_PATH = os.path.join(DATA_DIR, "prompts.json")
SKU_REGISTRY_PATH = os.path.join(DATA_DIR, "sku_registry.json")  # perzistentní SKU čítač

# 00_Input_Queue - Vstupní fronta
INPUT_QUEUE_DIR = os.path.join(PROJECT_ROOT, "automation", "00_Input_Queue") # Cesta uvnitř automation pro bot-specific data
# (pracovní složky se vytvářejí v ensure_dirs(), ne při importu modulu)
TO_EDIT_DIR = os.path.join(INPUT_QUEUE_DIR, "_To_Edit")
BATCH_LISTS_DIR = os.path.join(INPUT_QUEUE_DIR, "_Batch_Lists")
TOPICS_PATH = os.path.join(INPUT_QUEUE_DIR, "topics.json")  # téma/klíčová slova ke zdrojovým obrázkům (SEO pro SOLO)

# 01_System_Core - Systémové jádro (= tento skript)
SYSTEM_CORE_DIR = SCRIPT_DIR
ASSETS_DIR = os.path.join(PROJECT_ROOT, "images") # Použít složku images v kořenu

# Šablony mockupů: JEDINÝ zdroj pravdy je MOCKUP_TEMPLATES_DIR, ostatní názvy jsou aliasy.
MOCKUP_TEMPLATES_DIR = os.path.join(SCRIPT_DIR, "1_Mockup_Sablony")
MOCKUP_DIR = MOCKUP_TEMPLATES_DIR            # alias (zpětná kompatibilita)
TEMPLATES_MOCKUP_DIR = MOCKUP_TEMPLATES_DIR  # alias (zpětná kompatibilita)

# 02_Warehouse - Hotové produkty
WAREHOUSE_DIR = os.path.join(PROJECT_ROOT, "automation", "02_Warehouse")
# viz ensure_dirs()
SINGLES_DIR = os.path.join(WAREHOUSE_DIR, "Singles")
BUNDLES_DIR = os.path.join(WAREHOUSE_DIR, "Bundles")

# 03_Archive - Archiv
ARCHIVE_ROOT_DIR = os.path.join(PROJECT_ROOT, "automation", "03_Archive")
# viz ensure_dirs()

# Legacy aliases (zpětná kompatibilita)
OUTPUT_DIR = SINGLES_DIR  # Staré OUTPUT_DIR nyní ukazuje na Singles


def ensure_dirs() -> None:
    """Vytvoří pracovní složky. Volá se z CLI/GUI při startu úlohy, nikoli při importu modulu."""
    for directory in (INPUT_QUEUE_DIR, TO_EDIT_DIR, WAREHOUSE_DIR, SINGLES_DIR, BUNDLES_DIR, ARCHIVE_ROOT_DIR):
        os.makedirs(directory, exist_ok=True)


def generate_image(prompt, width=None, height=None):
    """Pollinations Flux. Výchozí 1536x2048 (poměr 3:4, config.json -> "image": {width, height}).

    Při chybě 429/5xx, timeoutu nebo vadném obrázku zkouší až 3x s rostoucím zpožděním.
    """
    # Klíč se čte z .env/proměnné prostředí - NIKDY ho nezapisuj do kódu!
    api_key = os.getenv("POLLINATIONS_API_KEY")
    if not api_key:
        print("   ❌ Chybí POLLINATIONS_API_KEY v .env souboru - generování přeskočeno.")
        return None

    cfg = _PROJECT_CONFIG.get("image", {})
    cfg = cfg if isinstance(cfg, dict) else {}
    width = int(width or cfg.get("width", 1536))
    height = int(height or cfg.get("height", 2048))
    print(f"   Generování obrazu (Pollinations.ai Flux {width}x{height})...")

    base_url = "https://gen.pollinations.ai/image"
    # Seed: výchozí je náhodný (každá generace jiný obrázek); pro reprodukovatelnost nastav POLLINATIONS_SEED v .env.
    seed_env = os.getenv("POLLINATIONS_SEED", "").strip()
    headers = {"Authorization": f"Bearer {api_key}"}
    encoded_prompt = urllib.parse.quote(f"{prompt}, 8k, centered, masterpiece")
    url = f"{base_url}/{encoded_prompt}"

    for attempt, delay in enumerate((0, 8, 20), 1):
        if delay:
            print(f"   ⏳ Další pokus za {delay} s ({attempt}/3)")
            for _ in range(delay):
                check_cancel()
                time.sleep(1)
        seed = int(seed_env) if seed_env.isdigit() else random.randint(1, 2**31 - 1)
        params = {"model": "flux", "width": width, "height": height, "seed": seed, "nologo": "true"}
        try:
            r = requests.get(url, headers=headers, params=params, timeout=180)
        except requests.RequestException as e:
            print(f"   ❌ Chyba při generování: {e}")
            continue
        if r.status_code == 200:
            try:
                img = Image.open(io.BytesIO(r.content))
                img.load()
                return img
            except Exception as e:  # noqa: BLE001 - vadný obrázek = zkusit znovu
                print(f"   ❌ Odpověď není platný obrázek: {e}")
                continue
        print(f"   ❌ Chyba API: {r.status_code} - {r.text[:200]}")
        if r.status_code != 429 and r.status_code < 500:
            break  # chyba klienta (např. 401/400) se opakováním nevyřeší
    return None


def _generate_image_legacy(prompt):
    print(f"   Generování obrazu (Pollinations.ai Flux)...")
    
    # Klíč se čte z .env/proměnné prostředí - NIKDY ho nezapisuj do kódu!
    api_key = os.getenv("POLLINATIONS_API_KEY")
    if not api_key:
        print("   ❌ Chybí POLLINATIONS_API_KEY v .env souboru - generování přeskočeno.")
        return None
    
    # Format: https://gen.pollinations.ai/image/{prompt}?model=flux&width={width}&height={height}&seed={seed}
    base_url = "https://gen.pollinations.ai/image"

    # Seed: výchozí je náhodný (každá generace jiný obrázek).
    # Pro reprodukovatelnost nastav POLLINATIONS_SEED v .env.
    seed_env = os.getenv("POLLINATIONS_SEED", "").strip()
    seed = int(seed_env) if seed_env.isdigit() else random.randint(1, 2**31 - 1)
    
    params = {
        "model": "flux",
        "width": 1024,
        "height": 1024,
        "seed": seed,
        "nologo": "true"
    }
    
    headers = {
        "Authorization": f"Bearer {api_key}"
    }
    
    # Encode prompt for URL path
    encoded_prompt = urllib.parse.quote(f"{prompt}, 8k, centered, masterpiece")
    url = f"{base_url}/{encoded_prompt}"
    
    try:
        # Pollinations uses GET for simple image generation
        r = requests.get(url, headers=headers, params=params, timeout=120)
        
        if r.status_code == 200:
            return Image.open(io.BytesIO(r.content))
        else:
            print(f"   ❌ Chyba API ({url}): {r.status_code} - {r.text[:200]}")
            return None
            
    except Exception as e:
        print(f"   ❌ Chyba při generování: {e}")
        return None 


# === SKU GENERÁTOR dle pravidla.md ===
@contextlib.contextmanager
def _sku_lock():
    """Procesový zámek nad SKU registrem (brání duplicitním SKU při souběžných úlohách)."""
    os.makedirs(DATA_DIR, exist_ok=True)
    lock_file = open(os.path.join(DATA_DIR, ".sku_registry.lock"), "a")
    try:
        try:
            import fcntl
            fcntl.flock(lock_file, fcntl.LOCK_EX)
        except ImportError:  # Windows
            import msvcrt
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
        yield
    finally:
        lock_file.close()  # zavření souboru zámek uvolní


def generate_sku(product_type: str = "S") -> str:
    """Vygeneruje unikátní SKU (SP-YYMMDD-SEQ-TYPE) pod zámkem."""
    with _sku_lock():
        return _generate_sku_unlocked(product_type)


def _generate_sku_unlocked(product_type: str = "S") -> str:
    """Generuje unikátní SKU dle formátu SP-YYMMDD-SEQ-TYPE
    
    Args:
        product_type: 'S' pro Single, 'B' pro Bundle
    Returns:
        SKU string, např. 'SP-260208-01-S'
    """
    today = datetime.now().strftime("%y%m%d")
    prefix = f"SP-{today}-"

    # Perzistentní registr SKU - chrání proti kolizím po archivaci a při
    # paralelních bězích (SEQ se neztratí, i když složky zmizí do 03_Archive)
    registry = {}
    try:
        if os.path.exists(SKU_REGISTRY_PATH):
            with open(SKU_REGISTRY_PATH, "r", encoding="utf-8") as f:
                registry = json.load(f)
    except (OSError, ValueError) as e:
        print(f"   ⚠️ SKU registr nelze načíst ({e}), pokračuji skenem složek.")

    max_seq = int(registry.get(today, {}).get(product_type, 0))

    # Najdi nejvyšší SEQ pro dnešní den v obou složkách (sken jako pojistka)
    for wdir in [SINGLES_DIR, BUNDLES_DIR]:
        if os.path.exists(wdir):
            for folder in os.listdir(wdir):
                if folder.startswith(prefix):
                    try:
                        parts = folder.split("-")
                        if len(parts) >= 4 and parts[3].startswith(product_type):
                            seq = int(parts[2].split("_")[0])  # Handle SP-260208-01-S_Name
                            max_seq = max(max_seq, seq)
                    except (ValueError, IndexError):
                        pass

    new_seq = max_seq + 1

    # Uložit do registru pro příští běh
    registry.setdefault(today, {})[product_type] = new_seq
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(SKU_REGISTRY_PATH, "w", encoding="utf-8") as f:
            json.dump(registry, f, indent=2)
    except OSError as e:
        print(f"   ⚠️ SKU registr nelze uložit: {e}")

    new_seq_str = str(new_seq).zfill(2)
    return f"SP-{today}-{new_seq_str}-{product_type}"


def _ascii_slug(text: str) -> str:
    """Odstraní diakritiku a vše krom písmen/číslic ('Mělník' -> 'Melnik'; dřív se základní písmena ztrácela: 'Mlnk')."""
    import unicodedata
    folded = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode("ascii")
    return re.sub(r'[^a-zA-Z0-9]', '', folded)


def _title_from_filename(name: str) -> str:
    """Čitelný název z názvu souboru: 'mont_saint-michel2' -> 'Mont Saint Michel2'."""
    import unicodedata
    folded = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode("ascii")
    folded = re.sub(r'([a-z])([A-Z])', r'\1 \2', folded)      # CamelCase -> Camel Case
    words = re.sub(r'[^a-zA-Z0-9]+', ' ', folded).split()
    return ' '.join(w.capitalize() if w.islower() else w for w in words) or 'Digital Art'


def create_product_folder(sku: str, keyword: str) -> str:
    """Vytvoří složku produktu s korektní strukturou dle pravidla.md
    
    Args:
        sku: Vygenerovaný SKU (např. 'SP-260208-01-S')
        keyword: Klíčové slovo produktu (např. 'AbstractGeometric')
    Returns:
        Cesta k vytvořené složce
    """
    product_type = sku.split("-")[-1]
    target_dir = SINGLES_DIR if product_type == "S" else BUNDLES_DIR
    
    # Očistit keyword od speciálních znaků
    safe_keyword = (_ascii_slug(keyword)[:40]) or "Product"
    folder_name = f"{sku}_{safe_keyword}"
    folder_path = os.path.join(target_dir, folder_name)
    
    # Vytvořit strukturu dle pravidel
    os.makedirs(folder_path, exist_ok=True)
    os.makedirs(os.path.join(folder_path, "01_Print_Files"), exist_ok=True)
    os.makedirs(os.path.join(folder_path, "02_Marketing_Assets"), exist_ok=True)
    os.makedirs(os.path.join(folder_path, "03_Metadata"), exist_ok=True)
    
    # Soubor 00_Master_Source.png bude přidán při generování
    
    print(f"   📁 Vytvořena produktová složka: {folder_name}")
    return folder_path


def create_listing_data(sku: str, title: str, tags: list, price: float = None, description: str = "") -> dict:
    """Vytvoří metadata pro listing dle pravidla.md formátu"""
    if price is None:
        price = DEFAULT_PRICE_BUNDLE if sku.endswith("-B") else DEFAULT_PRICE_SINGLE
    return {
        "sku": sku,
        "title": title,
        "description_generated": description or "",
        "seo_tags": tags,
        "pricing": {
            "currency": "EUR",
            "amount": price
        },
        "file_paths": {}
    }


# === LEGACY CESTY (zpětná kompatibilita) ===
# Vstupy pro SOLO - z Input Queue
SOLO_INPUT_DIR = TO_EDIT_DIR

# Cesty pro browsing mockupů
ETSY_ROOT = os.environ.get("ETSY_BROWSE_ROOT", os.path.join(os.path.expanduser("~"), "Pictures", "Etsy"))
ETSY_BROWSE_ROOT = ETSY_ROOT

# Požadované výstupní formáty pro Etsy (vysoká kvalita dle upravapic.md)
# Tiskové formáty podle orientace zdroje (dosud se vše ořízlo na 5 širokých/portrétních bez ohledu na obrázek):
# našívání 3:4 portrétu na 16:9 zahazovalo ~70 % obrazu.
def _size(label: str):
    dims = label.split("-")[1]
    w, h = dims.split("x")
    return {"name": label, "w": int(w), "h": int(h)}


PORTRAIT_SIZES = [_size(s) for s in ("15x20-4500x6000", "16x20-4800x6000", "12x18-4000x6000", "11x14-3300x4200", "12x12-3600x3600")]
LANDSCAPE_SIZES = [_size(s) for s in ("20x15-6000x4500", "20x16-6000x4800", "18x12-6000x4000", "14x11-4200x3300", "12x12-3600x3600")]
SQUARE_SIZES = [_size(s) for s in ("12x12-3600x3600", "16x16-4800x4800", "20x20-6000x6000")]
PRINT_SIZES = PORTRAIT_SIZES  # zpětná kompatibilita (výchozí sada)


def print_sizes_for(size):
    """Vrátí sadu tiskových velikostí podle poměru stran zdroje (šířka, výška)."""
    w, h = size
    aspect = w / h if h else 1.0
    if 0.9 <= aspect <= 1.1:
        return SQUARE_SIZES
    return LANDSCAPE_SIZES if aspect > 1 else PORTRAIT_SIZES


def _all_size_tokens():
    return sorted({s["name"].split("-")[0] for group in (PORTRAIT_SIZES, LANDSCAPE_SIZES, SQUARE_SIZES) for s in group}
                  | {"15x20", "16x20", "16x9", "20x11", "24x13"})

# Cesta k testovacímu artu (lze přepsat přes TEST_ART_PATH v .env)
TEST_ART_PATH = os.environ.get(
    "TEST_ART_PATH",
    r"c:\Users\cowle\Pictures\Etsy\01_Hotove_Produkty\SeFStandalone\Art.png",
)

def load_templates():
    if os.path.exists(TEMPLATES_JSON_PATH):
        with open(TEMPLATES_JSON_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_templates(templates):
    with open(TEMPLATES_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(templates, f, indent=4, ensure_ascii=False)

# Načtení šablon při startu
MOCKUP_TEMPLATES = load_templates()


def reload_config() -> None:
    """Znovu načte .env, config.json a šablony mockupů.

    GUI ji volá před každou úlohou, aby se změny z Nastavení projevily bez restartu.
    """
    global _PROJECT_CONFIG, _GROQ_CONFIG, DEFAULT_PRICE_SINGLE, DEFAULT_PRICE_BUNDLE
    global GROQ_MODEL, GROQ_TIMEOUT, GROQ_MAX_RETRIES, GROQ_API_KEY, ETSY_API_KEY, ETSY_SHOP_ID
    global MOCKUP_TEMPLATES
    load_dotenv(os.path.join(PROJECT_ROOT, ".env"), override=True)
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")
    ETSY_API_KEY = os.getenv("ETSY_API_KEY")
    ETSY_SHOP_ID = os.getenv("ETSY_SHOP_ID")
    _PROJECT_CONFIG = _load_project_config()
    prices = _PROJECT_CONFIG.get("prices", {})
    DEFAULT_PRICE_SINGLE = float(prices.get("single", 5.90))
    DEFAULT_PRICE_BUNDLE = float(prices.get("bundle", 9.90))
    _GROQ_CONFIG = _PROJECT_CONFIG.get("groq", {})
    GROQ_MODEL = _GROQ_CONFIG.get("model", "openai/gpt-oss-120b")
    GROQ_TIMEOUT = float(_GROQ_CONFIG.get("timeout", 60))
    GROQ_MAX_RETRIES = int(_GROQ_CONFIG.get("max_retries", 3))
    MOCKUP_TEMPLATES = load_templates()


# --- 2. FUNKCE PRO KVALITU ---

def find_coeffs(pa, pb):
    matrix = []
    for p1, p2 in zip(pa, pb):
        matrix.append([p1[0], p1[1], 1, 0, 0, 0, -p2[0]*p1[0], -p2[0]*p1[1]])
        matrix.append([0, 0, 0, p1[0], p1[1], 1, -p2[1]*p1[0], -p2[1]*p1[1]])

    A = np.array(matrix, dtype=float)
    B = np.array(pb).reshape(8)

    res, *_ = np.linalg.lstsq(A, B, rcond=None)
    return np.asarray(res).reshape(8)

def process_high_quality_print(source_img, output_folder, base_name):
    """Vytvoří tiskové varianty (sada podle poměru stran zdroje) ze zdroje z Pollinations (výchozí 1536x2048)."""
    print(f"   ⚙️  Extrémní upscaling a vylepšení detailů: {base_name}")
    
    if source_img.mode != "RGB":
        source_img = source_img.convert("RGB")

    # 1. Před-zpracování: Mírné zvýraznění detailů v původním malém rozlišení
    source_img = source_img.filter(ImageFilter.DETAIL)
    
    # Mírné zvýšení kontrastu a sytosti (vhodné pro tisk)
    source_img = ImageEnhance.Contrast(source_img).enhance(1.05)
    source_img = ImageEnhance.Color(source_img).enhance(1.05)

    for size in print_sizes_for(source_img.size):
        target_w = size["w"]
        target_h = size["h"]
        size_label = size["name"]
        
        src_w, src_h = source_img.size
        src_aspect = src_w / src_h
        target_aspect = target_w / target_h
        
        if src_aspect > target_aspect:
            new_h = target_h
            new_w = int(src_aspect * new_h)
        else:
            new_w = target_w
            new_h = int(new_w / src_aspect)
            
        # 2. Resampling: LANCZOS je nejlepší dostupný filtr pro upscaling v Pillow
        img_resized = source_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        
        # 3. Ořez na střed
        left = (new_w - target_w) / 2
        top = (new_h - target_h) / 2
        right = (new_w + target_w) / 2
        bottom = (new_h + target_h) / 2
        img_cropped = img_resized.crop((left, top, right, bottom))
        
        # 4. Finální zostření: Agresivnější nastavení pro kompenzaci 10x zvětšení
        img_final = img_cropped.filter(ImageFilter.UnsharpMask(radius=2.0, percent=150, threshold=1))
        
        out_path = os.path.join(output_folder, f"{base_name}-{size_label}.jpg")
        img_final.save(out_path, "JPEG", quality=95, dpi=(300, 300), subsampling=0)

# --- 3. LOGIKA AGENTA ---

def market_research(client):
    print("\n🕵️  Průzkum trhu...")
    prompt = """Act as a professional Art Market Trend Analyst for Etsy 2026.\nIdentify ONE specific, high-demand, low-competition art niche.\nFocus on styles like: Dark Academia, Moody Landscapes, Witchy Cottagecore, Japandi, or Abstract Organic.\n    
Output ONLY a raw JSON:\n{ \"bundle_theme\": \"Name of the theme\", \"visual_style\": \"Detailed visual description, colors, mood\", \"target_audience\": \"Who buys this\" }\n"""
    try:
        content = groq_complete(client, prompt).replace("```json", "").replace("```", "").strip()
        data = json.loads(content)
        if not str(data.get("bundle_theme", "")).strip():
            raise ValueError("odpověď nemá bundle_theme")
        data.setdefault("visual_style", "cohesive collection, rich detail")
        data.setdefault("target_audience", "")
        return data
    except Exception as e:
        print(f"   ⚠️ Průzkum trhu selhal ({e}), používám záložní téma.")
        return {"bundle_theme": "Dark Academia Botanical", "visual_style": "Vintage, moody, herbs", "target_audience": "Nature lovers"}

def get_prompts(client, trend):
    """Vrátí přesně 5 neprázdných promptů (LLM někdy vrátí jiný počet nebo položky, které nejsou text)."""
    raw = _get_prompts_raw(client, trend)
    prompts = [str(p).strip() for p in (raw if isinstance(raw, list) else []) if isinstance(p, (str, int, float)) and str(p).strip()]
    prompts = prompts[:5]
    while len(prompts) < 5:  # doplň variantami, aby bundle měl vždy 5 různých obrazů
        base = prompts[len(prompts) % len(prompts)] if prompts else f"{trend['bundle_theme']} masterpiece"
        prompts.append(f"{base}, variation {len(prompts) + 1}")
    return prompts


def _get_prompts_raw(client, trend):
    print("🎨 Návrh kolekce...")
    # Používáme zdvojené závorky {{ }} pro JSON v f-stringu
    prompt = f"Create 5 prompts for '{trend['bundle_theme']}'. Style: {trend['visual_style']}. Composition MUST be a vertical 3:4 portrait, main subject centered with generous empty margins (nothing important near the edges). Return ONLY raw JSON: {{'prompts': ['p1', 'p2', 'p3', 'p4', 'p5']}}"
    try:
        content = groq_complete(client, prompt).strip()
        # Odstranění Markdown kódování
        content = re.sub(r'```json\s*|\s*```', '', content)
        # Odstranění případného textu okolo (hledáme první { a poslední })
        start = content.find('{')
        end = content.rfind('}') + 1
        if start != -1 and end != -1:
            content = content[start:end]
            
        try:
            return json.loads(content)["prompts"]
        except json.JSONDecodeError:
            # Fallback pro situaci, kdy model použije jednoduché uvozovky (validní Python dict, ne JSON)
            import ast
            return ast.literal_eval(content)["prompts"]
            
    except Exception as e:
        print(f"   ❌ Prompty se nepodařilo získat: {e}")
        raise


# --- MOCKUPY: jedna implementace pro všechny režimy ---

DEFAULT_MOCKUP_CONFIG = {"x": 400, "y": 300, "w": 200, "h": 150}

def find_template_config(filename):
    """Vrátí konfiguraci šablony podle názvu souboru, nebo None."""
    for configs in MOCKUP_TEMPLATES.values():
        for config in configs:
            if config.get("filename") == filename:
                return config
    return None

def _crop_to_aspect(img, aspect):
    """Veškerý obraz ořízne na střed tak, aby měl poměr stran `aspect` (šířka/výška) - místo deformace."""
    w, h = img.size
    if h == 0 or aspect <= 0 or abs(w / h - aspect) < 0.01:
        return img
    if w / h > aspect:
        new_w = int(round(h * aspect))
        left = (w - new_w) // 2
        return img.crop((left, 0, left + new_w, h))
    new_h = int(round(w / aspect))
    top = (h - new_h) // 2
    return img.crop((0, top, w, top + new_h))


def render_mockup(art, template_path, config):
    """Vloží art do šablony mockupu a vrátí hotový RGB obrázek.

    Pokud config obsahuje 'corners' (TL, TR, BR, BL), použije se perspektivní
    transformace; jinak se art zmenší na x/y/w/h a vloží na dané místo. Art se před
    vložením ořízne na poměr rámu (portrét ve širokém rámu se tedy nedeformuje).
    """
    bg = Image.open(template_path).convert("RGBA")

    if art.mode != "RGBA":
        art = art.convert("RGBA")

    if "corners" in config:
        tl, tr, br, bl = [tuple(map(float, c)) for c in config["corners"]]
        frame_w = (np.hypot(tr[0] - tl[0], tr[1] - tl[1]) + np.hypot(br[0] - bl[0], br[1] - bl[1])) / 2
        frame_h = (np.hypot(bl[0] - tl[0], bl[1] - tl[1]) + np.hypot(br[0] - tr[0], br[1] - tr[1])) / 2
        if frame_h > 0:
            art = _crop_to_aspect(art, frame_w / frame_h)
        width, height = art.size
        # Zdrojové rohy (celý art) - pořadí: TL, TR, BR, BL
        source_corners = [(0, 0), (width, 0), (width, height), (0, height)]
        coeffs = find_coeffs(config["corners"], source_corners)
        # Transformujeme do plné velikosti pozadí a vložíme přes alfa masku
        art_transformed = art.transform(bg.size, Image.PERSPECTIVE, coeffs, Image.BICUBIC)
        bg.paste(art_transformed, (0, 0), art_transformed)
    else:
        art = _crop_to_aspect(art, config["w"] / config["h"])
        art_resized = art.resize((config["w"], config["h"]), Image.Resampling.LANCZOS)
        bg.paste(art_resized, (config["x"], config["y"]))

    return bg.convert("RGB")

def create_mockup(art, output_path, cat, used=None):
    """Vytvoří mockup ze šablony kategorie `cat` (MOCKUP_TEMPLATES[cat]). Vrací True/False.

    `used` je množina názvů již použitých šablon v tomto produktu: šablony se nemění na opakování, dokud
    jsou jiné k dispozici. Když kategorie neexistuje nebo je prázdná, použije se libovolná jiná (s varováním).
    """
    used = used if used is not None else set()
    configs = list(MOCKUP_TEMPLATES.get(cat, []))
    if not configs:
        configs = [c for group in MOCKUP_TEMPLATES.values() for c in group]
        if configs:
            print(f"   ⚠️ Kategorie '{cat}' nemá žádné šablony, použiji jinou.")
    configs = [c for c in configs if os.path.exists(os.path.join(MOCKUP_TEMPLATES_DIR, c.get("filename", "")))]
    if not configs:
        print(f"   ❌ Mockup '{os.path.basename(output_path)}' nevznikl: žádná použitelná šablona (kategorie '{cat}').")
        return False
    fresh = [c for c in configs if c["filename"] not in used]
    config = random.choice(fresh or configs)
    tmpl_path = os.path.join(MOCKUP_TEMPLATES_DIR, config["filename"])
    try:
        render_mockup(art, tmpl_path, config).save(output_path, quality=93)
        used.add(config["filename"])
        print(f"   ✅ Mockup hotov: {cat} ({config['filename']})")
        return True
    except Exception as e:
        print(f"   ❌ Chyba mockupu: {e}")
        return False


def _load_font(size: int):
    from PIL import ImageFont
    for path in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
                 "C:\\Windows\\Fonts\\arialbd.ttf"):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)  # Pillow >= 10.1
    except TypeError:
        return ImageFont.load_default()


def create_bundle_overview(images, output_path, caption="Set of 5 Printable Wall Art"):
    """Přehledový obrázek bundlu: všech (až 5) obrazů pohromadě ve dvou řádcích (hlavní obrázek listingu)."""
    from PIL import ImageDraw
    if not images:
        return False
    try:
        canvas_w, canvas_h = 3000, 2250  # 4:3 doporučený pro Etsy
        canvas = Image.new("RGB", (canvas_w, canvas_h), (236, 232, 226))
        frame_w, frame_h, gap = 660, 880, 70
        rows = [images[:3], images[3:5]]
        total_h = frame_h * len([r for r in rows if r]) + gap * (len([r for r in rows if r]) - 1)
        y = (canvas_h - total_h) // 2 - 60
        for row in rows:
            if not row:
                continue
            row_w = frame_w * len(row) + gap * (len(row) - 1)
            x = (canvas_w - row_w) // 2
            for art in row:
                tile = _crop_to_aspect(art.convert("RGB"), frame_w / frame_h).resize((frame_w, frame_h), Image.Resampling.LANCZOS)
                shadow = Image.new("RGBA", (frame_w + 80, frame_h + 80), (0, 0, 0, 0))
                ImageDraw.Draw(shadow).rectangle((40, 40, frame_w + 40, frame_h + 40), fill=(0, 0, 0, 90))
                shadow = shadow.filter(ImageFilter.GaussianBlur(18))
                canvas.paste(shadow, (x - 30, y - 20), shadow)
                border = Image.new("RGB", (frame_w + 24, frame_h + 24), (250, 250, 248))
                canvas.paste(border, (x - 12, y - 12))
                canvas.paste(tile, (x, y))
                x += frame_w + gap
            y += frame_h + gap
        draw = ImageDraw.Draw(canvas)
        font = _load_font(90)
        text_w = draw.textlength(caption, font=font)
        draw.text(((canvas_w - text_w) / 2, canvas_h - 190), caption, fill=(60, 56, 52), font=font)
        canvas.save(output_path, quality=93)
        print("   ✅ Přehledový obrázek bundlu hotov")
        return True
    except Exception as e:  # noqa: BLE001
        print(f"   ❌ Chyba přehledového obrázku: {e}")
        return False

def create_mockup_from_templates_dir(art, output_path):
    """Vytvoří mockup z náhodné šablony ze složky MOCKUP_TEMPLATES_DIR"""
    if not os.path.exists(MOCKUP_TEMPLATES_DIR):
        print(f"   ❌ Složka se šablonami neexistuje: {MOCKUP_TEMPLATES_DIR}")
        return False
    
    template_files = [f for f in os.listdir(MOCKUP_TEMPLATES_DIR) if f.lower().endswith('.png')]
    
    if not template_files:
        print(f"   ❌ Ve složce šablon nejsou žádné PNG soubory")
        return False
    
    random_template = random.choice(template_files)
    template_path = os.path.join(MOCKUP_TEMPLATES_DIR, random_template)
    
    print(f"   🎲 Použita šablona: {random_template}")
    
    template_config = find_template_config(random_template)
    if not template_config:
        print(f"   ⚠️ Konfigurace pro šablonu {random_template} nebyla nalezena, používám výchozí rozměry")
        template_config = DEFAULT_MOCKUP_CONFIG
    
    try:
        render_mockup(art, template_path, template_config).save(output_path, quality=93)
        print(f"   ✅ Mockup vytvořen: {output_path}")
        return True
    except Exception as e:
        print(f"   ❌ Chyba při vytváření mockupu: {e}")
        return False

def generate_seo_text(client, trend_data, output_folder):
    """Vygeneruje SEO texty (title/description/tags) a uloží BUNDLE_INFO.txt.

    Returns:
        Dict {"title", "description", "tags"} (viz parse_seo_text) nebo None při selhání.
    """
    print("📝 Generování SEO textů...")
    prompt = f"""Write Etsy Listing Info for: {trend_data['bundle_theme']} (visual style: {trend_data.get('visual_style', '')})\nOutput Structure:\nTITLE: (SEO friendly, plain text, max 140 characters, no emojis)\nDESCRIPTION: (Sales copy, plain text, 150-300 words, mention instant digital download and the included print sizes; do NOT mention AI)\nTAGS: (13 tags comma separated)\n"""
    try:
        content = groq_complete(client, prompt)
        with open(os.path.join(output_folder, "BUNDLE_INFO.txt"), "w", encoding="utf-8") as f:
            f.write(content)
        seo = parse_seo_text(content)
        if seo["tags"] or seo["title"] or seo["description"]:
            return seo
        return None
    except Exception as e:
        print(f"   ⚠️ SEO generování jako celek selhalo: {e}")
        return None


ETSY_TITLE_MAX = 140


def _truncate_title(title: str, limit: int = ETSY_TITLE_MAX) -> str:
    """Ořízne titulek na limit Etsy po celém slově."""
    title = re.sub(r'\s+', ' ', title).strip(' "\'*#')
    if len(title) <= limit:
        return title
    cut = title[:limit]
    if ' ' in cut and title[limit] != ' ':
        cut = cut.rsplit(' ', 1)[0]
    return cut.rstrip(' ,;:-|')


def parse_seo_text(content: str) -> dict:
    """Vyparsuje TITLE / DESCRIPTION / TAGS z výstupu LLM.

    Returns:
        {"title": str (max 140 znaků), "description": str, "tags": list} - chybějící části jsou prázdné.
    """
    result = {"title": "", "description": "", "tags": parse_seo_tags(content)}
    if not content:
        return result

    title_match = re.search(r'^[\s*#>\-]*TITLE\s*\**\s*:\s*\**\s*(.+)$', content, re.IGNORECASE | re.MULTILINE)
    if title_match:
        result["title"] = _truncate_title(title_match.group(1))

    desc_match = re.search(
        r'^[\s*#>\-]*DESCRIPTION\s*\**\s*:\s*\**\s*(.+?)(?=^[\s*#>\-]*TAGS?\s*\**\s*:|\Z)',
        content, re.IGNORECASE | re.MULTILINE | re.DOTALL,
    )
    if desc_match:
        description = desc_match.group(1).replace('**', '').strip()
        result["description"] = re.sub(r'\n{3,}', '\n\n', description)
    return result


def parse_seo_tags(content: str) -> list:
    """Vytáhne TAGS řádek z výstupu LLM a vrátí max. 13 tagů o max. 20 znacích."""
    if not content:
        return []
    match = re.search(r'^[\s*#>\-]*TAGS?\s*\**\s*:\s*\**\s*(.+)', content, re.IGNORECASE | re.MULTILINE)
    if not match:
        return []
    tags = []
    for raw in match.group(1).split(','):
        tag = raw.strip().strip('.,;"\'* ').strip()
        if tag and tag.lower() not in [t.lower() for t in tags]:
            tags.append(tag[:20])  # Etsy limit je 20 znaků na tag
        if len(tags) >= 13:
            break
    return tags

# --- BROWSE A MOCKUP ---

IMAGE_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.bmp', '.gif')

def is_source_image(filename):
    """Kontrola, zda je soubor zdrojový obrázek (neobsahuje rozlišení v názvu)"""
    # Rozlišení, která chceme ignorovat
    resolution_patterns = _all_size_tokens()
    
    filename_lower = filename.lower()
    for pattern in resolution_patterns:
        if pattern in filename_lower:
            return False
    
    # Kontrola, zda už není mockup
    if '_mockup' in filename_lower:
        return False
    
    return True

def process_folder_automatically(folder_path):
    """Automaticky zpracuje složku - najde zdrojový obrázek a vytvoří mockup"""
    try:
        items = os.listdir(folder_path)
        image_files = [item for item in items if os.path.isfile(os.path.join(folder_path, item)) 
                      and item.lower().endswith(IMAGE_EXTENSIONS)]
        
        # Najdi zdrojový obrázek
        source_images = [img for img in image_files if is_source_image(img)]
        
        if not source_images:
            print(f"  ⚠️  Žádný zdrojový obrázek nenalezen ve složce")
            return False
        
        # Vezmi první nalezený zdrojový obrázek
        source_image = source_images[0]
        image_path = os.path.join(folder_path, source_image)
        
        print(f"\n✅ Vybrán obrázek: {source_image}")
        print(f"📍 Cesta: {image_path}")
        
        # Vytvoř mockup
        print("\n🎨 Vytvářím mockup...")
        with Image.open(image_path) as img:
            base_name = os.path.splitext(source_image)[0]
            mockup_filename = f"{base_name}_mockup.jpg"
            mockup_path = os.path.join(folder_path, mockup_filename)
            
            success = create_mockup_from_templates_dir(img, mockup_path)
            
            if success:
                print(f"\n✨ Mockup úspěšně vytvořen!")
                print(f"💾 Uložen do: {mockup_path}")
                return True
            else:
                print(f"\n❌ Nepodařilo se vytvořit mockup")
                return False
                
    except Exception as e:
        print(f"❌ Chyba při zpracování složky: {e}")
        return False

def automate_folder_processing(base_path):
    """Automaticky projde všechny podsložky a vytvoří mockupy"""
    try:
        items = os.listdir(base_path)
        # Exclude Archive folder
        folders = sorted([item for item in items if os.path.isdir(os.path.join(base_path, item)) and item != "Archive"])
        
        if not folders:
            print("  ⚠️  Žádné podsložky k zpracování")
            return
        
        print(f"\n📂 Aktuální cesta: {base_path}")
        print("="*60)
        print(f"\n  Složka vybrána, spouštím automatizaci\n")
        print("📁 SLOŽKY PRO AUTOMATIZACI:")
        for i, folder in enumerate(folders, 1):
            print(f"  {i}. 📁 {folder}")
        print("\n" + "="*60)
        
        # Projdi všechny složky
        for i, folder in enumerate(folders, 1):
            folder_path = os.path.join(base_path, folder)
            
            print(f"\n{'='*60}")
            print(f"AUTOMATICKá volba: '{i}'")
            print(f"📂 Zpracovávám složku: {folder}")
            print("="*60)
            
            # Zkontroluj, zda složka obsahuje obrázky
            items = os.listdir(folder_path)
            image_files = sorted([item for item in items if os.path.isfile(os.path.join(folder_path, item)) 
                                 and item.lower().endswith(IMAGE_EXTENSIONS)])
            
            if image_files:
                # Zobraz obrázky
                print("\n🖼️  OBRÁZKY:")
                for j, img in enumerate(image_files, 1):
                    file_size = os.path.getsize(os.path.join(folder_path, img))
                    size_mb = file_size / (1024 * 1024)
                    print(f"  {j}. 🖼️  {img} ({size_mb:.2f} MB)")
                
                print("\n" + "="*60)
                print("Volby:")
                print("  Zadej číslo pro výběr složky nebo obrázku")
                print("  '..' pro návrat o úroveň výš")
                print("  'g' pro výběr složky (nová volba)")
                print("  'q' pro ukončení")
                
                # Najdi zdrojový obrázek
                source_images = [img for img in image_files if is_source_image(img)]
                
                if source_images:
                    source_index = image_files.index(source_images[0]) + 1
                    print(f"\nAUTOMATICKá volba: '{source_index}'")
                    
                    # Zpracuj obrázek
                    process_folder_automatically(folder_path)
                    
                    # Zobraz aktualizovaný seznam
                    print(f"\nChceš vybrat další obrázek? (automatická volba) (a/n): a")
                    
                    # Zobraz aktualizované obrázky
                    updated_items = os.listdir(folder_path)
                    updated_images = sorted([item for item in updated_items if os.path.isfile(os.path.join(folder_path, item)) 
                                           and item.lower().endswith(IMAGE_EXTENSIONS)])
                    
                    print(f"\n📂 Aktuální cesta: {folder_path}")
                    print("="*60)
                    print("\n🖼️  OBRÁZKY:")
                    for j, img in enumerate(updated_images, 1):
                        file_size = os.path.getsize(os.path.join(folder_path, img))
                        size_mb = file_size / (1024 * 1024)
                        print(f"  {j}. 🖼️  {img} ({size_mb:.2f} MB)")
                    
                    print("\n" + "="*60)
                    print("Volby:")
                    print("  Zadej číslo pro výběr složky nebo obrázku")
                    print("  '..' pro návrat o úroveň výš")
                    print("  'g' pro výběr složky (nová volba)")
                    print("  'q' pro ukončení")
                    print("\nAUTOMATICKá volba: '..'")
                else:
                    print("  ⚠️  Žádný zdrojový obrázek nenalezen")
            
            else:
                print("  ⚠️  Složka neobsahuje žádné obrázky")
        
        print(f"\n{'='*60}")
        print("✨ Automatizace dokončena!")
        print("="*60)
        
    except Exception as e:
        print(f"❌ Chyba při automatizaci: {e}")

def browse_and_create_mockup():
    """Procházení složek a vytváření mockupu z vybraného obrázku"""
    print(f"\n🔍 PROCHÁZENÍ SLOŽEK A VYTVÁŘENÍ MOCKUPU")
    print(f"Výchozí složka: {ETSY_BROWSE_ROOT}")
    
    if not os.path.exists(ETSY_BROWSE_ROOT):
        print(f"❌ Složka neexistuje: {ETSY_BROWSE_ROOT}")
        return
    
    current_path = ETSY_BROWSE_ROOT
    
    while True:
        print(f"\n📂 Aktuální cesta: {current_path}")
        print("="*60)
        
        try:
            items = os.listdir(current_path)
            
            # Rozděl na složky a soubory
            folders = sorted([item for item in items if os.path.isdir(os.path.join(current_path, item))])
            image_files = sorted([item for item in items if os.path.isfile(os.path.join(current_path, item)) 
                                 and item.lower().endswith(IMAGE_EXTENSIONS)])
            
            # Zobraz složky
            if folders:
                print("\n📁 SLOŽKY:")
                for i, folder in enumerate(folders, 1):
                    print(f"  {i}. 📁 {folder}")
            
            # Zobraz obrázky
            if image_files:
                print("\n🖼️  OBRÁZKY:")
                folder_count = len(folders)
                for i, img in enumerate(image_files, folder_count + 1):
                    file_size = os.path.getsize(os.path.join(current_path, img))
                    size_mb = file_size / (1024 * 1024)
                    print(f"  {i}. 🖼️  {img} ({size_mb:.2f} MB)")
            
            if not folders and not image_files:
                print("⚠️  Složka je prázdná")
            
            print("\n" + "="*60)
            print("Volby:")
            print("  Zadej číslo pro výběr složky nebo obrázku")
            print("  '..' pro návrat o úroveň výš")
            print("  'g' pro výběr složky (nová volba)")
            print("  'q' pro ukončení")
            
            choice = input("\nTvá volba: ").strip()
            
            if choice.lower() == 'q':
                print("👋 Ukončuji...")
                break
            
            if choice.lower() == 'g':
                # Spustit automatizaci pro aktuální složku
                automate_folder_processing(current_path)
                
                # Po dokončení automatizace se vrátit zpět do browseru
                print(f"\n📂 Návrat do prohlížeče složek...")
                continue
            
            if choice == '..':
                # Jdi o úroveň výš
                parent = os.path.dirname(current_path)
                if parent and os.path.exists(parent):
                    current_path = parent
                else:
                    print("⚠️  Jsi již v kořenové složce")
                continue
            
            try:
                index = int(choice) - 1
                
                # Kontrola, zda je to složka
                if 0 <= index < len(folders):
                    selected_folder = folders[index]
                    current_path = os.path.join(current_path, selected_folder)
                
                # Kontrola, zda je to obrázek
                elif len(folders) <= index < len(folders) + len(image_files):
                    image_index = index - len(folders)
                    selected_image = image_files[image_index]
                    image_path = os.path.join(current_path, selected_image)
                    
                    print(f"\n✅ Vybrán obrázek: {selected_image}")
                    print(f"📍 Cesta: {image_path}")
                    
                    # Vytvoř mockup
                    print("\n🎨 Vytvářím mockup...")
                    try:
                        with Image.open(image_path) as img:
                            # Vytvoř název pro mockup
                            base_name = os.path.splitext(selected_image)[0]
                            mockup_filename = f"{base_name}_mockup.jpg"
                            mockup_path = os.path.join(current_path, mockup_filename)
                            
                            success = create_mockup_from_templates_dir(img, mockup_path)
                            
                            if success:
                                print(f"\n✨ Mockup úspěšně vytvořen!")
                                print(f"💾 Uložen do: {mockup_path}")
                            else:
                                print(f"\n❌ Nepodařilo se vytvořit mockup")
                    
                    except Exception as e:
                        print(f"❌ Chyba při zpracování obrázku: {e}")
                    
                    # Zeptej se, zda pokračovat
                    cont = input("\nChceš vybrat další obrázek? (a/n): ").strip().lower()
                    if cont != 'a':
                        break
                
                else:
                    print("❌ Neplatný výběr")
                    
            except ValueError:
                print("❌ Zadej platné číslo, '..' , 'g' nebo 'q'")
                
        except PermissionError:
            print(f"❌ Nemáš oprávnění přistupovat k této složce")
            current_path = os.path.dirname(current_path)
        except Exception as e:
            print(f"❌ Chyba: {e}")
            break

# --- HLAVNÍ REŽIMY ---

BUNDLE_MOCKUP_NAMES = [
    ("01_Main_Thumbnail", "Obyčejný byt"),
    ("02_Bundle_Overview", "Střední třída"),
    ("03_Living_Room", "Luxusní sídlo"),
    ("04_Bedroom", "Obyčejný byt"),
    ("05_Office_Space", "Střední třída"),
    ("06_Detail_View", "Luxusní sídlo"),
    ("07_Size_Comparison", "Obyčejný byt"),
    ("08_Lifestyle", "Střední třída"),
]

SINGLE_MOCKUP_NAMES = [
    ("01_Main_Thumbnail", "Obyčejný byt"),
    ("02_Living_Room", "Střední třída"),
    ("03_Bedroom", "Luxusní sídlo"),
    ("04_Office", "Obyčejný byt"),
    ("05_Detail_Close", "Střední třída"),
    ("06_Size_Guide", "Luxusní sídlo"),
    ("07_Lifestyle_1", "Obyčejný byt"),
    ("08_Lifestyle_2", "Střední třída"),
]


# --- MOCKUPY SADY (B-7 přehledová koláž, B-9 hlášení selhání) ---

def make_mockups(images, names, marketing_dir, overview_caption=None):
    """Vyrobí sadu mockupů a vrátí (počet hotových, [názvy selhaných]).

    Každý mockup dostane jiný obraz (cyklicky) a jinou šablonu (bez opakování, dokud jsou k dispozici jiné).
    Je-li zadán `overview_caption`, je první obrázek sady přehledová koláž všech obrazů (hlavní obrázek
    listingu bundlu); když se koláž nepovede, použije se běžný mockup.
    """
    os.makedirs(marketing_dir, exist_ok=True)
    used, failed, done = set(), [], 0
    for index, (name, category) in enumerate(names):
        out_path = os.path.join(marketing_dir, f"{name}.jpg")
        ok = False
        if index == 0 and overview_caption:
            ok = create_bundle_overview(images, out_path, overview_caption)
        if not ok:
            ok = create_mockup(images[index % len(images)], out_path, category, used)
        if ok:
            done += 1
        else:
            failed.append(name)
    if failed:
        print(f"   ⚠️ Nevznikly mockupy ({len(failed)}/{len(names)}): {', '.join(failed)}. Listing bude mít méně obrázků.")
    return done, failed


def build_bundle(client, trend, prompts, progress=(10, 100)):
    """Jediná implementace sestavení bundlu (generování, tisky, mockupy, SEO, metadata).

    Args:
        client: Groq klient pro SEO texty (None = SEO se přeskočí a použijí se obecné texty).
        trend: {"bundle_theme", "visual_style", ...}
        prompts: seznam promptů (jeden obraz na prompt).
        progress: rozsah procent (od, do) pro hlášení průběhu.
    Returns:
        Cesta ke složce bundlu, nebo None, když se nevygeneroval žádný obraz. Při chybě nebo zrušení se
        rozpracovaná složka smaže (SKU se přesto spotřebuje, aby zůstalo unikátní).
    """
    import shutil

    lo, hi = progress

    def step(fraction, message):
        report(lo + (hi - lo) * fraction, message)

    theme = trend["bundle_theme"]
    total = len(prompts)
    sku = generate_sku("B")
    bundle_dir = create_product_folder(sku, theme)
    masters_dir = os.path.join(bundle_dir, "00_Masters")
    os.makedirs(masters_dir, exist_ok=True)
    old_print = os.path.join(bundle_dir, "01_Print_Files")
    print_dir = os.path.join(bundle_dir, "01_Print_Files_Ready")
    if os.path.exists(old_print):
        os.rename(old_print, print_dir)

    images = []
    try:
        print(f"\n🖼️  Začínám produkci {total} Art Printů do: {bundle_dir}")
        for i, prompt in enumerate(prompts, 1):
            check_cancel()
            step(0.6 * (i - 1) / max(total, 1), f"Generuji obraz {i}/{total}")
            print(f"\n--- Obraz {i}/{total} ---")
            img = generate_image(prompt)
            if not img:
                print(f"   ⚠️ Obraz {i}/{total} se nepodařilo vygenerovat, přeskakuji.")
                continue
            art_name = f"Art_{chr(65 + len(images))}"  # souvislé Art_A, Art_B, ... i při vynechaném obrazu
            img.save(os.path.join(masters_dir, f"{art_name}.png"))
            images.append(img)
            art_print_dir = os.path.join(print_dir, art_name)
            os.makedirs(art_print_dir, exist_ok=True)
            process_high_quality_print(img, art_print_dir, art_name)

        if not images:
            print("❌ Nepodařilo se vygenerovat žádný obrázek (zkontroluj POLLINATIONS_API_KEY a připojení) - bundle nebude dokončen.")
            shutil.rmtree(bundle_dir, ignore_errors=True)
            return None

        incomplete = len(images) < total
        warnings = []
        if incomplete:
            warnings.append(f"Bundle je neúplný: vygenerováno {len(images)} z {total} obrazů.")
            print(f"⚠️ {warnings[-1]}")

        check_cancel()
        step(0.65, "Tvorba mockupů")
        print(f"\n🎨 Tvorba prezentačních materiálů ({len(BUNDLE_MOCKUP_NAMES)} obrázků, první je přehled sady)...")
        _done, failed_mockups = make_mockups(images, BUNDLE_MOCKUP_NAMES, os.path.join(bundle_dir, "02_Marketing_Assets"),
                                             overview_caption=f"Set of {len(images)} Printable Wall Art")
        if failed_mockups:
            warnings.append("Nevznikly mockupy: " + ", ".join(failed_mockups))

        check_cancel()
        step(0.9, "SEO texty a metadata")
        metadata_dir = os.path.join(bundle_dir, "03_Metadata")
        seo = (generate_seo_text(client, trend, metadata_dir) if client else None) or {}
        listing_data = create_listing_data(
            sku=sku,
            title=seo.get("title") or f"{theme} Wall Art Bundle - Set of {len(images)} Printable Art"[:ETSY_TITLE_MAX],
            tags=seo.get("tags") or ["wall art", "printable", "digital download"],
            price=DEFAULT_PRICE_BUNDLE,
            description=seo.get("description", ""),
        )
        listing_data["images_generated"] = len(images)
        listing_data["images_planned"] = total
        if incomplete:
            listing_data["incomplete"] = True
        if warnings:
            listing_data["warnings"] = warnings
        with open(os.path.join(metadata_dir, "listing_data.json"), "w", encoding="utf-8") as f:
            json.dump(listing_data, f, indent=2, ensure_ascii=False)
    except BaseException:  # včetně zrušení úlohy: nenech ve skladu rozpracovaný bundle
        shutil.rmtree(bundle_dir, ignore_errors=True)
        raise

    print(f"\n✨ Bundle {sku} dokončen v: {bundle_dir}")
    return bundle_dir


# --- DORUČENÍ BUNDLU PŘES ODKAZ (B-4): Etsy dovolí max. 5 souborů á 20 MB ---

def _pdf_text(value):
    """Text do PDF (Helvetica, Latin-1): odstraní diakritiku a escapuje závorky a zpětná lomítka."""
    import unicodedata
    folded = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode("ascii")
    return folded.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def write_link_pdf(path, title, url, notes=()):
    """Zapíše jednostránkové PDF s klikací adresou ke stažení (PDF se sestaví ručně, bez dalších závislostí)."""
    if not re.match(r"^https?://\S+$", url or ""):
        raise ValueError("Odkaz ke stažení musí začínat http:// nebo https:// a nesmí obsahovat mezery.")
    ops = [f"BT /F1 22 Tf 60 770 Td ({_pdf_text(title)}) Tj ET"]
    y = 730
    for note in notes:
        ops.append(f"BT /F1 12 Tf 60 {y} Td ({_pdf_text(note)}) Tj ET")
        y -= 18
    y -= 14
    top = y + 14
    for start in range(0, len(url), 75):
        ops.append(f"BT /F1 11 Tf 60 {y} Td 0 0 0.8 rg ({_pdf_text(url[start:start + 75])}) Tj ET")
        y -= 15
    bottom = y + 8
    stream = "\n".join(ops)
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> "
        "/Contents 5 0 R /Annots [6 0 R] >>",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream",
        f"<< /Type /Annot /Subtype /Link /Rect [55 {bottom} 545 {top}] /Border [0 0 0] "
        f"/A << /S /URI /URI ({_pdf_text(url)}) >> >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n{body}\nendobj\n".encode("latin-1")
    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("latin-1")
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode("latin-1")
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n".encode("latin-1")
    with open(path, "wb") as f:
        f.write(out)


def _find_print_files(product_dir):
    """Vrátí (složka s tiskovými soubory, seřazený seznam [(cesta, velikost)]) nebo (None, [])."""
    for name in ("01_Print_Files_Ready", "01_Print_Files"):
        candidate = os.path.join(product_dir, name)
        if os.path.isdir(candidate):
            files = []
            for root, _dirs, names in os.walk(candidate):
                for n in sorted(names):
                    if n.lower().endswith(('.jpg', '.jpeg', '.png', '.pdf')):
                        full = os.path.join(root, n)
                        files.append((full, os.path.getsize(full)))
            return candidate, sorted(files)
    return None, []


def _read_listing_data(product_dir):
    try:
        with open(os.path.join(product_dir, "03_Metadata", "listing_data.json"), "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def get_download_url(product_dir):
    """Odkaz na plnou kvalitu (Drive/Dropbox), který uživatel uložil k bundlu; prázdný řetězec, když chybí."""
    return str((_read_listing_data(product_dir).get("delivery") or {}).get("download_url", "")).strip()


def prepare_download_archive(product_dir):
    """Zabalí všechny tiskové soubory v plné kvalitě do jednoho ZIPu (04_Delivery/<sku>_Full_Print_Files.zip).

    Tento ZIP uživatel nahraje na externí úložiště (Drive, Dropbox) a odkaz uloží u produktu.
    """
    sku = _read_listing_data(product_dir).get("sku") or os.path.basename(product_dir).split("_")[0]
    src_dir, files = _find_print_files(product_dir)
    if not files:
        print("❌ Ve složce produktu nejsou žádné tiskové soubory.")
        return None
    report(10, f"Balím {len(files)} souborů do ZIPu")
    out_dir = os.path.join(product_dir, "04_Delivery")
    os.makedirs(out_dir, exist_ok=True)
    zip_path = os.path.join(out_dir, f"{sku}_Full_Print_Files.zip")
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as zf:  # JPEG je již komprimovaný
        for index, (full, _size) in enumerate(files, 1):
            check_cancel()
            zf.write(full, arcname=os.path.relpath(full, src_dir))
            report(10 + 85 * index / len(files), f"Balím soubor {index}/{len(files)}")
    size_mb = os.path.getsize(zip_path) / 1024 / 1024
    print(f"📦 Hotovo: {zip_path} ({size_mb:.0f} MB). Nahraj ho na Drive/Dropbox a vlož odkaz u produktu ve Skladu.")
    report(100, "Hotovo")
    return zip_path


def build_external_delivery(product_dir, sku):
    """Doručení přes odkaz: vytvoří PDF s odkazem ke stažení plné kvality (jediný soubor pro Etsy).

    Returns:
        [cesta k PDF], nebo None, když u produktu chybí platný odkaz.
    """
    url = get_download_url(product_dir)
    if not url:
        print("❌ Bundle se nevejde do limitu Etsy (5 souborů x 20 MB) a doručuje se přes odkaz, ale u produktu chybí "
              "odkaz ke stažení. Připrav ZIP (tlačítko u produktu), nahraj ho na Drive/Dropbox a vlož odkaz.")
        return None
    out_dir = os.path.join(product_dir, "04_Delivery")
    os.makedirs(out_dir, exist_ok=True)
    pdf_path = os.path.join(out_dir, f"{sku}_Download_Your_Files.pdf")
    try:
        write_link_pdf(pdf_path, "Your printable wall art files", url, notes=(
            "Thank you for your purchase!",
            "Click the link below to download all print files in full quality (300 DPI).",
            "If the link does not open, copy it into your browser.",
        ))
    except ValueError as e:
        print(f"❌ {e}")
        return None
    print(f"📄 Připraveno PDF s odkazem ke stažení: {pdf_path}")
    return [pdf_path]


# --- SOLO: SEO z tématu (S-5) a archivace zdroje (S-6) ---

def load_topics():
    """Téma/klíčová slova k obrázkům ve frontě: {relativní cesta s '/': text}."""
    try:
        with open(TOPICS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}


def save_topics(topics):
    os.makedirs(os.path.dirname(TOPICS_PATH), exist_ok=True)
    tmp = TOPICS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(topics, f, indent=2, ensure_ascii=False)
    os.replace(tmp, TOPICS_PATH)


def generate_solo_seo(client, title_hint, topic):
    """Titulek, popis a až 13 tagů pro jeden obraz z jeho názvu a tématu/klíčových slov (bez vision modelu).

    Returns:
        {"title", "description", "tags"} (viz parse_seo_text) nebo None.
    """
    prompt = (
        "Write Etsy Listing Info for ONE printable wall art print (instant digital download).\n"
        f"Artwork name: {title_hint}\n"
        f"Subject / keywords from the seller: {topic.strip() or '(none - rely only on the artwork name)'}\n"
        "Use only what the name and keywords say; do not invent details about the image.\n"
        "Output Structure:\n"
        "TITLE: (SEO friendly, plain text, max 140 characters, no emojis)\n"
        "DESCRIPTION: (Sales copy, plain text, 100-200 words, mention instant digital download and the included "
        "print sizes; do NOT mention AI)\n"
        "TAGS: (13 tags comma separated, each max 20 characters)\n"
    )
    seo = parse_seo_text(groq_complete(client, prompt))
    return seo if (seo["title"] or seo["description"] or seo["tags"]) else None


def archive_queue_file(rel_path):
    """Přesune jeden zdrojový obrázek z fronty do 03_Archive/RRRR_MM (podsložky se zploští: Batch__x.png)."""
    import shutil
    target_dir = os.path.join(ARCHIVE_ROOT_DIR, datetime.now().strftime("%Y_%m"))
    os.makedirs(target_dir, exist_ok=True)
    src = os.path.join(SOLO_INPUT_DIR, rel_path)
    dst = os.path.join(target_dir, rel_path.replace(os.sep, "__").replace("/", "__"))
    if os.path.exists(dst):
        base, ext = os.path.splitext(dst)
        dst = f"{base}_{datetime.now().strftime('%H%M%S')}{ext}"
    shutil.move(src, dst)  # funguje i mezi souborovými systémy (os.rename ne)
    return dst


def _remove_empty_queue_dirs():
    """Smaže prázdné podsložky (Batch_*) ve frontě."""
    for entry in os.listdir(SOLO_INPUT_DIR):
        sub = os.path.join(SOLO_INPUT_DIR, entry)
        if os.path.isdir(sub) and not os.listdir(sub):
            os.rmdir(sub)


ETSY_TAXONOMY_PATH = ["Art & Collectibles", "Prints", "Digital Prints"]
ETSY_MAX_FILES = 5


def _find_node_by_name(nodes, name):
    """Hledá do hloubky uzel taxonomie podle názvu (case-insensitive)."""
    for node in nodes or []:
        if str(node.get("name", "")).lower() == name.lower():
            return node
        found = _find_node_by_name(node.get("children"), name)
        if found:
            return found
    return None


def resolve_taxonomy_id(client):
    """Zjistí taxonomy_id pro digitální tisky: ENV ETSY_TAXONOMY_ID > cesta v taxonomii > hledání názvu."""
    env_value = os.getenv("ETSY_TAXONOMY_ID", "").strip()
    if env_value.isdigit():
        return int(env_value)
    tax_id = client.find_taxonomy_id(ETSY_TAXONOMY_PATH)
    if tax_id:
        return tax_id
    node = _find_node_by_name(client.get_taxonomy_nodes(), ETSY_TAXONOMY_PATH[-1])
    return node.get("id") if node else None


def build_listing_payload(data: dict, taxonomy_id: int) -> dict:
    """Sestaví payload pro createDraftListing (titulek max 140, max 13 tagů, AI disclosure v popisu)."""
    title = _truncate_title(data.get("title") or "Digital Printable Wall Art")
    description = (data.get("description_generated") or "").strip() or "Digital printable wall art. Instant download."
    if AI_DISCLOSURE_TEXT.strip() not in description:
        description += AI_DISCLOSURE_TEXT

    tags = []
    for raw in data.get("seo_tags", []):
        tag = str(raw).strip()[:20]
        if tag and tag.lower() not in [t.lower() for t in tags]:
            tags.append(tag)
    tags = tags[:13]

    return {
        "quantity": 999,
        "title": title,
        "description": description,
        "price": data.get("pricing", {}).get("amount", DEFAULT_PRICE_SINGLE),
        "who_made": WhoMade.I_DID.value,
        "when_made": WhenMade.YEARS_2020_2026.value,
        "taxonomy_id": taxonomy_id,
        "type": ListingType.DOWNLOAD.value,
        "is_supply": "false",
        "tags": ",".join(tags),
    }


def build_delivery_zips(product_dir: str, sku: str):
    """Zabalí tiskové soubory do ZIPů pro Etsy (max 5 souborů á 20 MB) do 04_Delivery/.

    Returns:
        Seznam cest k ZIPům, nebo None pokud se soubory do limitů Etsy nevejdou / chybí.
    """
    src_dir = None
    for name in ("01_Print_Files_Ready", "01_Print_Files"):
        candidate = os.path.join(product_dir, name)
        if os.path.isdir(candidate):
            src_dir = candidate
            break
    if not src_dir:
        print("❌ Nenalezena složka s tiskovými soubory (01_Print_Files / 01_Print_Files_Ready).")
        return None

    files = []
    for root, _dirs, names in os.walk(src_dir):
        for n in sorted(names):
            if n.lower().endswith(('.jpg', '.jpeg', '.png', '.pdf')):
                full = os.path.join(root, n)
                files.append((full, os.path.getsize(full)))
    files.sort(key=lambda item: item[0])
    if not files:
        print(f"❌ Ve složce {src_dir} nejsou žádné tiskové soubory.")
        return None

    limit = int(MAX_ZIP_BYTES)
    parts, current, current_size = [], [], 0
    for full, size in files:
        if size > limit:
            print(f"❌ Soubor {os.path.basename(full)} ({size / 1024 / 1024:.1f} MB) se nevejde do limitu Etsy (20 MB).")
            return None
        if current and current_size + size > limit:
            parts.append(current)
            current, current_size = [], 0
        current.append((full, size))
        current_size += size
    if current:
        parts.append(current)

    if len(parts) > ETSY_MAX_FILES:
        total_mb = sum(s for _f, s in files) / 1024 / 1024
        print(f"❌ Tiskové soubory mají {total_mb:.0f} MB a vyžadovaly by {len(parts)} ZIPů; Etsy povoluje max. "
              f"{ETSY_MAX_FILES} souborů á 20 MB. Sniž počet/velikost tiskových souborů nebo doručuj přes odkaz.")
        return None

    out_dir = os.path.join(product_dir, "04_Delivery")
    os.makedirs(out_dir, exist_ok=True)
    for old in os.listdir(out_dir):
        if old.lower().endswith(".zip"):
            os.remove(os.path.join(out_dir, old))

    zip_paths = []
    for idx, group in enumerate(parts, 1):
        suffix = "" if len(parts) == 1 else f"_Part{idx}"
        zip_path = os.path.join(out_dir, f"{sku}_Print_Files{suffix}.zip")
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_STORED) as zf:  # JPEG je již komprimovaný
            for full, _size in group:
                zf.write(full, arcname=os.path.relpath(full, src_dir))
        zip_paths.append(zip_path)
    print(f"📦 Připraveno {len(zip_paths)} ZIP(ů) k doručení ({len(files)} souborů).")
    return zip_paths


def _save_etsy_state(metadata_path: str, data: dict, listing_id, state: str, files_uploaded: bool) -> None:
    """Zapíše do listing_data.json stav na Etsy (brní duplicitám a umožňuje pozdější zveřejnění)."""
    data["etsy"] = {"listing_id": listing_id, "state": state, "files_uploaded": files_uploaded}
    try:
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except OSError as e:
        print(f"   ⚠️ Stav listingu se nepodařilo uložit do {metadata_path}: {e}")


def activate_etsy_listing(product_dir: str) -> bool:
    """Zveřejní (state=active) dříve nahraný draft - jen pokud jsou nahrané digitální soubory."""
    if not EtsyClient:
        print("❌ Chyba: Modul etsy_api není dostupný.")
        return False
    metadata_path = os.path.join(product_dir, "03_Metadata", "listing_data.json")
    try:
        with open(metadata_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        print(f"❌ Metadata nelze načíst: {e}")
        return False

    etsy_state = data.get("etsy") or {}
    listing_id = etsy_state.get("listing_id")
    if not listing_id:
        print("❌ Produkt nemá draft na Etsy - nejdřív ho nahraj.")
        return False
    if etsy_state.get("state") == "active":
        print(f"ℹ️ Listing {listing_id} je již zveřejněn.")
        return True
    if not etsy_state.get("files_uploaded"):
        print("❌ Digitální soubory nejsou nahrané - zveřejnění by vytvořilo nedoručivý listing.")
        return False
    try:
        client = EtsyClient.from_env()
    except RuntimeError as e:
        print(f"❌ Etsy autorizace: {e}")
        return False
    if client.update_listing_state(listing_id, ListingState.ACTIVE.value):
        _save_etsy_state(metadata_path, data, listing_id, "active", True)
        return True
    return False


def offer_publish_cli(product_dir: str, sku: str) -> None:
    """CLI dialog: nahrát draft na Etsy a poté (odděleně potvrzené) zveřejnit."""
    choice = input(f"\n❓ Chceš tento produkt ({sku}) nahrát na Etsy jako draft? (y/n): ").strip().lower()
    if choice != 'y':
        return
    if not publish_to_etsy(product_dir):
        return
    choice = input(f"\n❓ Zveřejnit listing {sku} (Etsy účtuje poplatek za zveřejnění)? Zkontroluj draft v Etsy. (y/n): ").strip().lower()
    if choice == 'y':
        activate_etsy_listing(product_dir)


def publish_to_etsy(product_dir):
    """Nahraje produkt (draft) na Etsy na základě dat ve složce produktu."""
    if not EtsyClient:
        print("❌ Chyba: Modul etsy_api není dostupný.")
        return False

    if not ETSY_SHOP_ID:  # ETSY_API_KEY může být i jen v oauth/.env (kontroluje EtsyClient.from_env)
        print("⚠️ Chybí ETSY_API_KEY nebo ETSY_SHOP_ID v .env souboru.")
        return False

    metadata_path = os.path.join(product_dir, "03_Metadata", "listing_data.json")
    if not os.path.exists(metadata_path):
        print(f"❌ Metadata nenalezena: {metadata_path}")
        return False

    with open(metadata_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    print(f"\n📤 NAHRÁVÁNÍ NA ETSY: {data.get('title')}")
    try:
        # Tokeny se načítají z oauth/etsy_tokens.json a automaticky se obnovují
        client = EtsyClient.from_env()
    except RuntimeError as e:
        print(f"❌ Etsy autorizace: {e}")
        return False
    
    # 1. Příprava dat pro listing
    existing_id = (data.get("etsy") or {}).get("listing_id")
    if existing_id:
        print(f"⚠️ Produkt už byl na Etsy nahrán (listing_id {existing_id}) - duplicitní nahrání zablokováno. "
              f"Pro nový pokus smaž draft na Etsy a klíč 'etsy' v {metadata_path}.")
        return False

    report(5, "Zjišťuji kategorii na Etsy")
    taxonomy_id = resolve_taxonomy_id(client)
    if not taxonomy_id:
        print("❌ Nepodařilo se zjistit taxonomy_id (kategorii). Nastav ETSY_TAXONOMY_ID v .env.")
        return False

    # Digitální soubory připravíme předem - když se nevejdou do limitů Etsy, nevytváříme zbytečný draft
    report(15, "Připravuji ZIP soubory")
    if data.get("incomplete"):
        print("⚠️ Bundle je označen jako neúplný (méně obrazů, než bylo plánováno) - zkontroluj titulek a popis.")
    sku_value = data.get("sku", "product")
    if sku_value.endswith("-B"):  # bundle se do limitu Etsy nevejde: kupující dostane PDF s odkazem na plné soubory
        delivery_files = build_external_delivery(product_dir, sku_value)
    else:
        delivery_files = build_delivery_zips(product_dir, sku_value)
    if not delivery_files:
        return False

    listing_payload = build_listing_payload(data, taxonomy_id)

    # 2. Vytvoření listingu
    report(35, "Vytvářím draft na Etsy")
    listing_id = client.create_listing(listing_payload)
    if not listing_id:
        return False
    _save_etsy_state(metadata_path, data, listing_id, "draft", False)

    # 2b. Digitální soubory (to, co kupující dostane po nákupu)
    files_ok = True
    report(45, "Nahrávám digitální soubory")
    for i, zip_path in enumerate(delivery_files, 1):
        if not client.upload_listing_file(listing_id, zip_path, rank=i):
            files_ok = False
    _save_etsy_state(metadata_path, data, listing_id, "draft", files_ok)

    # 3. Nahrání obrázků z 02_Marketing_Assets
    marketing_dir = os.path.join(product_dir, "02_Marketing_Assets")
    if os.path.exists(marketing_dir):
        # Najít JPG soubory (mockupy) a seřadit je podle názvu (01_Main_Thumbnail bude první)
        images = sorted([f for f in os.listdir(marketing_dir) if f.lower().endswith(('.jpg', '.jpeg'))])
        
        print(f"🖼️ Nahrávám {len(images)} obrázků k listingu {listing_id}...")
        for i, img_name in enumerate(images, 1):
            report(70 + 28 * i / max(len(images), 1), f"Nahrávám obrázek {i}/{len(images)}")
            img_path = os.path.join(marketing_dir, img_name)
            client.upload_listing_image(listing_id, img_path, rank=i)

    if not files_ok:
        print(f"⚠️ Draft {listing_id} vznikl, ale digitální soubory se nenahrály - NEZVEŘEJŇUJ ho; "
              "dokonči ho ručně na Etsy nebo ho smaž.")
        return False

    print(f"✅ Produkt {data.get('sku')} byl úspěšně nahrán na Etsy jako draft (listing_id {listing_id}).")
    return True

def run_generation_mode(theme=None, interactive=True):
    """Automaticky generuje Bundle s 5 obrazy dle pravidla.md struktury"""
    print(f"\n🚀 SPUŠTĚNÍ AUTOMATICKÉHO GENERÁTORU {datetime.now().strftime('%H:%M')}")
    if not GROQ_API_KEY:
        print("❌ Chybí GROQ_API_KEY v .env souboru - generátor nelze spustit.")
        return False
    client = make_groq_client()

    ensure_dirs()
    report(3, "Průzkum trhu")
    if theme:
        trend = {"bundle_theme": theme, "visual_style": "cohesive collection, centered composition, rich detail, harmonious colors", "target_audience": ""}
    else:
        trend = market_research(client)
    check_cancel()

    report(8, "Návrh promptů")
    try:
        prompts = get_prompts(client, trend)
    except Exception as e:  # noqa: BLE001 - bez promptů by se plýtvalo kredity na 5 stejných obrazů
        print(f"❌ Generování zastaveno: nelze získat prompty od Groq ({e}).")
        return False
    check_cancel()

    bundle_dir = build_bundle(client, trend, prompts, progress=(10, 100))
    if not bundle_dir:
        return False
    report(100, "Hotovo")

    # Dotaz na nahrání na Etsy
    if EtsyClient and interactive:
        offer_publish_cli(bundle_dir, os.path.basename(bundle_dir).split("_")[0])
    return bundle_dir

def run_solo_mode(interactive=True):
    """Zpracuje obrázky z 00_Input_Queue/_To_Edit/ a vytvoří Singles produkty"""
    print(f"\n🛠️ SPUŠTĚNÍ SOLO ÚPRAV")
    ensure_dirs()
    print(f"Hledám obrázky ve složce: {SOLO_INPUT_DIR}")
    
    # Zajistit existenci vstupní složky
    if not os.path.exists(SOLO_INPUT_DIR):
        print(f"❌ Složka '_To_Edit' neexistuje! Vytvářím ji...")
        os.makedirs(SOLO_INPUT_DIR, exist_ok=True)
        print("📁 Složka vytvořena. Vložte do ní obrázky a spusťte skript znovu.")
        return
        
    # Obrázky i z podsložek (např. Batch_* z generování ze seznamu)
    files = sorted(
        os.path.relpath(os.path.join(root, name), SOLO_INPUT_DIR)
        for root, _dirs, names in os.walk(SOLO_INPUT_DIR)
        for name in names
        if name.lower().endswith(('.png', '.jpg', '.jpeg'))
    )
    
    if not files:
        print("⚠️ Ve složce nejsou žádné obrázky.")
        return {"ok": 0, "failed": 0}
        
    print(f"Nalezeno {len(files)} obrázků ke zpracování.")
    ok_count = failed_count = 0
    client = None
    if GROQ_API_KEY:
        try:
            client = make_groq_client()
        except Exception as e:  # noqa: BLE001
            print(f"   ⚠️ Groq klient nelze vytvořit ({e}) - SEO texty se nevygenerují.")
    else:
        print("   ⚠️ Chybí GROQ_API_KEY - SEO texty se nevygenerují, použije se obecný titulek a tagy.")
    topics = load_topics()

    for file_index, filename in enumerate(files):
        check_cancel()
        report(100 * file_index / len(files), f"Zpracovávám {filename} ({file_index + 1}/{len(files)})")
        print(f"\n--- Zpracovávám: {filename} ---")
        file_path = os.path.join(SOLO_INPUT_DIR, filename)
        base_name = os.path.splitext(os.path.basename(filename))[0]
        safe_name = _ascii_slug(base_name) or "Image"
        product_dir = None
        topic_key = filename.replace(os.sep, "/")
        
        try:
            with Image.open(file_path) as img:
                img = ImageOps.exif_transpose(img)  # fotky z telefonu: respektovat orientaci z EXIF
                if min(img.size) < 1500:
                    print(f"   ⚠️ Nízké rozlišení {img.size[0]}x{img.size[1]} px - velké tiskové formáty budou rozmazané.")
                # 1. Generování SKU pro Single produkt
                sku = generate_sku("S")
                product_dir = create_product_folder(sku, safe_name)
                
                # 2. Uložit Master Source (záloha originálu)
                master_path = os.path.join(product_dir, "00_Master_Source.png")
                img.save(master_path)
                
                # 3. HQ Printy do 01_Print_Files
                print_dir = os.path.join(product_dir, "01_Print_Files")
                process_high_quality_print(img, print_dir, sku)
                
                # 4. Mockupy do 02_Marketing_Assets (8 mockupů pro Etsy listing)
                marketing_dir = os.path.join(product_dir, "02_Marketing_Assets")
                print(f"   🎨 Generuji {len(SINGLE_MOCKUP_NAMES)} mockupů...")
                _done, failed_mockups = make_mockups([img], SINGLE_MOCKUP_NAMES, marketing_dir)
                
                # 5. Metadata do 03_Metadata
                metadata_dir = os.path.join(product_dir, "03_Metadata")
                seo = {}
                if client:
                    try:
                        seo = generate_solo_seo(client, _title_from_filename(base_name), topics.get(topic_key, "")) or {}
                    except Exception as e:  # noqa: BLE001 - SEO nesmí shodit celý produkt
                        print(f"   ⚠️ SEO pro {filename} selhalo ({e}), použiji obecné texty.")
                listing_data = create_listing_data(
                    sku=sku,
                    title=seo.get("title") or f"{_title_from_filename(base_name)} Wall Art - Digital Download Printable"[:ETSY_TITLE_MAX],
                    tags=seo.get("tags") or ["wall art", "printable", "digital download"],
                    price=DEFAULT_PRICE_SINGLE,
                    description=seo.get("description", ""),
                )
                listing_data["seo_generated"] = bool(seo)
                with open(os.path.join(metadata_dir, "listing_data.json"), "w", encoding="utf-8") as f:
                    json.dump(listing_data, f, indent=2, ensure_ascii=False)
                
                if failed_mockups:
                    listing_data["warnings"] = ["Nevznikly mockupy: " + ", ".join(failed_mockups)]
                    with open(os.path.join(metadata_dir, "listing_data.json"), "w", encoding="utf-8") as f:
                        json.dump(listing_data, f, indent=2, ensure_ascii=False)
                print(f"   ✅ Single {sku} vytvořen!")

        except Exception as e:
            failed_count += 1
            print(f"❌ Chyba při zpracování {filename}: {e}")
            if product_dir and os.path.isdir(product_dir):  # nenech ve skladu rozpracovaný produkt
                import shutil
                shutil.rmtree(product_dir, ignore_errors=True)
        else:
            ok_count += 1
            # S-6: zpracovaný zdroj přesunout do archivu, ať se při dalším běhu nezpracuje znovu (duplicitní produkt)
            try:
                archive_queue_file(filename)
                if topics.pop(topic_key, None) is not None:
                    save_topics(topics)
            except Exception as e:  # noqa: BLE001 - produkt je hotový, archivace je jen údržba
                print(f"   ⚠️ Zdroj {filename} se nepodařilo archivovat ({e}), zůstal ve frontě.")
            if EtsyClient and interactive:
                offer_publish_cli(product_dir, sku)

    try:
        _remove_empty_queue_dirs()
    except OSError:
        pass
    report(100, "Hotovo")
    print(f"\n✨ Hotovo: {ok_count} produktů, selhalo {failed_count}. Produkty jsou v: {SINGLES_DIR}")
    return {"ok": ok_count, "failed": failed_count}

def _open_file_crossplatform(path: str) -> None:
    """Otevře soubor v defaultní aplikaci na Win/mac/Linux (nahrazuje Windows-only os.startfile)."""
    try:
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
        print(f"   👁️  Otevřeno pro kontrolu: {path}")
    except Exception as e:
        print(f"   ⚠️  Nepodařilo se otevřít {path}: {e}")


def run_mockup_test_mode():
    print(f"\n🧪 SPUŠTĚNÍ TESTOVÁNÍ MOCKUPŮ")
    
    # 1. Kontrola testovacího obrázku
    if not os.path.exists(TEST_ART_PATH):
        print(f"❌ Testovací obrázek neexistuje: {TEST_ART_PATH}")
        print("   Nastav cestu přes TEST_ART_PATH v .env souboru.")
        return

    # 2. Načtení šablon
    if not os.path.exists(MOCKUP_TEMPLATES_DIR):
        print(f"❌ Složka šablon neexistuje: {MOCKUP_TEMPLATES_DIR}")
        return

    templates = [f for f in os.listdir(MOCKUP_TEMPLATES_DIR) if f.lower().endswith('.png')]
    if not templates:
        print("❌ Žádné šablony nenalezeny.")
        return

    print("\nDostupné šablony:")
    for i, t in enumerate(templates, 1):
        status = "✅ Konfigurováno" if find_template_config(t) else "⚠️ Bez konfigurace"
        print(f"  {i}. {t} ({status})")
    
    # 3. Výběr šablony
    try:
        choice_input = input("\nVyber číslo šablony (nebo 'q' pro konec): ").strip()
        if choice_input.lower() == 'q':
            return
        
        choice = int(choice_input)
        if 1 <= choice <= len(templates):
            selected_template = templates[choice-1]
        else:
            print("❌ Neplatná volba.")
            return
    except ValueError:
        print("❌ Neplatný vstup.")
        return

    # 4. Zpracování
    template_path = os.path.join(MOCKUP_TEMPLATES_DIR, selected_template)
    output_filename = f"TEST_MOCKUP_{os.path.splitext(selected_template)[0]}.jpg"
    output_path = os.path.join(SCRIPT_DIR, output_filename)
    
    print(f"\nGeneruji test: {selected_template}...")
    
    template_config = find_template_config(selected_template)
    if not template_config:
        print(f"⚠️ Konfigurace pro {selected_template} nenalezena. Použiji default 400x300.")
        template_config = DEFAULT_MOCKUP_CONFIG
    
    try:
        with Image.open(TEST_ART_PATH) as art:
            render_mockup(art, template_path, template_config).save(output_path, quality=95)
        print(f"✅ Hotovo! Uloženo jako: {output_path}")
        
        # Otevření pro kontrolu (multiplatformní)
        _open_file_crossplatform(output_path)
        
    except Exception as e:
        print(f"❌ Chyba: {e}")

def run_list_mode():
    """Načte prompts.json a vygeneruje buď singly nebo bundles dle obsahu"""
    json_path = PROMPTS_JSON_PATH

    print(f"\n📋 SPUŠTĚNÍ GENERACE ZE SEZNAMU")
    print(f"Hledám soubor: {json_path}")
    result = {"ok": 0, "failed": 0}

    if not os.path.exists(json_path):
        print(f"❌ Soubor 'prompts.json' nebyl nalezen!")
        return

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
            # A. NOVÝ REŽIM: Bundles
            if "bundles" in data:
                print(f"📦 Nalezeno {len(data['bundles'])} definic pro BUNDLES.")
                
                for i, bundle_def in enumerate(data["bundles"], 1):
                    theme = bundle_def.get("theme_name", f"Bundle_{i}")
                    style = bundle_def.get("visual_style", "")
                    prompts = bundle_def.get("prompts", [])
                    
                    if not prompts:
                        print(f"⚠️ Bundle '{theme}' nemá žádné prompty, přeskakuji.")
                        continue
                        
                    check_cancel()
                    print(f"\n🚀 Generuji Bundle {i}/{len(data['bundles'])}: '{theme}'")
                    print(f"🎨 Styl: {style}")

                    seo_client = None
                    try:
                        seo_client = make_groq_client()
                    except Exception as e:  # noqa: BLE001
                        print(f"   ⚠️ SEO generování bude přeskočeno (Groq není dostupný): {e}")
                    n_bundles = len(data["bundles"])
                    bundle_dir = build_bundle(
                        seo_client,
                        {"bundle_theme": theme, "visual_style": style, "target_audience": ""},
                        prompts,
                        progress=(100 * (i - 1) / n_bundles, 100 * i / n_bundles),
                    )
                    result["ok" if bundle_dir else "failed"] += 1

            # B. STARÝ REŽIM: Singles (tasks/prompts)
            elif "tasks" in data or "prompts" in data:
                if "tasks" in data:
                    tasks = data["tasks"]
                else:
                    tasks = [{"prompt": p, "filename": None} for p in data["prompts"]]
                
                print(f"🖼️ Nalezeno {len(tasks)} úkolů pro SINGLE obrazy.")
                
                # Vytvoříme batch složku v Input Queue
                timestamp_batch = int(time.time())
                batch_date = datetime.now().strftime("%Y-%m-%d_%H-%M")
                batch_dir = os.path.join(TO_EDIT_DIR, f"Batch_{batch_date}") # Ukládáme do _To_Edit
                os.makedirs(batch_dir, exist_ok=True)
                
                print(f"   Generuji do: {batch_dir}")

                for i, item in enumerate(tasks, 1):
                    prompt = item.get("prompt")
                    custom_name = item.get("filename")
                    
                    if not prompt:
                        continue

                    check_cancel()
                    report(100 * (i - 1) / len(tasks), f"Generuji obraz {i}/{len(tasks)}")
                    print(f"\n--- Generuji {i}/{len(tasks)} ---")
                    print(f"📝 Prompt: {prompt[:60]}...")
                    
                    img = generate_image(prompt)

                    if img:
                        if custom_name:
                            safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', custom_name)
                            filename = f"{safe_name}.png"
                        else:
                            safe_prompt = re.sub(r'[^a-zA-Z0-9]', '', prompt)[:20]
                            filename = f"Batch_{timestamp_batch}_{i}_{safe_prompt}.png"
                            
                        save_path = os.path.join(batch_dir, filename)
                        img.save(save_path)
                        print(f"   ✅ Uloženo: {filename}")
                        result["ok"] += 1
                    else:
                        result["failed"] += 1
                
                print("\n✨ Hotovo! Obrázky jsou v '00_Input_Queue/_To_Edit'.")
                print("👉 Spusťte volbu 2 (SOLO) pro jejich zpracování na produkty.")
            
            else:
                print("⚠️ JSON neobsahuje klíče 'bundles', 'tasks' ani 'prompts'.")

    except Exception as e:
        print(f"❌ Chyba při zpracování JSON: {e}")
        result["failed"] += 1
    return result

def run_config_server():
    """Spustí lokální HTTP server pro konfiguraci"""
    os.chdir(SCRIPT_DIR)  # Zajistí, že server vidí soubory ve složce skriptu
    PORT = 8000
    
    class ConfigHandler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            # Pokud je požadavek na root, zkus najít mereni.html v aktuálním adresáři
            if self.path == '/':
                self.path = '/mereni.html'
            return super().do_GET()

        def do_POST(self):
            if self.path == '/save_config':
                content_length = int(self.headers['Content-Length'])
                post_data = self.rfile.read(content_length)
                try:
                    data = json.loads(post_data.decode('utf-8'))
                    filename = data.get('filename')
                    corners = data.get('corners')
                    
                    if not filename or not corners:
                        raise ValueError("Chybí filename nebo corners")

                    # Najdi a aktualizuj šablonu
                    template = find_template_config(filename)
                    updated = template is not None
                    if updated:
                        template['corners'] = corners
                    
                    if updated:
                        save_templates(MOCKUP_TEMPLATES)
                        self.send_response(200)
                        self.send_header('Content-type', 'application/json')
                        self.end_headers()
                        self.wfile.write(json.dumps({'status': 'ok', 'message': f'Uloženo pro {filename}'}).encode('utf-8'))
                        print(f"   💾 Uložena konfigurace pro: {filename}")
                    else:
                        self.send_response(404)
                        self.send_header('Content-type', 'application/json')
                        self.end_headers()
                        self.wfile.write(json.dumps({'status': 'error', 'message': 'Šablona nenalezena'}).encode('utf-8'))
                
                except Exception as e:
                    self.send_response(500)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({'status': 'error', 'message': str(e)}).encode('utf-8'))
            else:
                self.send_response(404)
                self.end_headers()

    print(f"\n🌐 SPUŠTĚNÍ KALIBRAČNÍHO SERVERU")
    print(f"Otevírám prohlížeč na http://localhost:{PORT}/mereni.html")
    print("Pro ukončení stiskni Ctrl+C v terminálu.")
    
    # Auto-open browser
    webbrowser.open(f"http://localhost:{PORT}/mereni.html")

    
    with socketserver.TCPServer(("", PORT), ConfigHandler) as httpd:
        print(f"Běžím na portu {PORT}...")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n🛑 Server ukončen.")

def archive_old_files():
    """Přesune zpracované soubory z _To_Edit do 03_Archive/YYYY_MM"""
    # Cílová složka archivu dle pravidla.md: 03_Archive/YYYY_MM
    month_folder = datetime.now().strftime("%Y_%m")
    archive_target = os.path.join(ARCHIVE_ROOT_DIR, month_folder)
    os.makedirs(archive_target, exist_ok=True)
        
    print(f"\n📦 ARCHIVACE STARÝCH SOUBORŮ")
    print(f"Zdroj: {SOLO_INPUT_DIR}")
    print(f"Cíl: {archive_target}")
    
    # Soubory z kořene i z podsložek (Batch_*) - jako je zobrazuje fronta v GUI
    files = []
    for root, _dirs, names in os.walk(SOLO_INPUT_DIR):
        for n in names:
            if n.lower().endswith(('.png', '.jpg', '.jpeg', '.txt', '.json')):
                files.append(os.path.relpath(os.path.join(root, n), SOLO_INPUT_DIR))
    
    if not files:
        print("⚠️  Žádné soubory k archivaci ve vstupní složce.")
        return

    print(f"Přesouvám {len(files)} souborů do: {archive_target}...")
    
    count = 0
    topics = load_topics()
    for f in files:
        try:
            archive_queue_file(f)
            topics.pop(f.replace(os.sep, "/"), None)
            count += 1
        except Exception as e:
            print(f"❌ Chyba při přesunu {f}: {e}")
    try:
        save_topics(topics)
    except OSError as e:
        print(f"⚠️ Témata se nepodařilo uložit: {e}")

    # prázdné Batch_* složky po přesunu uklidit
    _remove_empty_queue_dirs()
            
    print(f"✅ Hotovo! Archivováno {count} souborů do {month_folder}.")

def main():
    """Hlavní nabídka (jediná; dříve existovala duplicitní nepoužitá verze)."""
    ensure_dirs()
    while True:
        print("\n" + "="*40)
        print("  SUPER ROBOT GENERATOR - ENTRY MENU")
        print("="*40)
        print("1. Spustit Generátor (Flow: Market -> Prompts -> Art -> Mockups -> SEO)")
        print("2. Spustit SOLO úpravy (Složka 00_Input_Queue/_To_Edit -> Hotovo)")
        print("3. Generovat ze seznamu (prompts.json -> Art -> Mockups)")
        print("4. Procházet složky a tvořit mockupy (Browser Mode)")
        print("5. Testování mockup (jeden obrázek + výběr šablony)")
        print("6. Spustit Kalibrační Server (mereni.html)")
        print("7. Archivovat staré soubory (v _To_Edit)")
        print("q. Ukončit")
        print("-" * 40)
        
        choice = input("Tvá volba: ").strip().lower()
        
        if choice == '1':
            run_generation_mode()
        elif choice == '2':
            run_solo_mode()
        elif choice == '3':
            run_list_mode()
        elif choice == '4':
            browse_and_create_mockup()
        elif choice == '5':
            run_mockup_test_mode()
        elif choice == '6':
            run_config_server()
        elif choice == '7':
            archive_old_files()
        elif choice == 'q':
            print("👋 Ahoj!")
            break
        else:
            print("❌ Neplatná volba. Zkus to znovu.")


if __name__ == "__main__":
    main()
