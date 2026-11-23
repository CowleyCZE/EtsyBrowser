#!/usr/bin/env python3
"""Získání Etsy OAuth 2.0 tokenů pomocí Authorization Code + PKCE.

Konfiguraci načítá z proměnných prostředí nebo ze souboru .env vedle skriptu.
Po úspěšné autorizaci uloží tokeny do etsy_tokens.json s omezenými právy.
"""

from __future__ import annotations

import base64
import hashlib
import html
import json
import os
import secrets
import sys
import time
import urllib.parse
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import requests


BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"
TOKEN_FILE = BASE_DIR / "etsy_tokens.json"

AUTHORIZE_URL = "https://www.etsy.com/oauth/connect"
TOKEN_URL = "https://api.etsy.com/v3/public/oauth/token"
SHOP_URL_TEMPLATE = "https://api.etsy.com/v3/application/users/{user_id}/shops"

DEFAULT_REDIRECT_URI = "http://localhost:3003/oauth/redirect"
DEFAULT_SCOPES = "shops_r listings_r listings_w"
CALLBACK_TIMEOUT_SECONDS = 300
HTTP_TIMEOUT = (5, 20)  # (připojení, čtení)


class EtsyOAuthError(RuntimeError):
    """Chyba v průběhu Etsy OAuth procesu."""


def load_env_file(path: Path) -> None:
    """Načte jednoduchý .env soubor; existující systémové proměnné nepřepisuje."""
    if not path.is_file():
        return

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise EtsyOAuthError(f"Nelze přečíst konfigurační soubor {path}: {exc}") from exc

    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            print(f"Varování: ignoruji neplatný řádek {line_number} v .env.")
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue

        # Odstraní pouze párové vnější uvozovky. Hodnoty s # uvnitř uvozovek
        # zůstanou nedotčené.
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].rstrip()

        os.environ.setdefault(key, value)


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise EtsyOAuthError(
            f"Chybí konfigurace {name}. Doplň ji do souboru .env vedle skriptu."
        )
    return value


def generate_pkce() -> tuple[str, str]:
    """Vrátí PKCE code_verifier a jeho S256 challenge."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


def make_html_page(title: str, message: str) -> bytes:
    safe_title = html.escape(title)
    safe_message = html.escape(message)
    page = f"""<!doctype html>
<html lang="cs">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{safe_title}</title>
</head>
<body>
  <h1>{safe_title}</h1>
  <p>{safe_message}</p>
  <p>Můžeš zavřít toto okno a vrátit se do terminálu.</p>
</body>
</html>"""
    return page.encode("utf-8")


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """Přijme jediné OAuth přesměrování od Etsy."""

    # Výsledek callbacku sdílí handler přes instanci HTTP serveru.
    server: "CallbackHTTPServer"

    def log_message(self, _format: str, *_args: Any) -> None:
        # V URL může být autorizační kód. Nezapisujeme proto požadavky do logu.
        return

    def _send_page(self, status: int, title: str, message: str) -> None:
        body = make_html_page(title, message)
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - název vyžaduje BaseHTTPRequestHandler
        parsed = urllib.parse.urlsplit(self.path)
        if parsed.path != "/oauth/redirect":
            self._send_page(404, "Nenalezeno", "Tato adresa není OAuth callback.")
            return

        if self.server.callback_result is not None:
            self._send_page(409, "Autorizace již byla přijata", "Vrať se do terminálu.")
            return

        params = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
        code = params.get("code", [""])[0].strip()
        state = params.get("state", [""])[0].strip()
        error = params.get("error", [""])[0].strip()
        error_description = params.get("error_description", [""])[0].strip()

        if error:
            self.server.callback_result = {
                "error": error,
                "error_description": error_description,
                "state": state,
            }
            self._send_page(
                200,
                "Autorizace nebyla dokončena",
                error_description or f"Etsy vrátilo chybu: {error}",
            )
            return

        if not code:
            self.server.callback_result = {
                "error": "missing_code",
                "error_description": "V odpovědi Etsy chybí autorizační kód.",
                "state": state,
            }
            self._send_page(400, "Chyba autorizace", "V odpovědi Etsy chybí autorizační kód.")
            return

        self.server.callback_result = {"code": code, "state": state}
        self._send_page(200, "Autorizace přijata", "Etsy autorizace byla přijata.")


class CallbackHTTPServer(HTTPServer):
    def __init__(self, server_address: tuple[str, int]):
        super().__init__(server_address, OAuthCallbackHandler)
        self.callback_result: dict[str, str] | None = None
        self.timeout = 1.0


def wait_for_callback(server: CallbackHTTPServer, timeout_seconds: int) -> dict[str, str]:
    """Čeká omezenou dobu na callback, průběžně obsluhuje HTTP požadavky."""
    deadline = time.monotonic() + timeout_seconds
    while server.callback_result is None:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise EtsyOAuthError(
                f"Časový limit {timeout_seconds} sekund pro Etsy callback vypršel."
            )
        server.timeout = min(1.0, remaining)
        server.handle_request()

    return server.callback_result


def response_json(response: requests.Response, operation: str) -> dict[str, Any]:
    try:
        data = response.json()
    except ValueError as exc:
        excerpt = response.text[:500].replace("\n", " ")
        raise EtsyOAuthError(
            f"Etsy při operaci '{operation}' vrátilo neplatnou JSON odpověď "
            f"(HTTP {response.status_code}): {excerpt}"
        ) from exc

    if not isinstance(data, dict):
        raise EtsyOAuthError(f"Etsy při operaci '{operation}' vrátilo neočekávaný formát odpovědi.")
    return data


def describe_api_error(response: requests.Response) -> str:
    """Vrátí stručnou chybu bez vypisování hlaviček nebo tokenů."""
    try:
        payload = response.json()
        if isinstance(payload, dict):
            message = payload.get("error") or payload.get("error_description") or payload.get("message")
            if message:
                return str(message)[:700]
    except ValueError:
        pass
    return response.text[:700].replace("\n", " ") or response.reason


def exchange_code_for_tokens(
    api_key: str,
    redirect_uri: str,
    code: str,
    verifier: str,
) -> dict[str, Any]:
    """Vymění jednorázový autorizační kód za OAuth tokeny."""
    payload = {
        "grant_type": "authorization_code",
        "client_id": api_key,
        "redirect_uri": redirect_uri,
        "code": code,
        "code_verifier": verifier,
    }

    try:
        response = requests.post(TOKEN_URL, data=payload, timeout=HTTP_TIMEOUT)
    except requests.RequestException as exc:
        raise EtsyOAuthError(f"Nepodařilo se spojit s Etsy při výměně tokenu: {exc}") from exc

    if not response.ok:
        raise EtsyOAuthError(
            f"Etsy odmítlo výměnu autorizačního kódu (HTTP {response.status_code}): "
            f"{describe_api_error(response)}"
        )

    tokens = response_json(response, "výměna autorizačního kódu")
    access_token = tokens.get("access_token")
    refresh_token = tokens.get("refresh_token")
    if not isinstance(access_token, str) or not access_token:
        raise EtsyOAuthError("Etsy odpovědělo úspěšně, ale neposlalo access_token.")
    if not isinstance(refresh_token, str) or not refresh_token:
        raise EtsyOAuthError("Etsy odpovědělo bez refresh_token; tokeny nebyly uloženy.")
    token_type = tokens.get("token_type") or "Bearer"
    if not isinstance(token_type, str) or token_type.lower() != "bearer":
        raise EtsyOAuthError("Etsy vrátilo neočekávaný typ tokenu.")

    user_id, separator, _token_part = access_token.partition(".")
    if not separator or not user_id.isdigit():
        raise EtsyOAuthError(
            "Access token má neočekávaný formát. Očekávám číselné user_id následované tečkou."
        )

    return tokens


def save_tokens(tokens: dict[str, Any], user_id: str, scopes: str) -> None:
    expires_in = tokens.get("expires_in")
    try:
        expires_at = int(time.time()) + int(expires_in)
    except (TypeError, ValueError):
        expires_at = None

    saved_data = {
        "token_type": tokens.get("token_type") or "Bearer",
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
        "expires_in": expires_in,
        "expires_at_unix": expires_at,
        "expires_at_utc": (
            datetime.fromtimestamp(expires_at, tz=timezone.utc).isoformat()
            if expires_at is not None
            else None
        ),
        "scope": tokens.get("scope", scopes),
        "user_id": user_id,
    }

    temporary_file = TOKEN_FILE.with_suffix(TOKEN_FILE.suffix + ".tmp")
    try:
        temporary_file.write_text(
            json.dumps(saved_data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        if os.name == "posix":
            os.chmod(temporary_file, 0o600)
        temporary_file.replace(TOKEN_FILE)
        if os.name == "posix":
            os.chmod(TOKEN_FILE, 0o600)
    except OSError as exc:
        try:
            temporary_file.unlink(missing_ok=True)
        except OSError:
            pass
        raise EtsyOAuthError(f"Nepodařilo se bezpečně uložit tokeny do {TOKEN_FILE}: {exc}") from exc


def fetch_shop_id(api_key: str, shared_secret: str, user_id: str, access_token: str) -> int | None:
    """Vyhledá obchod vlastníka. Endpoint vyžaduje x-api-key i Bearer token (scope shops_r)."""
    url = SHOP_URL_TEMPLATE.format(user_id=user_id)
    headers = {
        "x-api-key": f"{api_key}:{shared_secret}",
        "Authorization": f"Bearer {access_token}",
    }

    try:
        response = requests.get(url, headers=headers, timeout=HTTP_TIMEOUT)
    except requests.RequestException as exc:
        print(f"Varování: tokeny jsou uloženy, ale SHOP_ID se nepodařilo ověřit: {exc}")
        return None

    if not response.ok:
        print(
            "Varování: tokeny jsou uloženy, ale Etsy nevrátilo SHOP_ID "
            f"(HTTP {response.status_code}): {describe_api_error(response)}"
        )
        return None

    try:
        shop_data = response.json()
    except ValueError:
        print("Varování: tokeny jsou uloženy, ale odpověď s obchodem není platný JSON.")
        return None

    if not isinstance(shop_data, dict):
        print("Varování: tokeny jsou uloženy, ale Etsy vrátilo neočekávaný formát obchodu.")
        return None

    shop_id = shop_data.get("shop_id")
    if shop_id is None and isinstance(shop_data.get("results"), list) and shop_data["results"]:
        first = shop_data["results"][0]
        shop_id = first.get("shop_id") if isinstance(first, dict) else None
    if isinstance(shop_id, int) and shop_id > 0:
        return shop_id
    if isinstance(shop_id, str) and shop_id.isdigit() and int(shop_id) > 0:
        return int(shop_id)

    print("Varování: Etsy vrátilo odpověď bez platného shop_id.")
    return None


def authorize(log=print) -> dict[str, Any]:
    """Provede celou OAuth autorizaci (otevře prohlížeč, čeká na callback, uloží tokeny).

    Importovatelná funkce pro GUI i CLI. Průběh hlásí přes `log`.
    Returns:
        {"user_id": str, "shop_id": int | None}
    Raises:
        EtsyOAuthError při jakékoli chybě autorizace.
    """
    load_env_file(ENV_FILE)

    api_key = required_env("ETSY_API_KEY")
    shared_secret = required_env("ETSY_SHARED_SECRET")
    redirect_uri = os.getenv("ETSY_REDIRECT_URI", DEFAULT_REDIRECT_URI).strip()
    scopes = os.getenv("ETSY_SCOPES", DEFAULT_SCOPES).strip()

    if not scopes:
        raise EtsyOAuthError("ETSY_SCOPES nesmí být prázdné.")
    if not redirect_uri:
        raise EtsyOAuthError("ETSY_REDIRECT_URI nesmí být prázdné.")

    parsed_redirect = urllib.parse.urlsplit(redirect_uri)
    if parsed_redirect.scheme != "http" or parsed_redirect.hostname not in ("localhost", "127.0.0.1"):
        raise EtsyOAuthError(
            "Tento skript očekává lokální HTTP callback na localhost nebo 127.0.0.1. "
            "Pro vzdálený HTTPS callback je potřeba jiný server."
        )
    if parsed_redirect.path != "/oauth/redirect" or parsed_redirect.query or parsed_redirect.fragment:
        raise EtsyOAuthError(
            "ETSY_REDIRECT_URI musí končit přesně cestou /oauth/redirect bez query a fragmentu."
        )

    port = parsed_redirect.port or 80
    bind_host = parsed_redirect.hostname

    verifier, challenge = generate_pkce()
    state = secrets.token_urlsafe(32)
    params = {
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": scopes,
        "client_id": api_key,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    auth_url = AUTHORIZE_URL + "?" + urllib.parse.urlencode(params)

    try:
        server = CallbackHTTPServer((bind_host, port))
    except OSError as exc:
        raise EtsyOAuthError(
            f"Nelze spustit lokální callback server na {bind_host}:{port}. "
            "Zkontroluj, zda port nepoužívá jiný program."
        ) from exc

    try:
        log("Otevírám přihlášení k Etsy v prohlížeči…")
        log(f"Callback server běží na: {redirect_uri}")
        opened = webbrowser.open(auth_url, new=2)
        if not opened:
            log("Prohlížeč se nepodařilo otevřít automaticky. Zkopíruj tuto adresu:\n")
            log(auth_url)

        result = wait_for_callback(server, CALLBACK_TIMEOUT_SECONDS)
    finally:
        server.server_close()

    if result.get("state") != state:
        raise EtsyOAuthError("Nesouhlasí bezpečnostní parametr state. Callback byl odmítnut.")
    if result.get("error"):
        detail = result.get("error_description") or result["error"]
        raise EtsyOAuthError(f"Uživatel nebo Etsy nedokončili autorizaci: {detail}")

    code = result.get("code", "")
    if not code:
        raise EtsyOAuthError("Callback neobsahuje autorizační kód.")

    tokens = exchange_code_for_tokens(api_key, redirect_uri, code, verifier)
    access_token = tokens["access_token"]
    user_id = access_token.partition(".")[0]

    # Tokeny uložíme dříve než provedeme nepovinné dohledání obchodu.
    save_tokens(tokens, user_id, scopes)

    log("\n=== AUTORIZACE DOKONČENA ===")
    log(f"Etsy user_id: {user_id}")
    log(f"Tokeny bezpečně uloženy do: {TOKEN_FILE}")
    log("Přístupový ani obnovovací token se z bezpečnostních důvodů nevypisuje.")

    shop_id = fetch_shop_id(api_key, shared_secret, user_id, access_token)
    if shop_id is not None:
        log(f"Etsy shop_id: {shop_id}")
        log("SHOP_ID můžeš použít ve své další aplikaci.")

    return {"user_id": user_id, "shop_id": shop_id}


def main() -> int:
    authorize(print)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except EtsyOAuthError as exc:
        print(f"\nCHYBA: {exc}", file=sys.stderr)
        raise SystemExit(1)
    except KeyboardInterrupt:
        print("\nPřerušeno uživatelem.", file=sys.stderr)
        raise SystemExit(130)
