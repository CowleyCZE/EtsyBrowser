import os
import time
import random
import requests
import urllib.parse
import json
import re
from groq import Groq
from PIL import Image, ImageOps, ImageFilter
from datetime import datetime
import io
import numpy as np
from dotenv import load_dotenv

import http.server
import socketserver
import webbrowser

# Načtení environment proměnných
load_dotenv()

# Import modulu Etsy
try:
    from etsy_api import EtsyClient
except ImportError:
    EtsyClient = None

# --- 1. KONFIGURACE ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY") 
GEMINI_GEN_API_KEY = os.getenv("GEMINI_GEN_API_KEY")

# Etsy konfigurace
ETSY_API_KEY = os.getenv("ETSY_API_KEY")
ETSY_SHOP_ID = os.getenv("ETSY_SHOP_ID")
ETSY_ACCESS_TOKEN = os.getenv("ETSY_ACCESS_TOKEN")

# Nastavení cest (Reflektuje strukturu: EtsyBrowser / automation / script)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__)) 
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)        # .../EtsyBrowser/

# === NOVÁ STRUKTURA DLE integrace ===
# Data a konfigurace
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
CONFIGS_DIR = DATA_DIR  # Přesměrováno na data
TEMPLATES_JSON_PATH = os.path.join(DATA_DIR, "mockup_templates.json")
PROMPTS_JSON_PATH = os.path.join(DATA_DIR, "prompts.json")

# 00_Input_Queue - Vstupní fronta
INPUT_QUEUE_DIR = os.path.join(PROJECT_ROOT, "automation", "00_Input_Queue") # Cesta uvnitř automation pro bot-specific data
os.makedirs(INPUT_QUEUE_DIR, exist_ok=True)
TO_EDIT_DIR = os.path.join(INPUT_QUEUE_DIR, "_To_Edit")
BATCH_LISTS_DIR = os.path.join(INPUT_QUEUE_DIR, "_Batch_Lists")

# 01_System_Core - Systémové jádro (= tento skript)
SYSTEM_CORE_DIR = SCRIPT_DIR
ASSETS_DIR = os.path.join(PROJECT_ROOT, "images") # Použít složku images v kořenu
TEMPLATES_MOCKUP_DIR = os.path.join(SYSTEM_CORE_DIR, "1_Mockup_Sablony")

# 02_Warehouse - Hotové produkty
WAREHOUSE_DIR = os.path.join(PROJECT_ROOT, "automation", "02_Warehouse")
os.makedirs(WAREHOUSE_DIR, exist_ok=True)
SINGLES_DIR = os.path.join(WAREHOUSE_DIR, "Singles")
BUNDLES_DIR = os.path.join(WAREHOUSE_DIR, "Bundles")

# 03_Archive - Archiv
ARCHIVE_ROOT_DIR = os.path.join(PROJECT_ROOT, "automation", "03_Archive")
os.makedirs(ARCHIVE_ROOT_DIR, exist_ok=True)

# Legacy aliases (zpětná kompatibilita)
OUTPUT_DIR = SINGLES_DIR  # Staré OUTPUT_DIR nyní ukazuje na Singles

def generate_image(prompt):
    print(f"   Generování obrazu (Pollinations.ai Flux)...")
    
    # API Key (Pollinations - Flux Schnell)
    api_key = "sk_SbG7Wyh9ty8tGtiN5H3BJxvLpSl8iliH"
    
    # Construct URL for GET request
    # Format: https://gen.pollinations.ai/image/{prompt}?model=flux&width={width}&height={height}&seed={seed}
    base_url = "https://gen.pollinations.ai/image"
    
    # Parameters
    params = {
        "model": "flux",
        "width": 1024,
        "height": 1024,
        "seed": 42, # Optional: random seed for variety if removed or randomized
        "nologo": "true" # Optional: remove watermark if applicable/supported
    }
    
    headers = {
        "Authorization": f"Bearer {api_key}"
    }
    
    # Encode prompt for URL path
    import urllib.parse
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
def generate_sku(product_type: str = "S") -> str:
    """Generuje unikátní SKU dle formátu SP-YYMMDD-SEQ-TYPE
    
    Args:
        product_type: 'S' pro Single, 'B' pro Bundle
    Returns:
        SKU string, např. 'SP-260208-01-S'
    """
    today = datetime.now().strftime("%y%m%d")
    prefix = f"SP-{today}-"
    
    # Najdi nejvyšší SEQ pro dnešní den v obou složkách
    max_seq = 0
    for wdir in [SINGLES_DIR, BUNDLES_DIR]:
        if os.path.exists(wdir):
            for folder in os.listdir(wdir):
                if folder.startswith(prefix):
                    try:
                        parts = folder.split("-")
                        if len(parts) >= 4:
                            seq_part = parts[2].split("_")[0]  # Handle SP-260208-01-S_Name
                            seq = int(seq_part)
                            max_seq = max(max_seq, seq)
                    except (ValueError, IndexError):
                        pass
    
    new_seq = str(max_seq + 1).zfill(2)
    return f"SP-{today}-{new_seq}-{product_type}"


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
    safe_keyword = re.sub(r'[^a-zA-Z0-9]', '', keyword)
    folder_name = f"{sku}_{safe_keyword}"
    folder_path = os.path.join(target_dir, folder_name)
    
    # Vytvořit strukturu dle pravidel
    os.makedirs(folder_path, exist_ok=True)
    os.makedirs(os.path.join(folder_path, "01_Print_Files"), exist_ok=True)
    os.makedirs(os.path.join(folder_path, "02_Marketing_Assets"), exist_ok=True)
    os.makedirs(os.path.join(folder_path, "03_Metadata"), exist_ok=True)
    
    # Vytvořit prázdný Master source (pro zálohu originálu)
    # Soubor 00_Master_Source.png bude přidán při generování
    
    print(f"   📁 Vytvořena produktová složka: {folder_name}")
    return folder_path


def create_listing_data(sku: str, title: str, tags: list, price: float = 5.90) -> dict:
    """Vytvoří metadata pro listing dle pravidla.md formátu"""
    return {
        "sku": sku,
        "title": title,
        "description_generated": "",
        "seo_tags": tags,
        "pricing": {
            "currency": "USD",
            "amount": price
        },
        "file_paths": {}
    }


# === LEGACY CESTY (zpětná kompatibilita) ===
# 1. Šablony (zůstávají u skriptu)
MOCKUP_DIR = os.path.join(SCRIPT_DIR, "1_Mockup_Sablony")
TEMPLATES_JSON_PATH = os.path.join(SCRIPT_DIR, "mockup_templates.json")

# 3. Vstupy pro SOLO - NOVĚ z Input Queue
SOLO_INPUT_DIR = TO_EDIT_DIR  # Přesměrováno na novou lokaci

# 4. Cesty pro browsing mockupů
ETSY_BROWSE_ROOT = ETSY_ROOT
MOCKUP_TEMPLATES_DIR = os.path.join(SCRIPT_DIR, "1_Mockup_Sablony")

# Požadované výstupní formáty pro Etsy (vysoká kvalita dle upravapic.md)
PRINT_SIZES = [
    {"name": "16x9-4800x2700", "w": 4800, "h": 2700},   # Landscape
    {"name": "20x11-6000x3300", "w": 6000, "h": 3300},   # Landscape
    {"name": "24x13-7200x3960", "w": 7200, "h": 3960},   # Landscape (Max size)
    {"name": "15x20-4500x6000", "w": 4500, "h": 6000},   # Portrait
    {"name": "16x20-4800x6000", "w": 4800, "h": 6000},   # Portrait
]

# 5. Cesta k testovacímu artu
TEST_ART_PATH = r"c:\Users\cowle\Pictures\Etsy\01_Hotove_Produkty\SeFStandalone\Art.png"

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


# --- 2. FUNKCE PRO KVALITU ---

from PIL import Image, ImageOps, ImageFilter, ImageEnhance

def find_coeffs(pa, pb):
    matrix = []
    for p1, p2 in zip(pa, pb):
        matrix.append([p1[0], p1[1], 1, 0, 0, 0, -p2[0]*p1[0], -p2[0]*p1[1]])
        matrix.append([0, 0, 0, p1[0], p1[1], 1, -p2[1]*p1[0], -p2[1]*p1[1]])

    A = np.matrix(matrix, dtype=float)
    B = np.array(pb).reshape(8)

    res = np.dot(np.linalg.inv(A.T * A) * A.T, B)
    return np.array(res).reshape(8)

def process_high_quality_print(source_img, output_folder, base_name):
    """Vytvoří 5 HD variant optimalizovaných pro extrémní upscaling z 768px."""
    print(f"   ⚙️  Extrémní upscaling a vylepšení detailů: {base_name}")
    
    if source_img.mode != "RGB":
        source_img = source_img.convert("RGB")

    # 1. Před-zpracování: Mírné zvýraznění detailů v původním malém rozlišení
    source_img = source_img.filter(ImageFilter.DETAIL)
    
    # Mírné zvýšení kontrastu a sytosti (vhodné pro tisk)
    source_img = ImageEnhance.Contrast(source_img).enhance(1.05)
    source_img = ImageEnhance.Color(source_img).enhance(1.05)

    for size in PRINT_SIZES:
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
            
        # 2. Resampling: Používáme LANCZOS, což je nejlepší dostupný filtr pro upscaling v Pillow
        img_resized = source_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        
        # 3. Ořez na střed
        left = (new_w - target_w) / 2
        top = (new_h - target_h) / 2
        right = (new_w + target_w) / 2
        bottom = (new_h + target_h) / 2
        img_cropped = img_resized.crop((left, top, right, bottom))
        
        # 4. Finální zostření: Agresivnější nastavení pro kompenzaci 10x zvětšení
        # Radius 2.0 pomáhá definovat hrany, Percent 150 dodává ostrost
        img_final = img_cropped.filter(ImageFilter.UnsharpMask(radius=2.0, percent=150, threshold=1))
        
        # Možné přidat ještě mírný grain/šum pro potlačení digitálního rozmazání (volitelné)
        # img_final = img_final.filter(ImageFilter.SMOOTH_MORE) # Pouze pokud by byl výsledek příliš kostičkovaný
        
        out_path = os.path.join(output_folder, f"{base_name}-{size_label}.jpg")
        img_final.save(out_path, "JPEG", quality=95, dpi=(300, 300), subsampling=0)

# --- 3. LOGIKA AGENTA ---

def market_research(client):
    print("\n🕵️  Průzkum trhu...")
    prompt = """Act as a professional Art Market Trend Analyst for Etsy 2026.\nIdentify ONE specific, high-demand, low-competition art niche.\nFocus on styles like: Dark Academia, Moody Landscapes, Witchy Cottagecore, Japandi, or Abstract Organic.\n    
Output ONLY a raw JSON:\n{ \"bundle_theme\": \"Name of the theme\", \"visual_style\": \"Detailed visual description, colors, mood\", \"target_audience\": \"Who buys this\" }\n"""
    try:
        completion = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.3-70b-versatile"
        )
        content = completion.choices[0].message.content.replace("```json", "").replace("```", "").strip()
        return json.loads(content)
    except:
        return {"bundle_theme": "Dark Academia Botanical", "visual_style": "Vintage, moody, herbs", "target_audience": "Nature lovers"}

def get_prompts(client, trend):
    print("🎨 Návrh kolekce...")
    # Používáme zdvojené závorky {{ }} pro JSON v f-stringu
    prompt = f"Create 5 prompts for '{trend['bundle_theme']}'. Style: {trend['visual_style']}. Composition MUST be centered, 1:1 ratio. Return ONLY raw JSON: {{'prompts': ['p1', 'p2', 'p3', 'p4', 'p5']}}"
    try:
        completion = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.3-70b-versatile"
        )
        content = completion.choices[0].message.content.strip()
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
        print(f"   ⚠️ Chyba při získávání promptů, používám záložní: {e}")
        return [f"{trend['bundle_theme']} masterpiece"] * 5



def create_mockup(art, output_path, cat):
    configs = MOCKUP_TEMPLATES.get(cat, [])
    if not configs: return
    config = random.choice(configs)
    tmpl_path = os.path.join(MOCKUP_DIR, config["filename"])
    if not os.path.exists(tmpl_path): return
    try:
        bg = Image.open(tmpl_path).convert("RGBA")
        
        # Převod artu na RGBA, pokud není
        if art.mode != 'RGBA':
            art = art.convert('RGBA')

        # Zkontroluj, zda máme definované rohy pro perspektivu
        if "corners" in config:
            # Perspektivní transformace
            width, height = art.size
            
            # Cílové rohy (z configu) - pořadí: TL, TR, BR, BL
            target_corners = config["corners"]
            
            # Zdrojové rohy (celý art) - pořadí: TL, TR, BR, BL
            source_corners = [(0, 0), (width, 0), (width, height), (0, height)]
            
            # Vypočítáme koeficienty pro transformaci
            coeffs = find_coeffs(target_corners, source_corners)
            
            # Transformace
            # Použijeme velikost pozadí jako cílovou velikost, abychom mohli rovnou paste
            # Ale pozor, transform vrací nový obrázek. 
            
            # Lepší postup: Transformovat art do plné velikosti bg a pak ho tam vložit přes masku
            # Ale jednodušší je: Vytvořit průhledný layer velikosti BG, tam transformovat Art
            
            bg_w, bg_h = bg.size
            art_transformed = art.transform((bg_w, bg_h), Image.PERSPECTIVE, coeffs, Image.BICUBIC)
            
            # Vložíme transformovaný art na pozadí (pomocí alpha kanálu jako masky)
            bg.paste(art_transformed, (0, 0), art_transformed)
            
        else:
            # Klasický resize a vložení
            art_resized = art.resize((config["w"], config["h"]), Image.Resampling.LANCZOS)
            bg.paste(art_resized, (config["x"], config["y"]))
            
        bg.convert("RGB").save(output_path, quality=93)
        print(f"   ✅ Mockup hotov: {cat}")
    except Exception as e:
        print(f"   ❌ Chyba mockupu: {e}")

def create_mockup_from_templates_dir(art, output_path):
    """Vytvoří mockup z náhodné šablony ze složky MOCKUP_TEMPLATES_DIR"""
    if not os.path.exists(MOCKUP_TEMPLATES_DIR):
        print(f"   ❌ Složka se šablonami neexistuje: {MOCKUP_TEMPLATES_DIR}")
        return False
    
    # Najdi všechny PNG soubory v adresáři šablon
    template_files = [f for f in os.listdir(MOCKUP_TEMPLATES_DIR) if f.lower().endswith('.png')]
    
    if not template_files:
        print(f"   ❌ Ve složce šablon nejsou žádné PNG soubory")
        return False
    
    # Vyber náhodnou šablonu
    random_template = random.choice(template_files)
    template_path = os.path.join(MOCKUP_TEMPLATES_DIR, random_template)
    
    print(f"   🎲 Použita šablona: {random_template}")
    
    # Najdi konfiguraci pro tuto šablonu
    template_config = None
    for category, configs in MOCKUP_TEMPLATES.items():
        for config in configs:
            if config["filename"] == random_template:
                template_config = config
                break
        if template_config:
            break
    
    if not template_config:
        print(f"   ⚠️ Konfigurace pro šablonu {random_template} nebyla nalezena, používám výchozí rozměry")
        # Výchozí konfigurace, pokud není v MOCKUP_TEMPLATES
        template_config = {"x": 400, "y": 300, "w": 200, "h": 150}
    
    try:
        bg = Image.open(template_path).convert("RGBA")
        
        # Převod artu na RGBA, pokud není
        if art.mode != 'RGBA':
            art = art.convert('RGBA')

        # Zkontroluj, zda máme definované rohy pro perspektivu
        if "corners" in template_config:
            # Perspektivní transformace
            width, height = art.size
            
            # Cílové rohy (z configu)
            target_corners = template_config["corners"]
            
            # Zdrojové rohy (celý art)
            source_corners = [(0, 0), (width, 0), (width, height), (0, height)]
            
            # Vypočítáme koeficienty
            coeffs = find_coeffs(target_corners, source_corners)
            
            bg_w, bg_h = bg.size
            art_transformed = art.transform((bg_w, bg_h), Image.PERSPECTIVE, coeffs, Image.BICUBIC)
            
            bg.paste(art_transformed, (0, 0), art_transformed)
            
        else:
            # Klasický resize
            art_resized = art.resize((template_config["w"], template_config["h"]), Image.Resampling.LANCZOS)
            bg.paste(art_resized, (template_config["x"], template_config["y"]))
            
        bg.convert("RGB").save(output_path, quality=93)
        print(f"   ✅ Mockup vytvořen: {output_path}")
        return True
    except Exception as e:
        print(f"   ❌ Chyba při vytváření mockupu: {e}")
        return False

def generate_seo_text(client, trend_data, output_folder):
    print("📝 Generování SEO textů...")
    prompt = f"""Write Etsy Listing Info for: {trend_data['bundle_theme']}\nOutput Structure:\nTITLE: (SEO friendly)\nDESCRIPTION: (Sales copy)\nTAGS: (13 tags comma separated)\n"""
    try:
        completion = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.3-70b-versatile"
        )
        with open(os.path.join(output_folder, "BUNDLE_INFO.txt"), "w", encoding="utf-8") as f:
            f.write(completion.choices[0].message.content)
    except:
        pass

# --- NOVÁ FUNKCE: BROWSE A MOCKUP ---

def is_source_image(filename):
    """Kontrola, zda je soubor zdrojový obrázek (neobsahuje rozlišení v názvu)"""
    # Rozlišení, která chceme ignorovat
    resolution_patterns = ['15x20', '16x20', '16x9', '20x11', '24x13']
    
    # Kontrola, zda název neobsahuje žádné z těchto vzorů
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
                      and item.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif'))]
        
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
            
            # Vytvoř mockup
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
                                 and item.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif'))])
            
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
                                           and item.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif'))])
                    
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
                                 and item.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif'))])
            
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
                if index < len(folders):
                    selected_folder = folders[index]
                    current_path = os.path.join(current_path, selected_folder)
                
                # Kontrola, zda je to obrázek
                elif index < len(folders) + len(image_files):
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
                            
                            # Vytvoř mockup
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

def publish_to_etsy(product_dir):
    """Nahraje produkt (draft) na Etsy na základě dat ve složce produktu."""
    if not EtsyClient:
        print("❌ Chyba: Modul etsy_api není dostupný.")
        return False

    if not all([ETSY_API_KEY, ETSY_SHOP_ID, ETSY_ACCESS_TOKEN]):
        print("⚠️ Chybí konfigurace Etsy API v .env souboru.")
        return False

    metadata_path = os.path.join(product_dir, "03_Metadata", "listing_data.json")
    if not os.path.exists(metadata_path):
        print(f"❌ Metadata nenalezena: {metadata_path}")
        return False

    with open(metadata_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    print(f"\n📤 NAHRÁVÁNÍ NA ETSY: {data.get('title')}")
    client = EtsyClient(ETSY_API_KEY, ETSY_SHOP_ID, ETSY_ACCESS_TOKEN)
    
    # 1. Příprava dat pro listing
    # Poznámka: taxonomy_id pro 'Wall Art' (Digital) je např. 159 (Digital Prints)
    listing_payload = {
        "quantity": 999,
        "title": data.get("title"),
        "description": data.get("description_generated") or "Digital Printable Wall Art",
        "price": data.get("pricing", {}).get("amount", 5.90),
        "who_made": "i_did",
        "when_made": "2020_2024",
        "taxonomy_id": 159,  # Digital Prints
        "is_digital": "true",
        "tags": ",".join(data.get("seo_tags", []))[:255] # Max 13 tagů, ale API bere string
    }

    # 2. Vytvoření listingu
    listing_id = client.create_listing(listing_payload)
    if not listing_id:
        return False

    # 3. Nahrání obrázků z 02_Marketing_Assets
    marketing_dir = os.path.join(product_dir, "02_Marketing_Assets")
    if os.path.exists(marketing_dir):
        # Najít JPG soubory (mockupy) a seřadit je podle názvu (01_Main_Thumbnail bude první)
        images = sorted([f for f in os.listdir(marketing_dir) if f.lower().endswith(('.jpg', '.jpeg'))])
        
        print(f"🖼️ Nahrávám {len(images)} obrázků k listingu {listing_id}...")
        for i, img_name in enumerate(images, 1):
            img_path = os.path.join(marketing_dir, img_name)
            client.upload_listing_image(listing_id, img_path, rank=i)

    print(f"✅ Produkt {data.get('sku')} byl úspěšně nahrán na Etsy jako draft.")
    return True

def run_generation_mode():
    """Automaticky generuje Bundle s 5 obrazy dle pravidla.md struktury"""
    print(f"\n🚀 SPUŠTĚNÍ AUTOMATICKÉHO GENERÁTORU {datetime.now().strftime('%H:%M')}")
    client = Groq(api_key=GROQ_API_KEY)
    
    # 1. Průzkum trhu
    trend = market_research(client)
    safe_theme = re.sub(r'[^a-zA-Z0-9]', '', trend['bundle_theme'])
    
    # 2. Generování SKU pro Bundle
    sku = generate_sku("B")
    bundle_dir = create_product_folder(sku, safe_theme)
    
    # Vytvoření 00_Masters složky pro Bundle
    masters_dir = os.path.join(bundle_dir, "00_Masters")
    os.makedirs(masters_dir, exist_ok=True)
    
    # Přejmenování 01_Print_Files na 01_Print_Files_Ready (Bundle varianta)
    old_print = os.path.join(bundle_dir, "01_Print_Files")
    new_print = os.path.join(bundle_dir, "01_Print_Files_Ready")
    if os.path.exists(old_print):
        os.rename(old_print, new_print)
    
    # 3. Prompty a generování
    prompts = get_prompts(client, trend)
    images = []

    print(f"\n🖼️  Začínám produkci 5 Art Printů do: {bundle_dir}")
    
    for i, p in enumerate(prompts, 1):
        print(f"\n--- Obraz {i}/5 ---")
        img = generate_image(p)
        if img:
            art_name = f"Art_{chr(64+i)}"  # Art_A, Art_B, Art_C...
            
            # Uložit master do 00_Masters
            master_path = os.path.join(masters_dir, f"{art_name}.png")
            img.save(master_path)
            images.append(img)
            
            # Vytvořit složku pro tiskové soubory tohoto artu
            art_print_dir = os.path.join(new_print, art_name)
            os.makedirs(art_print_dir, exist_ok=True)
            process_high_quality_print(img, art_print_dir, art_name)

    # 4. Mockupy do 02_Marketing_Assets (8 mockupů pro Etsy listing)
    marketing_dir = os.path.join(bundle_dir, "02_Marketing_Assets")
    if images:
        print("\n🎨 Tvorba prezentačních materiálů (8 mockupů)...")
        mockup_names = [
            ("01_Main_Thumbnail", "Obyčejný byt"),
            ("02_Bundle_Overview", "Střední třída"),
            ("03_Living_Room", "Luxusní sídlo"),
            ("04_Bedroom", "Obyčejný byt"),
            ("05_Office_Space", "Střední třída"),
            ("06_Detail_View", "Luxusní sídlo"),
            ("07_Size_Comparison", "Obyčejný byt"),
            ("08_Lifestyle", "Střední třída"),
        ]
        for name, category in mockup_names:
            create_mockup(random.choice(images), os.path.join(marketing_dir, f"{name}.jpg"), category)

    # 5. SEO a metadata do 03_Metadata
    metadata_dir = os.path.join(bundle_dir, "03_Metadata")
    generate_seo_text(client, trend, metadata_dir)
    
    # Vytvořit listing_data.json
    listing_data = create_listing_data(
        sku=sku,
        title=f"{trend['bundle_theme']} Wall Art Bundle - Set of 5 Printable Art",
        tags=trend.get('visual_style', '').split(', ')[:13],
        price=9.90
    )
    with open(os.path.join(metadata_dir, "listing_data.json"), "w", encoding="utf-8") as f:
        json.dump(listing_data, f, indent=2, ensure_ascii=False)
    
    print(f"\n✨ Bundle {sku} dokončen v: {bundle_dir}")

    # Dotaz na nahrání na Etsy
    if EtsyClient:
        choice = input(f"\n❓ Chceš tento Bundle ({sku}) nahrát na Etsy jako draft? (y/n): ").strip().lower()
        if choice == 'y':
            publish_to_etsy(bundle_dir)

def run_solo_mode():
    """Zpracuje obrázky z 00_Input_Queue/_To_Edit/ a vytvoří Singles produkty"""
    print(f"\n🛠️ SPUŠTĚNÍ SOLO ÚPRAV")
    print(f"Hledám obrázky ve složce: {SOLO_INPUT_DIR}")
    
    # Zajistit existenci vstupní složky
    if not os.path.exists(SOLO_INPUT_DIR):
        print(f"❌ Složka '_To_Edit' neexistuje! Vytvářím ji...")
        os.makedirs(SOLO_INPUT_DIR, exist_ok=True)
        print("📁 Složka vytvořena. Vložte do ní obrázky a spusťte skript znovu.")
        return
        
    files = [f for f in os.listdir(SOLO_INPUT_DIR) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
    
    if not files:
        print("⚠️ Ve složce nejsou žádné obrázky.")
        return
        
    print(f"Nalezeno {len(files)} obrázků ke zpracování.")

    for filename in files:
        print(f"\n--- Zpracovávám: {filename} ---")
        file_path = os.path.join(SOLO_INPUT_DIR, filename)
        base_name = os.path.splitext(filename)[0]
        safe_name = re.sub(r'[^a-zA-Z0-9]', '', base_name)
        
        try:
            with Image.open(file_path) as img:
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
                print(f"   🎨 Generuji 8 mockupů...")
                mockup_names = [
                    ("01_Main_Thumbnail", "Obyčejný byt"),
                    ("02_Living_Room", "Střední třída"),
                    ("03_Bedroom", "Luxusní sídlo"),
                    ("04_Office", "Obyčejný byt"),
                    ("05_Detail_Close", "Střední třída"),
                    ("06_Size_Guide", "Luxusní sídlo"),
                    ("07_Lifestyle_1", "Obyčejný byt"),
                    ("08_Lifestyle_2", "Střední třída"),
                ]
                for name, category in mockup_names:
                    create_mockup(img, os.path.join(marketing_dir, f"{name}.jpg"), category)
                
                # 5. Metadata do 03_Metadata
                metadata_dir = os.path.join(product_dir, "03_Metadata")
                listing_data = create_listing_data(
                    sku=sku,
                    title=f"{safe_name} Wall Art - Digital Download Printable",
                    tags=["wall art", "printable", "digital download"],
                    price=5.90
                )
                with open(os.path.join(metadata_dir, "listing_data.json"), "w", encoding="utf-8") as f:
                    json.dump(listing_data, f, indent=2, ensure_ascii=False)
                
                print(f"   ✅ Single {sku} vytvořen!")

                # Dotaz na nahrání na Etsy
                if EtsyClient:
                    choice = input(f"\n❓ Chceš tento produkt ({sku}) nahrát na Etsy jako draft? (y/n): ").strip().lower()
                    if choice == 'y':
                        publish_to_etsy(product_dir)
                
        except Exception as e:
            print(f"❌ Chyba při zpracování {filename}: {e}")

    print(f"\n✨ Vše hotovo! Produkty jsou v: {SINGLES_DIR}")

def run_mockup_test_mode():
    print(f"\n🧪 SPUŠTĚNÍ TESTOVÁNÍ MOCKUPŮ")
    
    # 1. Kontrola testovacího obrázku
    if not os.path.exists(TEST_ART_PATH):
        print(f"❌ Testovací obrázek neexistuje: {TEST_ART_PATH}")
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
        # Zjisti, zda existuje konfigurace
        found_config = False
        for cat, configs in MOCKUP_TEMPLATES.items():
            for c in configs:
                if c["filename"] == t:
                    found_config = True
                    break
            if found_config: break
        
        status = "✅ Konfigurováno" if found_config else "⚠️ Bez konfigurace"
        print(f"  {i}. {t} ({status})")
    
    # 3. Výběr šablony
    try:
        choice_input = input("\nVyber číslo šablony (nebo 'q' pro konec): ").strip()
        if choice_input.lower() == 'q': return
        
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
    
    # Najdi konfiguraci
    template_config = None
    for category, configs in MOCKUP_TEMPLATES.items():
        for config in configs:
            if config["filename"] == selected_template:
                template_config = config
                break
        if template_config: break
    
    if not template_config:
        print(f"⚠️ Konfigurace pro {selected_template} nenalezena. Použiji default 400x300.")
        template_config = {"x": 400, "y": 300, "w": 200, "h": 150}
    
    try:
        # Načti art
        art = Image.open(TEST_ART_PATH)
        
        # Načti šablonu
        bg = Image.open(template_path).convert("RGBA")
        
        # Převod artu na RGBA
        if art.mode != 'RGBA':
            art = art.convert('RGBA')

        # Zkontroluj, zda máme definované rohy pro perspektivu
        if "corners" in template_config:
            # Perspektivní transformace
            width, height = art.size
            
            # Cílové rohy (z configu)
            target_corners = template_config["corners"]
            
            # Zdrojové rohy (celý art)
            source_corners = [(0, 0), (width, 0), (width, height), (0, height)]
            
            # Vypočítáme koeficienty
            coeffs = find_coeffs(target_corners, source_corners)
            
            bg_w, bg_h = bg.size
            # Transformace
            art_transformed = art.transform((bg_w, bg_h), Image.PERSPECTIVE, coeffs, Image.BICUBIC)
            
            # Vložíme transformovaný art na pozadí (pomocí alpha kanálu jako masky)
            bg.paste(art_transformed, (0, 0), art_transformed)
            
        else:
            # Klasický resize a vložení
            art_resized = art.resize((template_config["w"], template_config["h"]), Image.Resampling.LANCZOS)
            bg.paste(art_resized, (template_config["x"], template_config["y"]))
        
        # Uložení
        bg.convert("RGB").save(output_path, quality=95)
        print(f"✅ Hotovo! Uloženo jako: {output_path}")
        
        # Otevření pro kontrolu
        os.startfile(output_path)
        
    except Exception as e:
        print(f"❌ Chyba: {e}")

def run_list_mode():
    """Načte prompts.json a vygeneruje buď singly nebo bundles dle obsahu"""
    json_path = PROMPTS_JSON_PATH

    print(f"\n📋 SPUŠTĚNÍ GENERACE ZE SEZNAMU")
    print(f"Hledám soubor: {json_path}")

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
                        
                    print(f"\n🚀 Generuji Bundle {i}/{len(data['bundles'])}: '{theme}'")
                    print(f"🎨 Styl: {style}")
                    
                    # 1. Struktura Bundle
                    safe_theme = re.sub(r'[^a-zA-Z0-9]', '', theme)
                    sku = generate_sku("B")
                    bundle_dir = create_product_folder(sku, safe_theme)
                    
                    masters_dir = os.path.join(bundle_dir, "00_Masters")
                    os.makedirs(masters_dir, exist_ok=True)
                    
                    # Přejmenování Print Files složky
                    old_print = os.path.join(bundle_dir, "01_Print_Files")
                    new_print = os.path.join(bundle_dir, "01_Print_Files_Ready")
                    if os.path.exists(old_print):
                        os.rename(old_print, new_print)

                    images = []
                    
                    # 2. Generování obrazů
                    for j, p in enumerate(prompts, 1):
                        print(f"\n   --- Obraz {j}/{len(prompts)} ---")
                        print(f"   📝 Prompt: {p[:60]}...")
                        img = generate_image(p)
                        
                        if img:
                            art_name = f"Art_{chr(64+j)}" # A, B, C...
                            
                            # Master
                            master_path = os.path.join(masters_dir, f"{art_name}.png")
                            img.save(master_path)
                            images.append(img)
                            
                            # Print files
                            art_print_dir = os.path.join(new_print, art_name)
                            os.makedirs(art_print_dir, exist_ok=True)
                            process_high_quality_print(img, art_print_dir, art_name)
                    
                    # 3. Mockupy
                    marketing_dir = os.path.join(bundle_dir, "02_Marketing_Assets")
                    if images:
                        print("\n   🎨 Tvorba prezentačních materiálů (8 mockupů)...")
                        mockup_names = [
                            ("01_Main_Thumbnail", "Obyčejný byt"),
                            ("02_Bundle_Overview", "Střední třída"),
                            ("03_Living_Room", "Luxusní sídlo"),
                            ("04_Bedroom", "Obyčejný byt"),
                            ("05_Office_Space", "Střední třída"),
                            ("06_Detail_View", "Luxusní sídlo"),
                            ("07_Size_Comparison", "Obyčejný byt"),
                            ("08_Lifestyle", "Střední třída"),
                        ]
                        for name, category in mockup_names:
                            create_mockup(random.choice(images), os.path.join(marketing_dir, f"{name}.jpg"), category)
                    
                    # 4. Metadata
                    metadata_dir = os.path.join(bundle_dir, "03_Metadata")
                    
                    # SEO text (pokud je klient k dispozici, jinak skip)
                    try:
                        client = Groq(api_key=GROQ_API_KEY)
                        generate_seo_text(client, {"bundle_theme": theme, "visual_style": style}, metadata_dir)
                    except:
                        print("   ⚠️ SEO generování přeskočeno (chyba API/Client)")

                    listing_data = create_listing_data(
                        sku=sku,
                        title=f"{theme} Wall Art Bundle - Set of {len(prompts)} Printable Art",
                        tags=style.split(', ')[:13],
                        price=9.90
                    )
                    with open(os.path.join(metadata_dir, "listing_data.json"), "w", encoding="utf-8") as f:
                        json.dump(listing_data, f, indent=2, ensure_ascii=False)
                    
                    print(f"\n   ✨ Bundle {sku} hotov: {bundle_dir}")

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
                    
                    if not prompt: continue

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
                
                print("\n✨ Hotovo! Obrázky jsou v '00_Input_Queue/_To_Edit'.")
                print("👉 Spusťte volbu 2 (SOLO) pro jejich zpracování na produkty.")
            
            else:
                print("⚠️ JSON neobsahuje klíče 'bundles', 'tasks' ani 'prompts'.")

    except Exception as e:
        print(f"❌ Chyba při zpracování JSON: {e}")

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
                    updated = False
                    for cat, templates in MOCKUP_TEMPLATES.items():
                        for tmpl in templates:
                            if tmpl['filename'] == filename:
                                tmpl['corners'] = corners
                                updated = True
                                break
                        if updated: break
                    
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
    
    # Najít soubory v kořenové složce (ne ve složkách)
    files = [f for f in os.listdir(SOLO_INPUT_DIR) 
             if os.path.isfile(os.path.join(SOLO_INPUT_DIR, f)) 
             and f.lower().endswith(('.png', '.jpg', '.jpeg', '.txt', '.json'))]
    
    if not files:
        print("⚠️  Žádné soubory k archivaci ve vstupní složce.")
        return

    print(f"Přesouvám {len(files)} souborů do: {archive_target}...")
    
    count = 0
    for f in files:
        try:
            src = os.path.join(SOLO_INPUT_DIR, f)
            dst = os.path.join(archive_target, f)
            # Pokud soubor existuje, přidej timestamp
            if os.path.exists(dst):
                base, ext = os.path.splitext(f)
                timestamp = datetime.now().strftime("%H%M%S")
                dst = os.path.join(archive_target, f"{base}_{timestamp}{ext}")
            os.rename(src, dst)
            count += 1
        except Exception as e:
            print(f"❌ Chyba při přesunu {f}: {e}")
            
    print(f"✅ Hotovo! Archivováno {count} souborů do {month_folder}.")

def main():
    print("\n" + "="*40)
    print("   🤖 STORK PILOT - MANAGER SYSTEM")
    print("="*40)
    print("1. Spustit Generování (Nový Bundle automaticky)")
    print("2. Dodělat SOLO (Zpracovat obrázky ve složce 3_Upravit)")
    print("3. Vytvořit podle seznamu (Načíst prompts.json -> 3_Upravit)")
    print("4. Procházet složky a vytvořit mockup (Browser mode)")
    print("5. Testování mockup (Vložit Art.png do vybrané šablony)")
    print("6. Spustit Kalibrační Server (mereni.html)")
    print("7. Archivovat staré soubory (v 3_Upravit)")
    print("="*40)
    
    choice = input("Zadej volbu (1, 2, 3, 4, 5, 6 nebo 7): ").strip()
    
    if choice == "1":
        run_generation_mode()
    elif choice == "2":
        run_solo_mode()
    elif choice == "3":
        run_list_mode()
    elif choice == "4":
        browse_and_create_mockup()
    elif choice == "5":
        run_mockup_test_mode()
    elif choice == "6":
        run_config_server()
    elif choice == "7":
        archive_old_files()
    else:
        print("❌ Neplatná volba. Ukončuji.")

if __name__ == "__main__":
    while True:
        print("\n" + "="*40)
        print("  SUPER ROBOT GENERATOR - ENTRY MENU")
        print("="*40)
        print("1. Spustit Generátor (Flow: Market -> Prompts -> Art -> Mockups -> SEO)")
        print("2. Spustit SOLO úpravy (Složka 3_Upravit -> Hotovo)")
        print("3. Generovat ze seznamu (prompts.json -> Art -> Mockups)")
        print("4. Procházet složky a tvořit mockupy (Browser Mode)")
        print("5. Testování mockup (jeden obrázek + výběr šablony)")
        print("6. Spustit Kalibrační Server (mereni.html)")
        print("7. Archivovat staré soubory (v 3_Upravit)")
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
            print("❌ Neplatná volba. Ukončuji.")