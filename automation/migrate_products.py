"""Migrace produktů ze staré struktury (01_Hotove_Produkty) do skladu 02_Warehouse (pravidla.md v2.0).

Z příkazové řádky:
    python automation/migrate_products.py --source CESTA            # jen plán (dry-run)
    python automation/migrate_products.py --source CESTA --apply    # opravdová migrace

- původní složky se nemění (soubory se kopírují),
- SKU se berou z perzistentního čítače (`super_robot.generate_sku`), takže nekolidují s novými produkty,
- už migrované složky se evidují v `data/migrated_products.json` a při dalším běhu se přeskočí.
"""

import argparse
import json
import os
import re
import shutil
import sys
from typing import Callable, Dict, List, Optional

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPT_DIR)
if _PROJECT_ROOT not in sys.path:  # spuštění jako `python automation/migrate_products.py`
    sys.path.insert(0, _PROJECT_ROOT)

from src import progress  # noqa: E402

WAREHOUSE_DIR = os.path.join(_PROJECT_ROOT, "automation", "02_Warehouse")
STATE_PATH = os.path.join(_PROJECT_ROOT, "data", "migrated_products.json")
PRINT_RESOLUTIONS = ("15x20", "16x20", "16x9", "20x11", "24x13")


def _load_project_config() -> dict:
    """Načte kořenový config.json jako jednotný zdroj cen (sekce prices)."""
    try:
        with open(os.path.join(_PROJECT_ROOT, "config.json"), "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def default_source() -> str:
    """Výchozí zdrojová složka: $ETSY_BROWSE_ROOT/01_Hotove_Produkty, jinak ~/Pictures/Etsy/01_Hotove_Produkty."""
    root = os.environ.get("ETSY_BROWSE_ROOT") or os.path.join(os.path.expanduser("~"), "Pictures", "Etsy")
    return os.path.join(root, "01_Hotove_Produkty")


def _next_sku(product_type: str) -> str:
    """Další SKU z perzistentního čítače skladu (lazy import, super_robot je těžký)."""
    from automation import super_robot

    return super_robot.generate_sku(product_type)


def _art_letter(value, default="A"):
    """Převede číslo artu (1-26) na písmeno A-Z. Neplatný vstup vrátí default a vypíše varování."""
    try:
        num = int(value)
    except (TypeError, ValueError):
        print(f"  ⚠️ Neplatné číslo artu '{value}', používám '{default}'")
        return default
    if not 1 <= num <= 26:
        print(f"  ⚠️ Číslo artu {num} je mimo rozsah 1-26, používám '{default}'")
        return default
    return chr(64 + num)


def create_listing_data(sku, title, tags):
    prices = _load_project_config().get("prices", {})
    single = float(prices.get("single", 5.90))
    bundle = float(prices.get("bundle", 9.90))
    return {
        "sku": sku,
        "title": title,
        "description_generated": "",
        "seo_tags": tags,
        "pricing": {"currency": "EUR", "amount": single if sku.endswith("-S") else bundle},
        "file_paths": {},
    }


def detect_kind(folder_name: str) -> str:
    return "bundle" if "bundle" in folder_name.lower() else "single"


def _safe_keyword(folder_name: str, kind: str) -> str:
    if kind == "bundle":
        parts = folder_name.split("_")
        keyword = parts[-1] if len(parts) > 1 else folder_name
    else:
        keyword = re.sub(r"^Se[A-Z]", "", folder_name) or folder_name  # odstraní prefix SeA, SeB...
    return re.sub(r"[^a-zA-Z0-9]", "", keyword) or "Product"


# ---------------------------------------------------------------------------
# Evidence už migrovaných složek
# ---------------------------------------------------------------------------
def _load_state(path: str) -> Dict[str, str]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_state(path: str, state: Dict[str, str]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Plán (dry-run)
# ---------------------------------------------------------------------------
def plan_migration(source_dir: str, state_path: str = STATE_PATH) -> List[dict]:
    """Seznam složek ke zpracování: typ, název po migraci (bez SKU), počet souborů, zda už byla migrována."""
    if not os.path.isdir(source_dir):
        return []
    state = _load_state(state_path)
    plan = []
    for folder in sorted(os.listdir(source_dir)):
        path = os.path.join(source_dir, folder)
        if not os.path.isdir(path):
            continue
        kind = detect_kind(folder)
        files = sum(len(names) for _, _, names in os.walk(path))
        plan.append({
            "folder": folder,
            "kind": kind,
            "keyword": _safe_keyword(folder, kind),
            "files": files,
            "already_migrated": folder in state,
            "migrated_as": state.get(folder, ""),
        })
    return plan


# ---------------------------------------------------------------------------
# Migrace jedné složky
# ---------------------------------------------------------------------------
def migrate_single(old_path: str, folder_name: str, sku: str, target_dir: str) -> str:
    safe_keyword = _safe_keyword(folder_name, "single")
    new_folder = f"{sku}_{safe_keyword}"
    new_path = os.path.join(target_dir, "Singles", new_folder)
    print(f"  📦 {folder_name} -> {new_folder}")

    for sub in ("01_Print_Files", "02_Marketing_Assets", "03_Metadata"):
        os.makedirs(os.path.join(new_path, sub), exist_ok=True)

    master_saved = False
    for f in sorted(os.listdir(old_path)):
        src = os.path.join(old_path, f)
        if not os.path.isfile(src):
            continue
        lower = f.lower()
        if lower.endswith(".png") and not master_saved:
            shutil.copy2(src, os.path.join(new_path, "00_Master_Source.png"))
            master_saved = True
        elif "_mockup" in lower:
            idx = len(os.listdir(os.path.join(new_path, "02_Marketing_Assets"))) + 1
            shutil.copy2(src, os.path.join(new_path, "02_Marketing_Assets", f"{idx:02d}_Mockup.jpg"))
        elif any(res in lower for res in PRINT_RESOLUTIONS):
            shutil.copy2(src, os.path.join(new_path, "01_Print_Files", f))

    listing = create_listing_data(sku, f"{safe_keyword} Wall Art - Digital Download",
                                  ["wall art", "printable", "digital download"])
    with open(os.path.join(new_path, "03_Metadata", "listing_data.json"), "w", encoding="utf-8") as f:
        json.dump(listing, f, indent=2, ensure_ascii=False)
    return new_path


def migrate_bundle(old_path: str, folder_name: str, sku: str, target_dir: str) -> str:
    safe_keyword = _safe_keyword(folder_name, "bundle")
    new_folder = f"{sku}_{safe_keyword}"
    new_path = os.path.join(target_dir, "Bundles", new_folder)
    print(f"  📦 {folder_name} -> {new_folder}")

    for sub in ("00_Masters", "01_Print_Files_Ready", "02_Marketing_Assets", "03_Metadata"):
        os.makedirs(os.path.join(new_path, sub), exist_ok=True)

    for item in sorted(os.listdir(old_path)):
        src = os.path.join(old_path, item)
        lower = item.lower()
        if os.path.isdir(src):
            if "_files" in lower:  # Art_X_Files -> 01_Print_Files_Ready/Art_X
                art_name = item.replace("_Files", "").replace("_files", "")
                letter = _art_letter(art_name.split("_")[1]) if "_" in art_name else "A"
                dst_dir = os.path.join(new_path, "01_Print_Files_Ready", f"Art_{letter}")
                if not os.path.exists(dst_dir):
                    shutil.copytree(src, dst_dir)
        elif os.path.isfile(src):
            if "_source" in lower and lower.endswith(".png"):
                letter = _art_letter(item.split("_")[1] if "_" in item else "1")
                shutil.copy2(src, os.path.join(new_path, "00_Masters", f"Art_{letter}.png"))
            elif "showcase" in lower:
                idx = len(os.listdir(os.path.join(new_path, "02_Marketing_Assets"))) + 1
                shutil.copy2(src, os.path.join(new_path, "02_Marketing_Assets", f"{idx:02d}_{item}"))
            elif "bundle_info" in lower:
                shutil.copy2(src, os.path.join(new_path, "03_Metadata", "BUNDLE_INFO.txt"))

    listing = create_listing_data(sku, f"{safe_keyword} Wall Art Bundle - Set of 5",
                                  ["wall art", "bundle", "printable set"])
    with open(os.path.join(new_path, "03_Metadata", "listing_data.json"), "w", encoding="utf-8") as f:
        json.dump(listing, f, indent=2, ensure_ascii=False)
    return new_path


# ---------------------------------------------------------------------------
# Hlavní vstup (CLI i GUI)
# ---------------------------------------------------------------------------
def run_migration(source_dir: str, target_dir: Optional[str] = None, dry_run: bool = True,
                  state_path: str = STATE_PATH) -> dict:
    """Zmigruje (nebo jen naplánuje) všechny dosud nemigrované složky. Vrací počty."""
    target_dir = target_dir or WAREHOUSE_DIR
    plan = plan_migration(source_dir, state_path)
    todo = [p for p in plan if not p["already_migrated"]]
    result = {"total": len(plan), "to_migrate": len(todo), "skipped": len(plan) - len(todo),
              "singles": 0, "bundles": 0, "failed": 0, "dry_run": dry_run}

    print(f"📁 Zdroj: {source_dir}")
    print(f"   Nalezeno {len(plan)} složek, k migraci {len(todo)}, už migrováno {result['skipped']}")
    if dry_run:
        for item in todo:
            print(f"  (náhled) {item['folder']} -> {item['kind']} '{item['keyword']}', souborů: {item['files']}")
        return result

    state = _load_state(state_path)
    for i, item in enumerate(todo):
        progress.check_cancel()
        progress.report(100.0 * i / max(len(todo), 1), f"Migrace {i + 1}/{len(todo)}: {item['folder']}")
        old_path = os.path.join(source_dir, item["folder"])
        try:
            if item["kind"] == "bundle":
                new_path = migrate_bundle(old_path, item["folder"], _next_sku("B"), target_dir)
                result["bundles"] += 1
            else:
                new_path = migrate_single(old_path, item["folder"], _next_sku("S"), target_dir)
                result["singles"] += 1
        except OSError as exc:
            result["failed"] += 1
            print(f"  ❌ {item['folder']}: {exc}")
            continue
        state[item["folder"]] = os.path.basename(new_path)
        _save_state(state_path, state)

    print(f"✅ Hotovo. Singles: {result['singles']}, Bundles: {result['bundles']}, selhalo: {result['failed']}")
    return result


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Migrace produktů do skladu 02_Warehouse")
    parser.add_argument("--source", default=default_source(), help="složka se starými produkty (01_Hotove_Produkty)")
    parser.add_argument("--target", default=WAREHOUSE_DIR, help="cílový sklad (výchozí automation/02_Warehouse)")
    parser.add_argument("--apply", action="store_true", help="provést migraci (bez toho jen náhled)")
    args = parser.parse_args(argv)

    if not os.path.isdir(args.source):
        print(f"❌ Zdrojová složka neexistuje: {args.source}")
        return 1
    result = run_migration(args.source, args.target, dry_run=not args.apply)
    if not args.apply and result["to_migrate"]:
        print("\nTohle byl jen náhled. Pro opravdovou migraci přidej --apply.")
    return 0 if result["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
