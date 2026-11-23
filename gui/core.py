"""Jádro GUI: práce s konfigurací, .env, stavem tokenu a skladem produktů.

Záměrně NEimportuje super_robot (ten při importu vytváří složky a načítá těžké
knihovny). GUI tak zůstane rychlé a bezpečně importovatelné.
"""

from __future__ import annotations

import importlib.util
import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"
CONFIG_PATH = PROJECT_ROOT / "config.json"
OAUTH_DIR = PROJECT_ROOT / "oauth"
OAUTH_ENV_PATH = OAUTH_DIR / ".env"
TOKEN_FILE = OAUTH_DIR / "etsy_tokens.json"

WAREHOUSE_DIR = PROJECT_ROOT / "automation" / "02_Warehouse"
SINGLES_DIR = WAREHOUSE_DIR / "Singles"
BUNDLES_DIR = WAREHOUSE_DIR / "Bundles"
TO_EDIT_DIR = PROJECT_ROOT / "automation" / "00_Input_Queue" / "_To_Edit"

IMAGE_EXTS = (".png", ".jpg", ".jpeg")

# (soubor, klíč, popisek, tajné?)
ENV_FIELDS = [
    ("env", "ETSY_EMAIL", "E-mail k Etsy účtu (Selenium upload)", False),
    ("env", "ETSY_PASSWORD", "Heslo k Etsy účtu (Selenium upload)", True),
    ("env", "GROQ_API_KEY", "Groq API klíč", True),
    ("env", "POLLINATIONS_API_KEY", "Pollinations API klíč", True),
    ("env", "POLLINATIONS_SEED", "Seed obrázků (prázdné = náhodný)", False),
    ("env", "ETSY_API_KEY", "Etsy API klíč (keystring)", True),
    ("env", "ETSY_SHOP_ID", "Etsy shop_id", False),
    ("env", "ETSY_TAXONOMY_ID", "Etsy taxonomy_id (prázdné = zjistí se automaticky)", False),
    ("env", "TEST_ART_PATH", "Testovací obrázek pro mockupy", False),
    ("oauth", "ETSY_SHARED_SECRET", "Etsy shared secret (oauth/.env)", True),
]
ENV_FILES = {"env": ENV_PATH, "oauth": OAUTH_ENV_PATH}


# ---------------------------------------------------------------------------
# .env
# ---------------------------------------------------------------------------
def read_env(path: Path) -> Dict[str, str]:
    values: Dict[str, str] = {}
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.startswith("export "):
                line = line[7:].strip()
            key, value = line.split("=", 1)
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                value = value[1:-1]
            values[key.strip()] = value
    except OSError:
        pass
    return values


def _format_env_value(value: str) -> str:
    if value == "" or not any(c in value for c in " #\"'"):
        return value
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def write_env_updates(path: Path, updates: Dict[str, str]) -> None:
    """Změní/přidá klíče v .env a zachová komentáře i ostatní řádky. Zápis je atomický (práva 600)."""
    if not updates:
        return
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []

    remaining = dict(updates)
    out: List[str] = []
    for raw in lines:
        stripped = raw.strip()
        key = None
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].replace("export ", "").strip()
        if key in remaining:
            out.append(f"{key}={_format_env_value(remaining.pop(key))}")
        else:
            out.append(raw)
    for key, value in remaining.items():
        out.append(f"{key}={_format_env_value(value)}")

    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text("\n".join(out) + "\n", encoding="utf-8")
    if os.name == "posix":
        os.chmod(tmp, 0o600)
    tmp.replace(path)


def reload_env() -> None:
    """Znovu načte .env do os.environ (po změně nastavení)."""
    load_dotenv(ENV_PATH, override=True)


def mask_secret(value: str) -> str:
    if not value:
        return "nenastaveno"
    if len(value) <= 8:
        return "••••"
    return "••••••" + value[-4:]


# ---------------------------------------------------------------------------
# config.json
# ---------------------------------------------------------------------------
def read_config() -> Dict[str, Any]:
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def write_config(cfg: Dict[str, Any]) -> None:
    tmp = CONFIG_PATH.with_name(CONFIG_PATH.name + ".tmp")
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(CONFIG_PATH)


def settings_view() -> Dict[str, Any]:
    """Data pro stránku Nastavení (tajné hodnoty jen maskovaně)."""
    cfg = read_config()
    env_values = {name: read_env(path) for name, path in ENV_FILES.items()}
    fields = []
    for file_key, key, label, secret in ENV_FIELDS:
        value = env_values[file_key].get(key, "")
        fields.append(
            {
                "name": f"{file_key}__{key}",
                "label": label,
                "secret": secret,
                "value": "" if secret else value,
                "masked": mask_secret(value) if secret else "",
                "is_set": bool(value),
            }
        )
    return {
        "fields": fields,
        "prices": cfg.get("prices", {}),
        "groq": cfg.get("groq", {}),
        "cfg": cfg,
    }


def _num(form, name: str, kind, minimum, errors: List[str], label: str):
    raw = str(form.get(name, "")).strip().replace(",", ".")
    if raw == "":
        return None
    try:
        value = kind(raw)
    except ValueError:
        errors.append(f"{label}: '{raw}' není platné číslo.")
        return None
    if value < minimum:
        errors.append(f"{label}: hodnota musí být alespoň {minimum}.")
        return None
    return value


def apply_settings(form) -> List[str]:
    """Zvaliduje a uloží formulář Nastavení. Vrací seznam chyb (prázdný = uloženo)."""
    errors: List[str] = []
    cfg = read_config()

    price_single = _num(form, "price_single", float, 0.2, errors, "Cena Single")
    price_bundle = _num(form, "price_bundle", float, 0.2, errors, "Cena Bundle")
    delay_min = _num(form, "delay_min", float, 0, errors, "Zpoždění min")
    delay_max = _num(form, "delay_max", float, 0, errors, "Zpoždění max")
    max_per_hour = _num(form, "max_products_per_hour", int, 1, errors, "Limit produktů za hodinu")
    groq_timeout = _num(form, "groq_timeout", float, 5, errors, "Groq timeout")
    groq_retries = _num(form, "groq_max_retries", int, 0, errors, "Groq opakování")
    if delay_min is not None and delay_max is not None and delay_min > delay_max:
        errors.append("Zpoždění: minimum nesmí být větší než maximum.")

    seed = str(form.get("env__POLLINATIONS_SEED", "")).strip()
    if seed and not seed.isdigit():
        errors.append("Seed obrázků musí být celé číslo (nebo prázdné).")
    shop_id = str(form.get("env__ETSY_SHOP_ID", "")).strip()
    if shop_id and not shop_id.isdigit():
        errors.append("Etsy shop_id musí být číslo.")
    tax_id = str(form.get("env__ETSY_TAXONOMY_ID", "")).strip()
    if tax_id and not tax_id.isdigit():
        errors.append("Etsy taxonomy_id musí být číslo.")

    if errors:
        return errors

    prices = cfg.setdefault("prices", {})
    if price_single is not None:
        prices["single"] = price_single
    if price_bundle is not None:
        prices["bundle"] = price_bundle
    if delay_min is not None:
        cfg["delay_min"] = delay_min
    if delay_max is not None:
        cfg["delay_max"] = delay_max
    if max_per_hour is not None:
        cfg["max_products_per_hour"] = max_per_hour
    cfg["headless"] = form.get("headless") == "on"
    etsy_url = str(form.get("etsy_url", "")).strip()
    if etsy_url:
        cfg["etsy_url"] = etsy_url
    groq = cfg.setdefault("groq", {})
    model = str(form.get("groq_model", "")).strip()
    if model:
        groq["model"] = model
    if groq_timeout is not None:
        groq["timeout"] = groq_timeout
    if groq_retries is not None:
        groq["max_retries"] = groq_retries
    write_config(cfg)

    updates: Dict[str, Dict[str, str]] = {"env": {}, "oauth": {}}
    for file_key, key, _label, secret in ENV_FIELDS:
        raw = form.get(f"{file_key}__{key}")
        if raw is None:
            continue
        value = str(raw).strip()
        if secret and value == "":
            continue  # prázdné tajné pole = beze změny
        updates[file_key][key] = value
    for file_key, items in updates.items():
        write_env_updates(ENV_FILES[file_key], items)
    reload_env()
    return []


# ---------------------------------------------------------------------------
# Stav Etsy tokenu
# ---------------------------------------------------------------------------
def token_status() -> Dict[str, Any]:
    """Stav připojení k Etsy podle oauth/etsy_tokens.json (bez volání API)."""
    try:
        data = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"state": "missing", "label": "Nepřipojeno", "kind": "bad",
                "detail": "Chybí soubor s tokeny. Klikni na „Připojit k Etsy“."}
    if not data.get("access_token") or not data.get("refresh_token"):
        return {"state": "missing", "label": "Nepřipojeno", "kind": "bad",
                "detail": "Soubor s tokeny je neúplný. Připoj se k Etsy znovu."}

    expires_at = data.get("expires_at_unix")
    if isinstance(expires_at, (int, float)):
        remaining = int(expires_at - time.time())
        until = datetime.fromtimestamp(expires_at, tz=timezone.utc).astimezone().strftime("%d.%m.%Y %H:%M")
        if remaining > 120:
            return {"state": "valid", "label": "Připojeno", "kind": "ok",
                    "detail": f"Přístupový token platí do {until} (poté se sám obnoví)."}
        return {"state": "refreshable", "label": "Připojeno (token se obnoví)", "kind": "ok",
                "detail": "Přístupový token vypršel, při dalším volání API se automaticky obnoví. "
                          "Pokud se obnova nezdaří (refresh token platí 90 dní), připoj se znovu."}
    return {"state": "unknown", "label": "Připojeno", "kind": "ok", "detail": "Platnost tokenu není známa."}


# ---------------------------------------------------------------------------
# Test spojení a OAuth na pozadí
# ---------------------------------------------------------------------------
def test_etsy_connection() -> Dict[str, Any]:
    """Zavolá Etsy API (get_shop_info). Vrací {'ok': bool, 'message': str, 'shop_name', 'shop_id'}."""
    reload_env()
    from automation.etsy_api import EtsyClient, EtsyAuthError  # lokální import: až když je potřeba

    try:
        client = EtsyClient.from_env()
    except EtsyAuthError as exc:
        return {"ok": False, "message": str(exc)}
    info = client.get_shop_info()
    if not info:
        return {"ok": False, "message": "Etsy nevrátilo informace o obchodě. Zkontroluj klíče, shop_id a připojení "
                                         "(podrobnosti jsou v konzoli, kde běží GUI)."}
    return {"ok": True, "message": "Spojení s Etsy funguje.",
            "shop_name": info.get("shop_name"), "shop_id": info.get("shop_id")}


_oauth_lock = threading.Lock()
oauth_state: Dict[str, Any] = {"running": False, "log": [], "error": None, "done": False, "result": None}


def _load_oauth_module():
    spec = importlib.util.spec_from_file_location("get_etsy_token", OAUTH_DIR / "get_etsy_token.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _oauth_worker() -> None:
    def log(message: str) -> None:
        with _oauth_lock:
            oauth_state["log"].append(str(message))

    try:
        reload_env()  # ETSY_API_KEY může být jen v kořenovém .env (Nastavení ho ukládá tam)
        # prázdné hodnoty z kořenového .env nesmějí zastínit klíč uložený v oauth/.env
        for key in ("ETSY_API_KEY", "ETSY_SHARED_SECRET", "ETSY_REDIRECT_URI", "ETSY_SCOPES"):
            if not os.environ.get(key):
                os.environ.pop(key, None)
        module = _load_oauth_module()
        result = module.authorize(log)
        if result.get("shop_id") and not read_env(ENV_PATH).get("ETSY_SHOP_ID"):
            write_env_updates(ENV_PATH, {"ETSY_SHOP_ID": str(result["shop_id"])})
            reload_env()
        with _oauth_lock:
            oauth_state["result"] = result
    except Exception as exc:  # noqa: BLE001 - chybu zobrazíme uživateli
        with _oauth_lock:
            oauth_state["error"] = str(exc)
    finally:
        with _oauth_lock:
            oauth_state["running"] = False
            oauth_state["done"] = True


def start_oauth() -> bool:
    """Spustí autorizaci na pozadí. Vrací False, pokud už jedna běží."""
    with _oauth_lock:
        if oauth_state["running"]:
            return False
        oauth_state.update({"running": True, "log": [], "error": None, "done": False, "result": None})
    threading.Thread(target=_oauth_worker, daemon=True).start()
    return True


def oauth_snapshot() -> Dict[str, Any]:
    with _oauth_lock:
        return {**oauth_state, "log": list(oauth_state["log"])}


# ---------------------------------------------------------------------------
# Sklad produktů
# ---------------------------------------------------------------------------
STATUS_LABELS = {"active": "publikováno", "draft": "draft na Etsy"}


def list_products() -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for kind, base in (("Single", SINGLES_DIR), ("Bundle", BUNDLES_DIR)):
        if not base.is_dir():
            continue
        for folder in base.iterdir():
            if not folder.is_dir():
                continue
            data: Dict[str, Any] = {}
            try:
                data = json.loads((folder / "03_Metadata" / "listing_data.json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                pass
            etsy = data.get("etsy") or {}
            items.append(
                {
                    "kind": kind,
                    "folder": folder.name,
                    "sku": data.get("sku", ""),
                    "title": data.get("title") or folder.name,
                    "status": STATUS_LABELS.get(etsy.get("state"), "nový"),
                    "listing_id": etsy.get("listing_id"),
                    "mtime": folder.stat().st_mtime,
                }
            )
    items.sort(key=lambda i: i["mtime"], reverse=True)
    return items


def dashboard_data() -> Dict[str, Any]:
    products = list_products()
    queue = 0
    if TO_EDIT_DIR.is_dir():
        queue = sum(1 for f in TO_EDIT_DIR.rglob("*") if f.is_file() and f.suffix.lower() in IMAGE_EXTS)
    for p in products:
        p["date"] = datetime.fromtimestamp(p["mtime"]).strftime("%d.%m.%Y %H:%M")
    return {
        "token": token_status(),
        "singles": sum(1 for p in products if p["kind"] == "Single"),
        "bundles": sum(1 for p in products if p["kind"] == "Bundle"),
        "drafts": sum(1 for p in products if p["status"] == "draft na Etsy"),
        "published": sum(1 for p in products if p["status"] == "publikováno"),
        "queue": queue,
        "recent": products[:8],
    }
