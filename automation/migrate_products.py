"""
Migrační skript pro přesun produktů z 01_Hotove_Produkty do 02_Warehouse
dle pravidla.md v2.0
"""

import os
import shutil
import json
import re
from datetime import datetime

# Cesty
ETSY_ROOT = r"c:\Users\cowle\Pictures\Etsy"
OLD_DIR = os.path.join(ETSY_ROOT, "01_Hotove_Produkty")
SINGLES_DIR = os.path.join(ETSY_ROOT, "02_Warehouse", "Singles")
BUNDLES_DIR = os.path.join(ETSY_ROOT, "02_Warehouse", "Bundles")

# SKU counter (začínáme od 01 pro dnešní den)
sku_counter = {"S": 0, "B": 0}

def generate_sku(product_type):
    """Generuje SKU pro migraci - použijeme dnešní datum"""
    global sku_counter
    sku_counter[product_type] += 1
    today = datetime.now().strftime("%y%m%d")
    return f"SP-{today}-{str(sku_counter[product_type]).zfill(2)}-{product_type}"

def create_listing_data(sku, title, tags):
    return {
        "sku": sku,
        "title": title,
        "description_generated": "",
        "seo_tags": tags,
        "pricing": {"currency": "USD", "amount": 5.90 if sku.endswith("-S") else 9.90},
        "file_paths": {}
    }

def migrate_single(old_path, folder_name):
    """Migruje Single produkt"""
    # Extrahovat keyword z názvu
    keyword = re.sub(r'^Se[A-Z]', '', folder_name)  # Odstraní prefix SeA, SeB...
    if not keyword:
        keyword = folder_name
    safe_keyword = re.sub(r'[^a-zA-Z0-9]', '', keyword)
    
    sku = generate_sku("S")
    new_folder = f"{sku}_{safe_keyword}"
    new_path = os.path.join(SINGLES_DIR, new_folder)
    
    print(f"  📦 {folder_name} -> {new_folder}")
    
    # Vytvořit strukturu
    os.makedirs(new_path, exist_ok=True)
    os.makedirs(os.path.join(new_path, "01_Print_Files"), exist_ok=True)
    os.makedirs(os.path.join(new_path, "02_Marketing_Assets"), exist_ok=True)
    os.makedirs(os.path.join(new_path, "03_Metadata"), exist_ok=True)
    
    # Přesunout soubory
    files = os.listdir(old_path)
    master_saved = False
    
    for f in files:
        src = os.path.join(old_path, f)
        if os.path.isfile(src):
            lower = f.lower()
            
            # Zdrojové PNG -> 00_Master_Source.png
            if lower.endswith('.png') and not master_saved:
                dst = os.path.join(new_path, "00_Master_Source.png")
                shutil.copy2(src, dst)
                master_saved = True
            
            # Mockupy -> 02_Marketing_Assets
            elif '_mockup' in lower:
                idx = len([x for x in os.listdir(os.path.join(new_path, "02_Marketing_Assets"))]) + 1
                dst = os.path.join(new_path, "02_Marketing_Assets", f"{idx:02d}_Mockup.jpg")
                shutil.copy2(src, dst)
            
            # Print files (ty s rozlišením)
            elif any(res in lower for res in ['15x20', '16x20', '16x9', '20x11', '24x13']):
                dst = os.path.join(new_path, "01_Print_Files", f)
                shutil.copy2(src, dst)
    
    # Vytvořit listing_data.json
    listing = create_listing_data(sku, f"{safe_keyword} Wall Art - Digital Download", ["wall art", "printable", "digital download"])
    with open(os.path.join(new_path, "03_Metadata", "listing_data.json"), "w", encoding="utf-8") as f:
        json.dump(listing, f, indent=2, ensure_ascii=False)
    
    return new_path

def migrate_bundle(old_path, folder_name):
    """Migruje Bundle produkt"""
    # Extrahovat keyword
    parts = folder_name.split("_")
    keyword = parts[-1] if len(parts) > 1 else folder_name
    safe_keyword = re.sub(r'[^a-zA-Z0-9]', '', keyword)
    
    sku = generate_sku("B")
    new_folder = f"{sku}_{safe_keyword}"
    new_path = os.path.join(BUNDLES_DIR, new_folder)
    
    print(f"  📦 {folder_name} -> {new_folder}")
    
    # Vytvořit strukturu
    os.makedirs(new_path, exist_ok=True)
    os.makedirs(os.path.join(new_path, "00_Masters"), exist_ok=True)
    os.makedirs(os.path.join(new_path, "01_Print_Files_Ready"), exist_ok=True)
    os.makedirs(os.path.join(new_path, "02_Marketing_Assets"), exist_ok=True)
    os.makedirs(os.path.join(new_path, "03_Metadata"), exist_ok=True)
    
    items = os.listdir(old_path)
    
    for item in items:
        src = os.path.join(old_path, item)
        lower = item.lower()
        
        if os.path.isdir(src):
            # Složky Art_X_Files -> 01_Print_Files_Ready/Art_X
            if '_files' in lower:
                art_name = item.replace("_Files", "").replace("_files", "")
                art_letter = chr(64 + int(art_name.split("_")[1])) if "_" in art_name else "A"
                dst_dir = os.path.join(new_path, "01_Print_Files_Ready", f"Art_{art_letter}")
                shutil.copytree(src, dst_dir)
        
        elif os.path.isfile(src):
            # Source PNG -> 00_Masters
            if '_source' in lower and lower.endswith('.png'):
                art_num = item.split("_")[1] if "_" in item else "1"
                art_letter = chr(64 + int(art_num))
                dst = os.path.join(new_path, "00_Masters", f"Art_{art_letter}.png")
                shutil.copy2(src, dst)
            
            # Showcase mockupy -> 02_Marketing_Assets
            elif 'showcase' in lower:
                idx = len([x for x in os.listdir(os.path.join(new_path, "02_Marketing_Assets"))]) + 1
                dst = os.path.join(new_path, "02_Marketing_Assets", f"{idx:02d}_{item}")
                shutil.copy2(src, dst)
            
            # BUNDLE_INFO.txt -> 03_Metadata
            elif 'bundle_info' in lower:
                dst = os.path.join(new_path, "03_Metadata", "BUNDLE_INFO.txt")
                shutil.copy2(src, dst)
    
    # Vytvořit listing_data.json
    listing = create_listing_data(sku, f"{safe_keyword} Wall Art Bundle - Set of 5", ["wall art", "bundle", "printable set"])
    with open(os.path.join(new_path, "03_Metadata", "listing_data.json"), "w", encoding="utf-8") as f:
        json.dump(listing, f, indent=2, ensure_ascii=False)
    
    return new_path

def main():
    print("🚀 MIGRACE PRODUKTŮ NA NOVOU STRUKTURU")
    print("="*50)
    
    if not os.path.exists(OLD_DIR):
        print(f"❌ Zdrojová složka neexistuje: {OLD_DIR}")
        return
    
    folders = [f for f in os.listdir(OLD_DIR) if os.path.isdir(os.path.join(OLD_DIR, f))]
    
    print(f"📁 Nalezeno {len(folders)} produktů k migraci\n")
    
    migrated = {"singles": 0, "bundles": 0}
    
    for folder in sorted(folders):
        old_path = os.path.join(OLD_DIR, folder)
        
        # Detekce typu: Bundle nebo Single
        if folder.lower().startswith("bundle") or "bundle" in folder.lower():
            migrate_bundle(old_path, folder)
            migrated["bundles"] += 1
        else:
            migrate_single(old_path, folder)
            migrated["singles"] += 1
    
    print("\n" + "="*50)
    print(f"✅ MIGRACE DOKONČENA!")
    print(f"   Singles: {migrated['singles']}")
    print(f"   Bundles: {migrated['bundles']}")
    print(f"   Celkem: {migrated['singles'] + migrated['bundles']}")

if __name__ == "__main__":
    main()
