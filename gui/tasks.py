"""Úlohy GUI (běží na pozadí přes src/jobs.py) a pomocné funkce vstupní fronty obrázků.

`super_robot` se importuje líně až při první úloze, aby start GUI zůstal rychlý
(importuje Pillow, numpy, groq apod.).
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import core

MAX_UPLOAD_BYTES = 80 * 1024 * 1024
UPLOAD_EXTS = (".png", ".jpg", ".jpeg")
PROMPTS_PATH = core.PROJECT_ROOT / "data" / "prompts.json"


# ---------------------------------------------------------------------------
# Úlohy (volá je fronta úloh ve vlákně na pozadí)
# ---------------------------------------------------------------------------
def _robot():
    from automation import super_robot as sr  # těžké importy až tady

    sr.reload_config()  # změny z Nastavení se projeví bez restartu GUI
    return sr


def generate_bundle(theme: str = ""):
    """Vygeneruje Bundle. Vrací cestu ke složce, nebo False při selhání."""
    sr = _robot()
    result = sr.run_generation_mode(theme=(theme or "").strip() or None, interactive=False)
    if not result:
        raise RuntimeError("Generování bundlu selhalo (chybějící klíče nebo se nevygeneroval žádný obrázek). Podrobnosti jsou v logu úlohy.")
    return result


def process_queue():
    """Zpracuje obrázky z _To_Edit na Single produkty (při selhání všech vyhodí výjimku, ne "hotovo")."""
    result = _robot().run_solo_mode(interactive=False) or {}
    if result.get("failed") and not result.get("ok"):
        raise RuntimeError(f"Nepodařilo se zpracovat žádný obrázek ({result['failed']} selhalo). Podrobnosti jsou v logu úlohy.")
    return f"Vytvořeno {result.get('ok', 0)} produktů, selhalo {result.get('failed', 0)}."


def generate_from_list():
    """Vygeneruje produkty podle data/prompts.json (při úplném neúspěchu vyhodí výjimku, ne "hotovo")."""
    result = _robot().run_list_mode() or {}
    if result.get("failed") and not result.get("ok"):
        raise RuntimeError(f"Generování ze seznamu selhalo ({result['failed']} chyb). Podrobnosti jsou v logu úlohy.")
    return f"Hotovo: {result.get('ok', 0)}, selhalo: {result.get('failed', 0)}."


def prepare_archive_zip(product_dir: str):
    """Zabalí tiskové soubory produktu do jednoho ZIPu k nahrání na Drive/Dropbox (doručení bundlu přes odkaz)."""
    path = _robot().prepare_download_archive(product_dir)
    if not path:
        raise RuntimeError("ZIP se nepodařilo vytvořit. Podrobnosti jsou v logu úlohy.")
    return f"ZIP je připraven: {path}"


def publish_draft(product_dir: str):
    """Nahraje produkt na Etsy jako draft (bez zveřejnění)."""
    return _robot().publish_to_etsy(product_dir)


def activate_listing(product_dir: str):
    """Zveřejní dříve nahraný draft."""
    return _robot().activate_etsy_listing(product_dir)


def run_uploader(headless: bool = False):
    """Hromadný Selenium upload z products.csv. Vrací shrnutí; při úplném neúspěchu vyhodí výjimku."""
    os.chdir(core.PROJECT_ROOT)  # uploader a logger pracují s relativními cestami (logs/, ./images/...)
    core.reload_env()
    from src.uploader import EtsyUploader  # těžký import (selenium) až tady

    uploader = EtsyUploader(config_path=str(core.CONFIG_PATH),
                            selectors_file=str(core.PROJECT_ROOT / "src" / "selectors.json"))
    uploader.config["headless"] = bool(headless)
    try:
        results = uploader.run_bulk_upload(str(core.PROJECT_ROOT / "products.csv"))
    finally:  # i při zrušení nebo chybě zavřít okno prohlížeče
        driver = getattr(uploader, "driver", None)
        if driver is not None:
            try:
                driver.quit()
            except Exception:  # noqa: BLE001 - už může být zavřený
                pass
    total, ok, failed = results.get("total", 0), results.get("success", 0), results.get("failed", 0)
    summary = f"Nahráno {ok} z {total}, selhalo {failed}."
    if total == 0 or ok == 0:
        raise RuntimeError(summary + " Podrobnosti jsou v logu úlohy a ve složce logs/.")
    return summary


def run_migration(source: str):
    """Zmigruje staré produkty ze zdrojové složky do skladu (automation/02_Warehouse)."""
    from automation import migrate_products

    result = migrate_products.run_migration(source, dry_run=False)
    migrated = result["singles"] + result["bundles"]
    summary = (f"Zmigrováno {result['singles']} singles a {result['bundles']} bundlů, "
               f"přeskočeno {result['skipped']}, selhalo {result['failed']}.")
    if result["failed"] and not migrated:
        raise RuntimeError(summary)
    return summary


def archive_queue():
    """Přesune soubory z _To_Edit do 03_Archive/RRRR_MM."""
    _robot().archive_old_files()


# ---------------------------------------------------------------------------
# Pomocné funkce pro stránku Generovat
# ---------------------------------------------------------------------------
def missing_keys(keys: List[str]) -> List[str]:
    """Vrátí, které z klíčů nejsou nastavené (ani v .env, ani v prostředí)."""
    env = core.read_env(core.ENV_PATH)
    return [k for k in keys if not (env.get(k) or os.getenv(k))]


def topics_path() -> Path:
    """Soubor s tématy k obrázkům ve frontě (stejný jako `TOPICS_PATH` v super_robot)."""
    return core.TO_EDIT_DIR.parent / "topics.json"


def load_topics() -> Dict[str, str]:
    try:
        data = json.loads(topics_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}


def save_topics_from_form(form) -> int:
    """Uloží témata/klíčová slova z formuláře fronty (pole file_N / topic_N). Vrací počet uložených témat.

    Přijímají se jen soubory, které skutečně jsou ve frontě (ochrana proti podvrženým cestám).
    """
    in_queue = {item["name"].replace("\\", "/") for item in queue_files()}
    topics = {k: v for k, v in load_topics().items() if k in in_queue}
    try:
        count = min(int(str(form.get("n", "0")) or 0), 500)
    except ValueError:
        count = 0
    for i in range(count):
        name = str(form.get(f"file_{i}", "")).replace("\\", "/")
        if name not in in_queue:
            continue
        topic = " ".join(str(form.get(f"topic_{i}", "")).split())[:300]
        if topic:
            topics[name] = topic
        else:
            topics.pop(name, None)
    target = topics_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(json.dumps(topics, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(target)
    return len(topics)


def queue_files() -> List[Dict[str, Any]]:
    """Obrázky čekající ve vstupní frontě (včetně podsložek Batch_*) a jejich téma pro SEO."""
    base = core.TO_EDIT_DIR
    topics = load_topics()
    items: List[Dict[str, Any]] = []
    if base.is_dir():
        for path in sorted(base.rglob("*")):
            if path.is_file() and path.suffix.lower() in core.IMAGE_EXTS:
                rel = path.relative_to(base)
                items.append({"name": str(rel), "mb": round(path.stat().st_size / 1048576, 2),
                              "topic": topics.get(rel.as_posix(), "")})
    return items


def prompts_summary() -> Optional[str]:
    """Stručný popis obsahu data/prompts.json (nebo None, pokud chybí/je neplatný)."""
    try:
        data = json.loads(PROMPTS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    if "bundles" in data:
        return f"{len(data['bundles'])} definic bundlů"
    if "tasks" in data:
        return f"{len(data['tasks'])} promptů pro jednotlivé obrázky (uloží se do fronty _To_Edit)"
    if "prompts" in data:
        return f"{len(data['prompts'])} promptů pro jednotlivé obrázky (uloží se do fronty _To_Edit)"
    return None


def save_upload(filename: str, fileobj) -> Tuple[bool, str]:
    """Uloží nahraný obrázek do fronty _To_Edit. Vrací (ok, zpráva)."""
    name = Path(filename or "").name
    stem, ext = Path(name).stem, Path(name).suffix.lower()
    if ext not in UPLOAD_EXTS:
        return False, f"{name or '(bez názvu)'}: povolené jsou jen PNG a JPG."

    safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._") or "image"
    core.TO_EDIT_DIR.mkdir(parents=True, exist_ok=True)
    target = core.TO_EDIT_DIR / f"{safe_stem}{ext}"
    counter = 1
    while target.exists():
        target = core.TO_EDIT_DIR / f"{safe_stem}_{counter}{ext}"
        counter += 1

    written = 0
    try:
        with open(target, "wb") as out:
            while True:
                chunk = fileobj.read(1024 * 1024)
                if not chunk:
                    break
                written += len(chunk)
                if written > MAX_UPLOAD_BYTES:
                    raise ValueError(f"větší než {MAX_UPLOAD_BYTES // 1048576} MB")
                out.write(chunk)
        from PIL import Image  # ověření, že jde opravdu o obrázek

        with Image.open(target) as img:
            img.verify()
    except Exception as exc:  # noqa: BLE001 - uživateli ukážeme důvod
        try:
            target.unlink(missing_ok=True)
        except OSError:
            pass
        return False, f"{name}: {exc}"
    return True, target.name
