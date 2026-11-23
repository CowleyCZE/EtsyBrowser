"""GUI-8: Mockupy - výběr šablony, náhled s vlastním obrázkem a stažení výsledku.

Vykreslení dělá `automation.super_robot.render_mockup`, takže GUI a generování
produktů používají přesně stejný kód. `super_robot` se importuje líně až při
prvním náhledu (těžké knihovny).
"""

from __future__ import annotations

import io
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import core

TEMPLATES_DIR = core.PROJECT_ROOT / "automation" / "1_Mockup_Sablony"
TEMPLATES_JSON = core.PROJECT_ROOT / "data" / "mockup_templates.json"
PREVIEW_DIR = core.PROJECT_ROOT / "data" / "mockup_preview"
ART_NAME = "art.png"

UPLOAD_EXTS = (".png", ".jpg", ".jpeg")
MAX_UPLOAD_BYTES = 80 * 1024 * 1024
ART_MAX_SIDE = 2400      # nahraný obrázek se zmenší, aby byl náhled rychlý
PREVIEW_MAX_SIDE = 1400  # náhled v prohlížeči; stažení je v plné velikosti šablony


def _safe_name(name: str) -> bool:
    return bool(name) and name not in (".", "..") and "/" not in name and "\\" not in name


# ---------------------------------------------------------------------------
# Šablony
# ---------------------------------------------------------------------------
def _config_index() -> Dict[str, Tuple[str, Dict[str, Any]]]:
    """filename -> (kategorie, konfigurace) z data/mockup_templates.json."""
    try:
        data = json.loads(TEMPLATES_JSON.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    index: Dict[str, Tuple[str, Dict[str, Any]]] = {}
    if isinstance(data, dict):
        for category, configs in data.items():
            if not isinstance(configs, list):
                continue
            for cfg in configs:
                if isinstance(cfg, dict) and cfg.get("filename"):
                    index[str(cfg["filename"])] = (str(category), cfg)
    return index


def list_templates() -> List[Dict[str, Any]]:
    if not TEMPLATES_DIR.is_dir():
        return []
    index = _config_index()
    items: List[Dict[str, Any]] = []
    for path in sorted(TEMPLATES_DIR.iterdir()):
        if not path.is_file() or path.suffix.lower() != ".png":
            continue
        category, cfg = index.get(path.name, ("", None))
        if cfg is None:
            mode, label = "none", "bez konfigurace"
        elif "corners" in cfg:
            mode, label = "perspective", "perspektiva (4 rohy)"
        else:
            mode, label = "rect", "obdélník"
        items.append({"name": path.name, "category": category, "mode": mode, "mode_label": label,
                      "configured": cfg is not None})
    return items


def template_path(name: str) -> Path:
    """Bezpečně vyřeší cestu k šabloně; vyhodí FileNotFoundError při neplatném vstupu."""
    if not _safe_name(name) or Path(name).suffix.lower() != ".png":
        raise FileNotFoundError("Šablona nenalezena.")
    base = TEMPLATES_DIR.resolve()
    path = (base / name).resolve()
    if path.parent != base or not path.is_file():
        raise FileNotFoundError("Šablona nenalezena.")
    return path


def template_config(name: str) -> Optional[Dict[str, Any]]:
    entry = _config_index().get(name)
    return entry[1] if entry else None


# ---------------------------------------------------------------------------
# Obrázek pro náhled
# ---------------------------------------------------------------------------
def art_path() -> Tuple[Optional[Path], str]:
    """Obrázek použitý v náhledech: nahraný, jinak TEST_ART_PATH z .env. Vrací (cesta|None, popisek)."""
    uploaded = PREVIEW_DIR / ART_NAME
    if uploaded.is_file():
        return uploaded, "nahraný obrázek"
    value = core.read_env(core.ENV_PATH).get("TEST_ART_PATH") or os.environ.get("TEST_ART_PATH") or ""
    if value:
        candidate = Path(value).expanduser()
        if candidate.is_file():
            return candidate, "testovací obrázek z Nastavení (TEST_ART_PATH)"
    return None, ""


def art_version() -> int:
    path, _ = art_path()
    try:
        return int(path.stat().st_mtime) if path else 0
    except OSError:
        return 0


def save_art(filename: str, fileobj) -> Tuple[bool, str]:
    """Uloží nahraný obrázek jako PNG pro náhledy. Vrací (ok, název souboru nebo důvod chyby)."""
    name = Path(filename or "").name
    if Path(name).suffix.lower() not in UPLOAD_EXTS:
        return False, f"{name or '(bez názvu)'}: povolené jsou jen PNG a JPG."
    data = fileobj.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        return False, f"{name}: soubor je větší než {MAX_UPLOAD_BYTES // 1048576} MB."
    try:
        from PIL import Image

        with Image.open(io.BytesIO(data)) as img:
            img.load()
            art = img.convert("RGBA") if "A" in img.mode else img.convert("RGB")
        art.thumbnail((ART_MAX_SIDE, ART_MAX_SIDE), Image.Resampling.LANCZOS)
        PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
        tmp = PREVIEW_DIR / (ART_NAME + ".tmp")
        art.save(tmp, "PNG")
        tmp.replace(PREVIEW_DIR / ART_NAME)
    except Exception as exc:  # noqa: BLE001 - důvod ukážeme uživateli
        return False, f"{name}: {exc}"
    return True, name


def clear_art() -> None:
    try:
        (PREVIEW_DIR / ART_NAME).unlink(missing_ok=True)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Vykreslení
# ---------------------------------------------------------------------------
def _robot():
    if str(core.PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(core.PROJECT_ROOT))
    from automation import super_robot as sr  # těžké importy až tady

    return sr


def render(name: str, full: bool = False) -> bytes:
    """Vloží obrázek do šablony a vrátí JPEG.

    FileNotFoundError = šablona neexistuje, LookupError = není vybrán žádný obrázek.
    `full=True` vrací plnou velikost šablony (pro stažení), jinak zmenšený náhled.
    """
    path = template_path(name)
    source, _ = art_path()
    if source is None:
        raise LookupError("Nejdřív nahraj obrázek, který se do šablony vloží.")
    sr = _robot()
    config = template_config(name) or sr.DEFAULT_MOCKUP_CONFIG

    from PIL import Image

    with Image.open(source) as art:
        art.load()
        result = sr.render_mockup(art, str(path), config)
    if not full:
        result.thumbnail((PREVIEW_MAX_SIDE, PREVIEW_MAX_SIDE), Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    result.save(buffer, "JPEG", quality=95 if full else 88)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# GUI-9: Editor šablon (kalibrace rámu)
# ---------------------------------------------------------------------------
CATEGORY_MAX_LEN = 60
MIN_FRAME_SIDE = 10


def template_size(name: str) -> Tuple[int, int]:
    from PIL import Image

    with Image.open(template_path(name)) as img:
        return img.size


def categories() -> List[str]:
    try:
        data = json.loads(TEMPLATES_JSON.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [str(k) for k in data] if isinstance(data, dict) else []


def editor_points(name: str) -> Tuple[str, List[List[int]]]:
    """Uložené body šablony pro editor: (režim 'perspective'|'rect', body)."""
    cfg = template_config(name)
    if not cfg:
        return "perspective", []
    if "corners" in cfg:
        return "perspective", [[int(x), int(y)] for x, y in cfg["corners"]]
    x, y, w, h = (int(cfg.get(k, 0)) for k in ("x", "y", "w", "h"))
    return "rect", [[x, y], [x + w, y + h]]


def _cross(o, a, b) -> float:
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _parse_points(raw: str) -> Optional[List[List[int]]]:
    try:
        data = json.loads(raw)
        return [[int(round(float(p[0]))), int(round(float(p[1])))] for p in data]
    except (ValueError, TypeError, IndexError, KeyError):
        return None


def _write_templates(data: Dict[str, Any]) -> None:
    tmp = TEMPLATES_JSON.with_name(TEMPLATES_JSON.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(TEMPLATES_JSON)


def _load_templates_data() -> Dict[str, Any]:
    try:
        data = json.loads(TEMPLATES_JSON.read_text(encoding="utf-8"))
    except OSError:
        return {}
    except ValueError:
        raise ValueError("Soubor mockup_templates.json je poškozený, oprav ho ručně.")
    return data if isinstance(data, dict) else {}


def save_template_config(name: str, category: str, mode: str, raw_points: str) -> List[str]:
    """Zvaliduje a uloží rám šablony do mockup_templates.json. Vrací seznam chyb (prázdný = uloženo)."""
    try:
        width, height = template_size(name)
    except FileNotFoundError:
        return ["Šablona nenalezena."]
    category = " ".join(category.split())
    if not category or len(category) > CATEGORY_MAX_LEN:
        return [f"Kategorie je povinná (max. {CATEGORY_MAX_LEN} znaků)."]
    points = _parse_points(raw_points)
    if points is None:
        return ["Neplatné souřadnice bodů."]
    expected = {"perspective": 4, "rect": 2}.get(mode)
    if expected is None:
        return ["Neznámý režim."]
    if len(points) != expected:
        return [f"Pro tento režim je potřeba označit přesně {expected} bodů, označeno {len(points)}."]
    if any(not (0 <= x <= width and 0 <= y <= height) for x, y in points):
        return [f"Body musí ležet uvnitř šablony ({width}×{height} px)."]

    xs, ys = [p[0] for p in points], [p[1] for p in points]
    x, y, w, h = min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)
    if w < MIN_FRAME_SIDE or h < MIN_FRAME_SIDE:
        return [f"Rám je moc malý (min. {MIN_FRAME_SIDE} px na každou stranu)."]

    entry: Dict[str, Any] = {"filename": name, "x": x, "y": y, "w": w, "h": h}
    if mode == "perspective":
        # pořadí TL, TR, BR, BL: všechny odběry hran stejným směrem = konvexní čtyřúhelník bez křížení
        signs = [_cross(points[i], points[(i + 1) % 4], points[(i + 2) % 4]) for i in range(4)]
        if not (all(s > 0 for s in signs) or all(s < 0 for s in signs)):
            return ["Body nejsou ve správném pořadí. Označ je postupně: levý horní, pravý horní, "
                    "pravý dolní, levý dolní (kolem dokola, bez křížení)."]
        entry["corners"] = points

    try:
        data = _load_templates_data()
    except ValueError as exc:
        return [str(exc)]
    for configs in data.values():
        if isinstance(configs, list):
            configs[:] = [c for c in configs if not (isinstance(c, dict) and c.get("filename") == name)]
    data.setdefault(category, []).append(entry)
    _write_templates(data)
    return []


def remove_template_config(name: str) -> List[str]:
    try:
        template_path(name)
        data = _load_templates_data()
    except (FileNotFoundError, ValueError) as exc:
        return [str(exc)]
    for configs in data.values():
        if isinstance(configs, list):
            configs[:] = [c for c in configs if not (isinstance(c, dict) and c.get("filename") == name)]
    _write_templates(data)
    return []
