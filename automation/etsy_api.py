"""Klient pro Etsy Open API v3 s automatickým obnovováním OAuth tokenu.

Tokeny se načítají ze souboru oauth/etsy_tokens.json (vytváří ho
oauth/get_etsy_token.py). Access token platí cca 1 hodinu, klient ho proto
před každým voláním zkontroluje a v případě potřeby obnoví pomocí refresh
tokenu. Etsy při obnově vrací NOVÝ refresh token, proto se po každé obnově
celý soubor s tokeny bezpečně přepíše.
"""

import json
import mimetypes
import os
import time
import unicodedata
from pathlib import Path
from typing import Any, Dict, Optional

import requests

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
OAUTH_DIR = PROJECT_ROOT / "oauth"
DEFAULT_TOKEN_FILE = OAUTH_DIR / "etsy_tokens.json"

TOKEN_URL = "https://api.etsy.com/v3/public/oauth/token"
HTTP_TIMEOUT = (5, 30)          # (připojení, čtení) v sekundách
UPLOAD_TIMEOUT = (5, 120)       # nahrávání obrázků je pomalejší
REFRESH_MARGIN_SECONDS = 120    # obnovit token, pokud vyprší dřív než za 2 min
MAX_RETRIES = 3                 # opakování při 429 / 5xx / síťové chybě
FILE_UPLOAD_TIMEOUT = (5, 300)  # digitální soubory až 20 MB
MAX_LISTING_FILE_BYTES = 20 * 1024 * 1024  # limit Etsy na jeden digitální soubor
FILE_UPLOAD_ATTEMPTS = 3                    # opakování při 400 (Etsy endpoint pro soubory je občas nespolehlivý)
FILE_UPLOAD_RETRY_DELAYS = (5, 20, 60)      # čekání mezi pokusy (s)


class EtsyAuthError(RuntimeError):
    """Token chybí, je neplatný nebo ho nelze obnovit."""


def _read_env_file(path: Path) -> Dict[str, str]:
    """Jednoduché načtení KEY=VALUE ze souboru .env (bez zápisu do os.environ)."""
    values: Dict[str, str] = {}
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                value = value[1:-1]
            values[key.strip()] = value
    except OSError:
        pass
    return values


class EtsyClient:
    """Klient pro komunikaci s Etsy API v3.

    Zpětně kompatibilní: EtsyClient(api_key, shop_id, access_token) stále funguje
    (token se pak neobnovuje). Doporučené je EtsyClient.from_env(), které
    používá oauth/etsy_tokens.json a automatické obnovování.
    """

    BASE_URL = "https://openapi.etsy.com/v3"

    def __init__(
        self,
        api_key: str,
        shop_id: str,
        access_token: Optional[str] = None,
        shared_secret: Optional[str] = None,
        token_file: Optional[os.PathLike] = None,
    ):
        self.api_key = api_key
        self.shop_id = shop_id
        self.shared_secret = shared_secret
        self.token_file = Path(token_file) if token_file else DEFAULT_TOKEN_FILE
        self._tokens: Dict[str, Any] = {}
        self._taxonomy_cache: Optional[list] = None

        self._load_tokens_from_file()
        if not self._tokens.get("access_token") and access_token:
            # Ruční token bez refresh_tokenu - platí jen do vypršení
            self._tokens = {"access_token": access_token}

    # ------------------------------------------------------------------
    # Vytvoření z prostředí
    # ------------------------------------------------------------------
    @classmethod
    def from_env(cls) -> "EtsyClient":
        """Vytvoří klienta z .env / proměnných prostředí a tokenů z oauth/etsy_tokens.json."""
        oauth_env = _read_env_file(OAUTH_DIR / ".env")

        api_key = os.getenv("ETSY_API_KEY") or oauth_env.get("ETSY_API_KEY", "")
        shared_secret = os.getenv("ETSY_SHARED_SECRET") or oauth_env.get("ETSY_SHARED_SECRET")
        shop_id = os.getenv("ETSY_SHOP_ID", "")
        token_file = os.getenv("ETSY_TOKEN_FILE")
        access_token = os.getenv("ETSY_ACCESS_TOKEN")

        if not api_key:
            raise EtsyAuthError("Chybí ETSY_API_KEY (.env nebo oauth/.env).")
        if not shop_id:
            raise EtsyAuthError("Chybí ETSY_SHOP_ID v .env (zjistí ho oauth/get_etsy_token.py).")

        return cls(api_key, shop_id, access_token, shared_secret, token_file)

    # ------------------------------------------------------------------
    # Správa tokenů
    # ------------------------------------------------------------------
    def _load_tokens_from_file(self) -> None:
        try:
            data = json.loads(self.token_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if isinstance(data, dict) and data.get("access_token"):
            self._tokens = data

    def _save_tokens(self) -> None:
        """Atomicky přepíše soubor s tokeny (práva 600)."""
        tmp = self.token_file.with_suffix(self.token_file.suffix + ".tmp")
        try:
            tmp.write_text(json.dumps(self._tokens, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            if os.name == "posix":
                os.chmod(tmp, 0o600)
            tmp.replace(self.token_file)
        except OSError as exc:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            raise EtsyAuthError(f"Nelze uložit obnovené tokeny do {self.token_file}: {exc}") from exc

    def _token_is_fresh(self) -> bool:
        expires_at = self._tokens.get("expires_at_unix")
        if not isinstance(expires_at, (int, float)):
            return True  # neznámá expirace (ruční token) - zkusíme a při 401 obnovíme
        return time.time() < expires_at - REFRESH_MARGIN_SECONDS

    def refresh_access_token(self) -> None:
        """Vymění refresh token za nový access + refresh token a uloží je."""
        # Jiný proces mohl token mezitím obnovit - zkontroluj soubor
        before = self._tokens.get("refresh_token")
        self._load_tokens_from_file()
        if self._tokens.get("refresh_token") != before and self._token_is_fresh():
            return

        refresh_token = self._tokens.get("refresh_token")
        if not refresh_token:
            raise EtsyAuthError(
                "Chybí refresh_token. Spusť znovu: python3 oauth/get_etsy_token.py"
            )

        try:
            response = requests.post(
                TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "client_id": self.api_key,
                    "refresh_token": refresh_token,
                },
                timeout=HTTP_TIMEOUT,
            )
        except requests.RequestException as exc:
            raise EtsyAuthError(f"Nepodařilo se spojit s Etsy při obnově tokenu: {exc}") from exc

        if not response.ok:
            raise EtsyAuthError(
                f"Etsy odmítlo obnovu tokenu (HTTP {response.status_code}): {response.text[:300]}. "
                "Pokud refresh token vypršel (90 dní), spusť: python3 oauth/get_etsy_token.py"
            )

        try:
            new = response.json()
            access = new["access_token"]
            new_refresh = new.get("refresh_token") or refresh_token
        except (ValueError, KeyError) as exc:
            raise EtsyAuthError("Etsy vrátilo neplatnou odpověď při obnově tokenu.") from exc

        expires_in = new.get("expires_in")
        try:
            expires_at = int(time.time()) + int(expires_in)
        except (TypeError, ValueError):
            expires_at = None

        self._tokens.update(
            {
                "access_token": access,
                "refresh_token": new_refresh,
                "expires_in": expires_in,
                "expires_at_unix": expires_at,
                "token_type": new.get("token_type") or "Bearer",
            }
        )
        self._save_tokens()
        print("🔑 Etsy access token byl automaticky obnoven.")

    def _ensure_token(self) -> None:
        if not self._tokens.get("access_token"):
            raise EtsyAuthError("Žádný Etsy token. Spusť: python3 oauth/get_etsy_token.py")
        if not self._token_is_fresh():
            self.refresh_access_token()

    @property
    def access_token(self) -> str:
        return self._tokens.get("access_token", "")

    def _headers(self) -> Dict[str, str]:
        key = f"{self.api_key}:{self.shared_secret}" if self.shared_secret else self.api_key
        return {"x-api-key": key, "Authorization": f"Bearer {self.access_token}"}

    # ------------------------------------------------------------------
    # HTTP vrstva (timeout, retry, obnova tokenu při 401)
    # ------------------------------------------------------------------
    def _request(self, method: str, url: str, timeout=HTTP_TIMEOUT, **kwargs) -> requests.Response:
        self._ensure_token()
        refreshed_on_401 = False
        last_exc: Optional[Exception] = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = requests.request(
                    method, url, headers=self._headers(), timeout=timeout, **kwargs
                )
            except requests.RequestException as exc:
                last_exc = exc
                if attempt == MAX_RETRIES:
                    raise
                time.sleep(2 ** attempt)
                continue

            if response.status_code == 401 and not refreshed_on_401 and self._tokens.get("refresh_token"):
                refreshed_on_401 = True
                # Vynutit obnovu i když lokálně token vypadá platně
                self._tokens["expires_at_unix"] = 0
                self.refresh_access_token()
                continue

            if response.status_code == 429 or response.status_code >= 500:
                if attempt < MAX_RETRIES:
                    retry_after = response.headers.get("Retry-After", "")
                    delay = int(retry_after) if retry_after.isdigit() else 2 ** attempt
                    time.sleep(min(delay, 60))
                    continue

            return response

        if last_exc:
            raise last_exc
        raise RuntimeError("Etsy request selhal bez odpovědi.")

    # ------------------------------------------------------------------
    # API metody
    # ------------------------------------------------------------------
    def get_shop_info(self) -> Optional[Dict[Any, Any]]:
        """Získá základní informace o obchodě pro ověření spojení."""
        url = f"{self.BASE_URL}/application/shops/{self.shop_id}"
        try:
            response = self._request("GET", url)
            if response.status_code == 200:
                return response.json()
            print(f"❌ Chyba při získávání informací o obchodě: {response.status_code} - {response.text}")
            return None
        except (EtsyAuthError, requests.RequestException) as e:
            print(f"❌ Chyba při komunikaci s Etsy: {e}")
            return None

    def create_listing(self, data: Dict[str, Any]) -> Optional[str]:
        """Vytvoří nový listing jako draft.

        Args:
            data: Slovník s daty (quantity, title, description, price, who_made, when_made, taxonomy_id, tags)
        Returns:
            Listing ID při úspěchu, jinak None.
        """
        url = f"{self.BASE_URL}/application/shops/{self.shop_id}/listings"
        try:
            response = self._request("POST", url, data=data)
            if response.status_code == 201:
                listing_id = response.json().get("listing_id")
                print(f"✅ Listing vytvořen! ID: {listing_id}")
                return listing_id
            print(f"❌ Chyba při vytváření listingu: {response.status_code} - {response.text}")
            return None
        except (EtsyAuthError, requests.RequestException) as e:
            print(f"❌ Chyba při vytváření listingu: {e}")
            return None

    def upload_listing_image(self, listing_id: str, image_path: str, rank: int = 1) -> bool:
        """Nahraje obrázek k existujícímu listingu.

        Args:
            listing_id: ID listingu
            image_path: Cesta k souboru s obrázkem
            rank: Pořadí obrázku (1 je hlavní)
        """
        url = f"{self.BASE_URL}/application/shops/{self.shop_id}/listings/{listing_id}/images"
        try:
            # Obsah načteme do paměti, aby šel požadavek bezpečně opakovat (retry)
            with open(image_path, "rb") as img_file:
                content = img_file.read()
        except OSError as e:
            print(f"❌ Nelze přečíst obrázek {image_path}: {e}")
            return False

        try:
            response = self._request(
                "POST",
                url,
                timeout=UPLOAD_TIMEOUT,
                files={"image": (os.path.basename(image_path), content)},
                data={"rank": rank},
            )
            if response.status_code == 201:
                print(f"✅ Obrázek {os.path.basename(image_path)} nahrán.")
                return True
            print(f"❌ Chyba při nahrávání obrázku: {response.status_code} - {response.text}")
            return False
        except (EtsyAuthError, requests.RequestException) as e:
            print(f"❌ Chyba při nahrávání obrázku: {e}")
            return False

    def upload_listing_file(self, listing_id: str, file_path: str, rank: int = 1) -> bool:
        """Nahraje digitální soubor (to, co kupující dostane ke stažení) k listingu.

        Etsy limity: max. 5 souborů na listing, každý max. 20 MB.
        Endpoint pro soubory občas vrátí 400 "An error ocurred while
        uploading your file, please try again." i pro zcela platný požadavek
        (typicky krátce po vytvoření listingu), proto se pokusy opakují s
        časovým odstupem a po každé chybě se ověří, zda soubor na listingu
        náhodou přesto není.
        """
        try:
            size = os.path.getsize(file_path)
        except OSError as e:
            print(f"❌ Nelze přečíst soubor {file_path}: {e}")
            return False
        if size > MAX_LISTING_FILE_BYTES:
            print(f"❌ Soubor {os.path.basename(file_path)} má {size / 1024 / 1024:.1f} MB (limit Etsy je 20 MB).")
            return False

        url = f"{self.BASE_URL}/application/shops/{self.shop_id}/listings/{listing_id}/files"
        name = os.path.basename(file_path)
        existing = self.get_listing_files(listing_id)
        before = len(existing) if existing is not None else None
        if existing and any(str(f.get("filename", "")) == name for f in existing):
            print(f"ℹ️ Digitální soubor {name} už na listingu je, přeskočen.")
            return True
        try:
            with open(file_path, "rb") as fh:
                content = fh.read()
        except OSError as e:
            print(f"❌ Nelze přečíst soubor {file_path}: {e}")
            return False

        mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
        # První pokus s původním názvem; při diakritice v názvu i pokus s ASCII názvem.
        ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii") or "file.zip"
        upload_names = [name] if ascii_name == name else [name, ascii_name]

        attempt_no = 0
        for upload_name in upload_names:
            for _ in range(FILE_UPLOAD_ATTEMPTS):
                if attempt_no > 0:
                    wait = FILE_UPLOAD_RETRY_DELAYS[min(attempt_no - 1, len(FILE_UPLOAD_RETRY_DELAYS) - 1)]
                    print(f"⏳ Opakuji nahrávání digitálního souboru (pokus {attempt_no + 1}) za {wait} s...")
                    time.sleep(wait)
                attempt_no += 1
                try:
                    response = self._request(
                        "POST",
                        url,
                        timeout=FILE_UPLOAD_TIMEOUT,
                        files={"file": (upload_name, content, mime)},
                        data={"name": upload_name, "rank": rank},
                    )
                except (EtsyAuthError, requests.RequestException) as e:
                    print(f"❌ Chyba při nahrávání souboru: {e}")
                    response = None
                if response is not None and response.status_code == 201:
                    print(f"✅ Digitální soubor {upload_name} nahrán.")
                    return True
                if response is not None:
                    print(f"⚠️ Etsy vrátilo {response.status_code} při nahrávání souboru: {response.text[:200]}")
                # Etsy API někdy vrátí chybu, ale soubor přesto uloží - ověřit přímo na listingu
                time.sleep(3)
                after = self.get_listing_files(listing_id)
                if after is not None and (
                    any(str(f.get("filename", "")) in (name, upload_name) for f in after)
                    or (before is not None and len(after) > before)
                ):
                    print(f"✅ Digitální soubor {name} je na listingu (ověřeno), chybu Etsy ignoruji.")
                    return True
        print(f"❌ Digitální soubor {name} se nepodařilo nahrát.")
        return False

    def get_listing_files(self, listing_id: str) -> Optional[list]:
        """Vrátí seznam digitálních souborů listingu (None při chybě)."""
        url = f"{self.BASE_URL}/application/shops/{self.shop_id}/listings/{listing_id}/files"
        try:
            response = self._request("GET", url)
            if response.status_code == 200:
                return response.json().get("results", [])
        except (EtsyAuthError, requests.RequestException, ValueError):
            pass
        return None

    def update_listing_state(self, listing_id: str, state: str) -> bool:
        """Změní stav listingu (např. 'active' pro zveřejnění, 'draft' pro skrytí)."""
        url = f"{self.BASE_URL}/application/shops/{self.shop_id}/listings/{listing_id}"
        try:
            response = self._request("PATCH", url, data={"state": state})
            if response.status_code == 200:
                print(f"✅ Listing {listing_id} má nyní stav '{state}'.")
                return True
            print(f"❌ Chyba při změně stavu listingu: {response.status_code} - {response.text}")
            return False
        except (EtsyAuthError, requests.RequestException) as e:
            print(f"❌ Chyba při změně stavu listingu: {e}")
            return False

    def get_listing(self, listing_id: str) -> Optional[Dict[Any, Any]]:
        """Vrátí detail listingu (stav, soubory, obrázky) nebo None."""
        url = f"{self.BASE_URL}/application/listings/{listing_id}"
        try:
            response = self._request("GET", url, params={"includes": "Images"})
            if response.status_code == 200:
                return response.json()
            print(f"❌ Chyba při načtení listingu: {response.status_code} - {response.text}")
            return None
        except (EtsyAuthError, requests.RequestException) as e:
            print(f"❌ Chyba při načtení listingu: {e}")
            return None

    def get_taxonomy_nodes(self) -> list:
        """Vrátí strom kategorií prodejce (seller taxonomy); výsledek se cachuje."""
        if self._taxonomy_cache is not None:
            return self._taxonomy_cache
        url = f"{self.BASE_URL}/application/seller-taxonomy/nodes"
        try:
            response = self._request("GET", url)
            if response.status_code == 200:
                self._taxonomy_cache = response.json().get("results", [])
                return self._taxonomy_cache
            print(f"❌ Chyba při načtení taxonomie: {response.status_code} - {response.text}")
        except (EtsyAuthError, requests.RequestException) as e:
            print(f"❌ Chyba při načtení taxonomie: {e}")
        return []

    def find_taxonomy_id(self, path: list) -> Optional[int]:
        """Najde ID kategorie podle cesty názvů, např. ['Art & Collectibles', 'Prints', 'Digital Prints']."""
        nodes = self.get_taxonomy_nodes()
        node = None
        for name in path:
            node = next((n for n in nodes if str(n.get("name", "")).lower() == name.lower()), None)
            if node is None:
                return None
            nodes = node.get("children") or []
        return node.get("id") if node else None


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")

    try:
        client = EtsyClient.from_env()
    except EtsyAuthError as e:
        print(f"❌ {e}")
        raise SystemExit(1)

    print("Provádím test spojení s Etsy...")
    info = client.get_shop_info()
    if info:
        print(f"Spojení úspěšné! Obchod: {info.get('shop_name')}")
    else:
        print("Spojení selhalo.")
        raise SystemExit(1)
