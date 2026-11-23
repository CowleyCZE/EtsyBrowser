"""GUI-4: sklad produktů - výpis, detail a úprava metadat (listing_data.json)."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import core

KINDS = {"single": ("Single", core.SINGLES_DIR), "bundle": ("Bundle", core.BUNDLES_DIR)}
MEDIA_EXTS = (".jpg", ".jpeg", ".png")
TITLE_MAX = 140
TAG_MAX_LEN = 20
TAG_MAX_COUNT = 13


def _safe_name(name: str) -> bool:
    return bool(name) and name not in (".", "..") and "/" not in name and "\\" not in name


def product_dir(kind: str, folder: str) -> Path:
    """Bezpečně vyřeší složku produktu; vyhodí FileNotFoundError při neplatném vstupu."""
    if kind not in KINDS or not _safe_name(folder):
        raise FileNotFoundError("Produkt nenalezen.")
    base = KINDS[kind][1].resolve()
    path = (base / folder).resolve()
    if path.parent != base or not path.is_dir():
        raise FileNotFoundError("Produkt nenalezen.")
    return path


def _marketing_images(path: Path) -> List[str]:
    folder = path / "02_Marketing_Assets"
    if not folder.is_dir():
        return []
    return sorted(f.name for f in folder.iterdir() if f.is_file() and f.suffix.lower() in MEDIA_EXTS)


def _read_meta(path: Path) -> Dict[str, Any]:
    try:
        return json.loads((path / "03_Metadata" / "listing_data.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def list_products(query: str = "", status: str = "") -> List[Dict[str, Any]]:
    query = query.strip().lower()
    items = []
    for kind_key, (kind_label, base) in KINDS.items():
        if not base.is_dir():
            continue
        for folder in base.iterdir():
            if not folder.is_dir():
                continue
            meta = _read_meta(folder)
            etsy = meta.get("etsy") or {}
            item_status = core.STATUS_LABELS.get(etsy.get("state"), "nový")
            title = meta.get("title") or folder.name
            if status and item_status != status:
                continue
            if query and query not in f"{title} {folder.name} {meta.get('sku', '')}".lower():
                continue
            images = _marketing_images(folder)
            items.append(
                {
                    "kind": kind_key,
                    "kind_label": kind_label,
                    "folder": folder.name,
                    "sku": meta.get("sku", ""),
                    "title": title,
                    "status": item_status,
                    "thumb": images[0] if images else None,
                    "mtime": folder.stat().st_mtime,
                    "date": datetime.fromtimestamp(folder.stat().st_mtime).strftime("%d.%m.%Y"),
                }
            )
    items.sort(key=lambda i: i["mtime"], reverse=True)
    return items


def get_product(kind: str, folder: str) -> Dict[str, Any]:
    path = product_dir(kind, folder)
    meta = _read_meta(path)
    etsy = meta.get("etsy") or {}
    return {
        "kind": kind,
        "kind_label": KINDS[kind][0],
        "folder": folder,
        "sku": meta.get("sku", ""),
        "title": meta.get("title", ""),
        "description": meta.get("description_generated", ""),
        "tags": ", ".join(meta.get("seo_tags", [])),
        "price": (meta.get("pricing") or {}).get("amount", ""),
        "status": core.STATUS_LABELS.get(etsy.get("state"), "nový"),
        "listing_id": etsy.get("listing_id"),
        "files_uploaded": bool(etsy.get("files_uploaded")),
        "images": _marketing_images(path),
        "has_meta": bool(meta),
        "currency": (meta.get("pricing") or {}).get("currency", "EUR"),
        "download_url": str((meta.get("delivery") or {}).get("download_url", "")),
        "warnings": [str(w) for w in meta.get("warnings", [])] if isinstance(meta.get("warnings"), list) else [],
        "seo_generated": meta.get("seo_generated", True),
        "external_delivery": kind == "bundle",
        "zip_ready": any(path.glob("04_Delivery/*_Full_Print_Files.zip")),
    }


def save_download_url(kind: str, folder: str, url: str) -> List[str]:
    """Uloží odkaz ke stažení plné kvality (Drive/Dropbox) k produktu. Prázdný odkaz ho smaže."""
    path = product_dir(kind, folder)
    meta = _read_meta(path)
    if not meta:
        return ["Produkt nemá soubor listing_data.json."]
    url = url.strip()
    if url and not re.match(r"^https?://\S+$", url):
        return ["Odkaz musí začínat http:// nebo https:// a nesmí obsahovat mezery."]
    delivery = meta.setdefault("delivery", {})
    if url:
        delivery["download_url"] = url
    else:
        delivery.pop("download_url", None)
    target = path / "03_Metadata" / "listing_data.json"
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(target)
    return []


def save_product(kind: str, folder: str, form) -> List[str]:
    """Zvaliduje a uloží úpravy. Vrací seznam chyb (prázdný = uloženo)."""
    path = product_dir(kind, folder)
    meta = _read_meta(path)
    if not meta:
        return ["Produkt nemá soubor listing_data.json, nelze ho upravit."]

    errors: List[str] = []
    title = " ".join(str(form.get("title", "")).split())
    if not title:
        errors.append("Titulek nesmí být prázdný.")
    elif len(title) > TITLE_MAX:
        errors.append(f"Titulek má {len(title)} znaků, Etsy povoluje max. {TITLE_MAX}.")

    tags: List[str] = []
    for raw in str(form.get("tags", "")).split(","):
        tag = raw.strip()
        if not tag:
            continue
        if len(tag) > TAG_MAX_LEN:
            errors.append(f"Tag „{tag}“ má {len(tag)} znaků, max. je {TAG_MAX_LEN}.")
        elif tag.lower() not in [t.lower() for t in tags]:
            tags.append(tag)
    if len(tags) > TAG_MAX_COUNT:
        errors.append(f"Tagů je {len(tags)}, Etsy povoluje max. {TAG_MAX_COUNT}.")

    price_raw = str(form.get("price", "")).strip().replace(",", ".")
    price: Optional[float] = None
    try:
        price = float(price_raw)
        if price < 0.2:
            errors.append("Cena musí být alespoň 0.20.")
    except ValueError:
        errors.append(f"Cena „{price_raw}“ není platné číslo.")

    if errors:
        return errors

    meta["title"] = title
    meta["description_generated"] = str(form.get("description", "")).strip()
    meta["seo_tags"] = tags
    meta.setdefault("pricing", {})["currency"] = "EUR"  # obchod počítá v EUR (X-1)
    meta["pricing"]["amount"] = price
    target = path / "03_Metadata" / "listing_data.json"
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(target)
    return []


def media_path(kind: str, folder: str, filename: str) -> Path:
    path = product_dir(kind, folder)
    if not _safe_name(filename) or Path(filename).suffix.lower() not in MEDIA_EXTS:
        raise FileNotFoundError("Soubor nenalezen.")
    file = path / "02_Marketing_Assets" / filename
    if not file.is_file():
        raise FileNotFoundError("Soubor nenalezen.")
    return file
