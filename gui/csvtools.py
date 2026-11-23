"""GUI-11: editor products.csv (vstup Selenium uploaderu) - čtení, validace a bezpečný zápis."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from . import core

CSV_PATH = core.PROJECT_ROOT / "products.csv"
SELECTORS_PATH = core.PROJECT_ROOT / "src" / "selectors.json"

# (sloupec, popisek) - sloupce zobrazené v editoru; další sloupce v souboru se zachovají beze změny
COLUMNS: List[Tuple[str, str]] = [
    ("title", "Titulek"),
    ("description", "Popis"),
    ("price", "Cena (prázdné = cena z Nastavení)"),
    ("tags", "Tagy (oddělené čárkou)"),
    ("category_path", "Kategorie"),
    ("image_paths", "Obrázky (cesty oddělené středníkem)"),
    ("shop_section", "Sekce obchodu"),
]
EDIT_KEYS = [key for key, _ in COLUMNS]

TITLE_MAX = 140
TAG_MAX_LEN = 20
TAG_MAX_COUNT = 13
MIN_PRICE = 0.2
MAX_ROWS = 500
MAX_WARNINGS = 20


def read_rows() -> Tuple[List[str], List[Dict[str, str]]]:
    """Vrátí (všechny sloupce souboru + chybějící editovatelné, řádky). Chybějící soubor = prázdný seznam."""
    header: List[str] = []
    rows: List[Dict[str, str]] = []
    try:
        with open(CSV_PATH, "r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            header = [h for h in (reader.fieldnames or []) if h]
            for row in reader:
                rows.append({k: (v or "") for k, v in row.items() if k})
    except FileNotFoundError:
        pass
    columns = header + [key for key in EDIT_KEYS if key not in header]
    for row in rows:
        for column in columns:
            row.setdefault(column, "")
    return columns, rows


def extra_columns(columns: List[str]) -> List[str]:
    return [c for c in columns if c not in EDIT_KEYS]


def form_to_rows(form, columns: List[str]) -> List[Dict[str, str]]:
    """Složí řádky z formuláře (pole f<i>__<sloupec>, políčko del<i> = smazat). Prázdné řádky se zahodí."""
    try:
        count = max(0, min(int(str(form.get("row_count", "0"))), MAX_ROWS))
    except ValueError:
        count = 0
    rows: List[Dict[str, str]] = []
    for i in range(count + 1):  # poslední index je prázdný řádek pro přidání nového produktu
        if form.get(f"del{i}") == "on":
            continue
        row = {c: str(form.get(f"f{i}__{c}", "")).replace("\r\n", "\n").strip() for c in columns}
        row["price"] = row.get("price", "").replace(",", ".")  # uploader posílá cenu na Etsy jako text
        if any(row.values()):
            rows.append(row)
    return rows


def _split(value: str, sep: str) -> List[str]:
    return [part.strip() for part in value.split(sep) if part.strip()]


def validate_rows(rows: List[Dict[str, str]]) -> List[str]:
    errors: List[str] = []
    for n, row in enumerate(rows, 1):
        prefix = f"Řádek {n}"
        title = row.get("title", "")
        if not title:
            errors.append(f"{prefix}: titulek nesmí být prázdný.")
        elif len(title) > TITLE_MAX:
            errors.append(f"{prefix}: titulek má {len(title)} znaků, Etsy povoluje max. {TITLE_MAX}.")
        price = row.get("price", "").replace(",", ".")
        if price:
            try:
                if float(price) < MIN_PRICE:
                    errors.append(f"{prefix}: cena musí být alespoň {MIN_PRICE}.")
            except ValueError:
                errors.append(f"{prefix}: cena „{row['price']}“ není platné číslo.")
        tags = _split(row.get("tags", ""), ",")
        if len(tags) > TAG_MAX_COUNT:
            errors.append(f"{prefix}: tagů je {len(tags)}, Etsy povoluje max. {TAG_MAX_COUNT}.")
        for tag in tags:
            if len(tag) > TAG_MAX_LEN:
                errors.append(f"{prefix}: tag „{tag}“ má {len(tag)} znaků, max. je {TAG_MAX_LEN}.")
    return errors


def image_warnings(rows: List[Dict[str, str]]) -> List[str]:
    """Upozornění na obrázky, které na disku nejsou (neblokuje uložení)."""
    warnings: List[str] = []
    for n, row in enumerate(rows, 1):
        for raw in _split(row.get("image_paths", ""), ";"):
            path = Path(raw).expanduser()
            if not path.is_absolute():
                path = core.PROJECT_ROOT / path
            if not path.is_file():
                warnings.append(f"Řádek {n}: obrázek nenalezen: {raw}")
                if len(warnings) >= MAX_WARNINGS:
                    warnings.append("…další upozornění nezobrazena.")
                    return warnings
    return warnings


def write_rows(columns: List[str], rows: List[Dict[str, str]]) -> None:
    tmp = CSV_PATH.with_name(CSV_PATH.name + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({c: row.get(c, "") for c in columns})
    tmp.replace(CSV_PATH)


def selectors_status() -> Dict[str, Any]:
    """Kolik selektorů v src/selectors.json je vyplněných (prázdné se nahradí výchozími)."""
    try:
        data = json.loads(SELECTORS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"total": 0, "empty": 0, "found": False}
    items = [v for k, v in data.items() if not k.startswith("_") and isinstance(v, dict)]
    return {"total": len(items), "empty": sum(1 for v in items if not v.get("primary")), "found": True}
