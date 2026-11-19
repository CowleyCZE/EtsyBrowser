# EtsyBrowser - TODO List

**Poslední aktualizace:** 19. listopadu 2026 (fix(P0): P0.1-P0.5 hotovo, commity c1f6e97 a b3c414e)
**Dokument pročištěn:** dokončené úkoly se při aktualizaci odstraňují (historie zůstává ve starších commitech).

---

## P0 - KRITICKÉ (Okamžitá oprava) #nové-chyby

### Bezpečnost
- [x] **Únik API klíče v kódu** - KÓDOVÁ ČÁST HOTOVA (commit c1f6e97) #nová-chyba
  - `automation/super_robot.py`, řádek ~76: Pollinations API klíč `sk_SbG7...` je natvrdo zapsaný ve zdrojovém kódu veřejného repozitáře.
  - Nález: `api_key = "***REMOVED***"` ve funkci `generate_image()`.
  - Řešení: (1) OKAMŽITĚ revoke klíče u Pollinations - ⚠️ MUSÍ UDĚLAT UŽIVATEL mansuálně, (2) číst klíč z `os.getenv("POLLINATIONS_API_KEY")` přes `load_dotenv()` - ✅ HOTOVO (commit c1f6e97, 19.11.2026), (3) pročistit git historii (např. `git filter-repo` nebo BFG) - ⚠️ VYŽADUJE UŽIVATELE (git push --force i počáteční local replace).
- [x] **config.json s přihlašovacími údaji je commitovaný** - HOTOVO (email/password přesunuty do .env; přidán config.example.json a .env.example) #nová-chyba
  - `config.json` obsahuje pole `email`/`password` a skutečnou URL obchodu a je v gitu. Jakmile se do něj vyplní heslo, unikne.
  - Řešení: přihlašovací údaje přesunout do `.env` (`.gitignore` už má `.env*`), v `config.json` nechat jen non-secret nastavení (delays, headless, csv_file) a přidat `config.example.json`.

### Chyby v kódu
- [x] **Login "uspěje" i když selhal** - HOTOVO (login() nyní detekuje 2FA/captchu a viditelný login formulář, vrací False) #nová-chyba
  - `src/uploader.py` `login()`: při neúspěchu se jen zaloguje warning a vrátí se `True` ("continuing anyway"). Bulk upload pak jede neautentizovaný a každý produkt zbytečně "selže".
  - Řešení: verifikovat úspěch proti reálnému stavu (přítomnost elementu manage st
ánky / absence login formuláře), při selhání vrátit `False` a ukončit běh s jasnou chybou. Navíc se nekontroluje přesměrování na 2FA/captcha.
- [x] **Nevalidní CSS selektor `:contains()`** - HOTOVO (odstraněny z DEFAULT_SELECTORS, publish/resi XPath fallback) #nová-chyba
  - `src/uploader.py` `DEFAULT_SELECTORS`: `publish_button` a `save_draft_button` používají `'button:contains("Publish")'` / `'button:contains("Save as draft")'`. `:contains` není platný CSS selektor, Selenium vyhodí `InvalidSelectorException`, takže tyto fallbacky nikdy nemohou fungovat.
  - Řešení: použít XPath (`//button[contains(., "Publish")]`), ideálně se selektory zaznamenanými Selector Recorderem.
- [x] **Description vkládaná přes f-string do `innerHTML`** - HOTOVO (bezpečné argumenty místo f-stringu) #nová-chyba
  - `src/uploader.py` `upload_single_product()`: `execute_script(f"arguments[0].innerHTML = '{description}';")`. Popis s apostrofem (v češtině běžný) rozbije JS, zároveň je to vektor skript injection.
  - Řešení: `self.driver.execute_script("arguments[0].innerHTML = arguments[1];", desc_editor, description)`.
- [ ] **Nevalidní enumy pro Etsy v3 API** #nová-chyba
  - `automation/super_robot.py` `publish_to_etsy()`: `when_made: "2020_2024"` - ověřit aktuální platné hodnoty enumu v dokumentaci Etsy Open API v3. Zároveň `fill_csv.py` má `DEFAULT_VALUES["who_made"] = "AI_GENERATED"` - taková hodnota v Etsy CSV neexistuje (AI obsah se deklaruje jinak).
  - Řešení: ověřit hodnoty v dokumentaci Etsy API v3 a sjednotit obě upload cesty do jednoho společného modulu.

---

## P1 - DŮLEŽITÉ (Vysoká priorita) #nové-chyby

### Chyby v logice
- [ ] **Rate limit `max_products_per_hour` se nikdy nepoužije** #nová-chyba
  - `run_bulk_upload()` má jen pevnou pauzu 30 s každých 10 produktů. Nastavení `max_products_per_hour: 50` z `config.json` se nikde nečte.
  - Řešení: skutečný sliding-window limiter podle configu, logovat kolik produktů zbývá v aktuálním okně.
- [ ] **Detekce úspěchu uploadu je nevěrohodná** #nová-chyba
  - `upload_single_product()` vrací `True`, i když se nevyplnil title (prázdný selektor), nenahrají obrázky ani neprobehne publish ani save-draft. Statistika `success/failed` je tak zkreslená.
  - Řešení: rozlišit výsledky (published / saved_as_draft / failed_with_reason) a po publish ověřit, že listing opravdu vznikl (redirect na listing URL nebo API check).
- [ ] **Chybí validace existence obrázků na disku** #nová-chyba
  - Před `file_input.send_keys(abs_path)` v `upload_image()` se nekontroluje `os.path.exists(abs_path)`. Neexistující cesta vede na kryptickou Selenium chybu.
- [ ] **Defaultní ceny hardcodované na více místech a nekonzistentní** #nová-chyba
  - `uploader.py`: `"9.99"`; `super_robot.py`: `5.90` (single) / `9.90` (bundle); `migrate_products.py` totéž copy-paste. Řešení: jednotný zdroj pravdy (config / listing_data).
- [ ] **Tagy pro bundle se generují z `visual_style` místo z SEO tagů** #nová-chyba
  - `run_generation_mode()`: `tags=trend.get('visual_style', '').split(', ')[:13]` - tagy jsou větný popis stylu, nikoliv krátké Etsy tagy (max 20 znaků na tag). Tagy z `generate_seo_text()` se do `listing_data.json` vůbec nedostanou.
- [ ] **`generate_sku()` nechrání proti kolizím** #nová-chyba
  - Číslování se odvodí z obsahu `SINGLES_DIR`/`BUNDLES_DIR`; po archivaci (03_Archive) se kolize mohou opakovat a dva paralelní běhy si vygenerují stejné SKU.
  - Řešení: perzistentní counter (JSON v datovém adresáři) nebo timestamp se sekundami.

### Chyby v kódu
- [ ] **Vyčistit bare `except:` v celém projektu** #nová-chyba
  - `uploader.py`, `browser_utils.py`, `super_robot.py`, `migrate_products.py`: desítky `except: pass` / `except: continue`, které polykají i `KeyboardInterrupt` a maskují skutečné příčiny chyb.
  - Řešení: chytat konkrétní výjimky (`NoSuchElementException`, `TimeoutException`, `WebDriverException`) a logovat je.
- [ ] **`wait_for_element` vrací `WebDriverWait`, ne element; a chybí čekání před fill formulářů** #nová-chyba
  - `browser_utils.wait_for_element()` by měl vracet WebElement. Formulářová pole se navíc všude plní přes okamžité `find_element`, takže po redirectu dochází ke race conditions.
  - Řešení: vrátit `driver.find_element(...)` po úspěšném waitu a použít čekání ve všech formulářových krocích.
- [ ] **Křehký import v super_robot.py** #nová-chyba
  - `from etsy_api import EtsyClient` funguje jen při spuštění z `automation/` složky. Řešení: přidat `SCRIPT_DIR` do `sys.path` nebo použít package-relative import.
- [ ] **`run_generation_mode` spadne na `Groq(api_key=None)`** #nová-chyba
  - Fallback v `market_research` chyby zachytává, ale samotné `Groq(api_key=GROQ_API_KEY)` v `run_generation_mode` vyhodí výjimku dřív, než se k fallbacku dostane. Ošetřit chybějící `GROQ_API_KEY` hned na startu s jasnou chybou.
- [ ] **`chr(64 + int(art_num))` v migrate_products.py padne nad Art_26 a při nečíselném sufixu** #nová-chyba
  - Validovat vstup a přeskočit s varováním místo pádu.

---

## P2 - STŘEDNÍ PRIORITA #nové-chyby

### Volba nástrojů a duplicity
- [ ] **Next.js/React/Bun/Tailwind scaffold je mrtvá váha** #nová-chyba
  - `src/app/` obsahuje jen prázdný template (`page.tsx` 94 B), žádná funkcionalita. Zároveň projekt má 2 README (`README.md`, `README_auto_etsy.md`) a 3 soubory promptů (`prompts.json`, `prompts2.json`, `promptsvzor.json`) bez jasného rozdělení rolí.
  - Rozhodnutí: bv䏠(a) odstranit Next.js scaffold (package.json, bun.lock, next.config.ts, src/app, eslint/tailwind configy) dokud nebude reálně potřeba, nebo (b) naplánovat reálné dashboard UI, který scaffold využije. Současný stav mate přispěvatele i AI agenty.
- [ ] **Duplicitní logika mockupů** #nová-chyba
  - Tři aliasy na stejný adresář (`MOCKUP_DIR`, `MOCKUP_TEMPLATES_DIR`, `TEMPLATES_MOCKUP_DIR`) a dvě téměř identické funkce `create_mockup` a `create_mockup_from_templates_dir` (~60 řádků copy-paste). Refaktorovat do jedné funkce s jedním zdrojem konfigurace.
- [ ] **Dva duplicitní hlavní nabídky v super_robot.py** #nová-chyba
  - `main()` se nikdy nevolá (`__main__` používá vlastní while-loop) a texty nabídek jsou už v divergenci. Odstranit mrtvý `main()` nebo unifikovat.
- [ ] **Sjednotit konfiguraci promptů: prompts.json vs prompts2.json vs promptsvzor.json** #nová-chyba
  - Etalovat jednu verzi jako aktivní, zbytek přesunout do `data/archive/`.

### Chyby v kódu
- [ ] **Fixní `seed: 42` u generování obrázků** #nová-chyba
  - `generate_image()`: všechny generace se stejným promptem dostanou identický obrázek, komentář v kódu tvrdí opak. Randomizovat seed (nebo ho dát do konfigurace pro reprodukovatelnost).
- [ ] **`fill_csv.py` mapování je nevyužité a nekonzistentní** #nová-chyba
  - `ETSY_FIELDS` mapuje `shop_section -> shop_section_id`, ale `generate_etsy_csv` vypisuje sloupec `shop_section`. Mapování se navíc nikde nepoužívá. Sloučit a uklidit.
- [ ] **Nepoužívané importy a zastaralé pinutí závislostí** #nová-chyba
  - `uploader.py` importuje `pandas`, `human_like_mouse_move`, `wait_for_element`, `upload_file` bez použití. `requirements.txt` pinuje `groq==0.4.2`. Projít importy a aktualizovat verze.
- [ ] **Chybí timeout a retry u Groq / Etsy API volání** #nová-chyba
  - `etsy_api.py` `requests.get/post` ani Groq volání nemají timeout ani retry, jedno zamrznutí zastaví celý běh.

---

## P3 - NÍZKÁ PRIORITA

- [ ] **Sjednotit jazyk kódové báze** - mix CZ/EN v log zprávách, docstringách a README. Zvolit jednu konvenci (např. CZ pro logy a UI, EN pro docstrings).
- [ ] **logger.py: nový log soubor na každý běh** - `setup_logger` vytváří soubor podle timestampu, každý modul tedy generuje vlastní soubor per run. Pro dlouhé běhy lepší daily rotating handler.
- [ ] **migrate_products.py hardcodovaná Windows cesta** `c:\Users\cowle\Pictures\Etsy` - přidat parametr CLI (`--root`) a rozumný default.
- [ ] **dry-run mód pro uploader** (`--dry-run`) - projít CSV, validovat formát a obrázky bez publikování.
- [ ] **User-agent nesedí s versí prohlížeče** - UA tvrdí Chrome/120, ale ChromeDriver odpovídá reálně nainstalovanému Chromu; mismatch je detekovatelný. Postavit UA podle skutečné hlavní verze Chrome.

---

## P4 - DLOUHODOBÉ

- [ ] **Přejít ze Selenium na oficiální Etsy API v3 všude** - už existuje `automation/etsy_api.py` s `create_listing` a `upload_listing_image`. Selenium upload podléhá banům a změnám Etsy UI; API cesta je stabilnější. Selenium udržovat jen jako fallback/diagnostický nástroj.
- [ ] **Testy a CI** - projekt nemá jediný test. Začít unit testy pro `fill_csv.py`, `generate_sku`, mapování tagů (pytest + GitHub Actions workflow pro lint a testy).
- [ ] **Vyplnit src/selectors.json reálnými selektory** - repozitář obsahuje prázdnou šablonu (všechny `primary: ""`), takže produkce běží jen na DEFAULT_SELECTORS, u kterých jsou publish/save selektory už teď neplatné. Spustit Selector Recorder a commitnout výsledek.
- [ ] **Frontend dashboard** (jen pokud scaffold zůstane): rozhraní pro správu products.csv, frontu generování a status uploadů.
- [ ] **Persistní evidence nasazených listingů** - SQLite/JSON log SKU -> listing_id, aby opakované běhy neduplikovaly produkty.

---

## STATISTIKA

- P0 (Kritické): 6
- P1 (Důležité): 11
- P2 (Střední): 7
- P3 (Nízké): 5
- P4 (Dlouhodobé): 5
- **Celkem otevřeno: 34**

---

## POKYNY PRO AI

1. **Priorita:** P0 > P1 > P2 > P3 > P4
2. **Odškrtávání:** Změňte `- [ ]` na `- [x]` pro hotové úkoly
3. **Úklid:** Dokončené úkoly při aktualizaci dokumentu odstraňte (historie zůstává v gitu)
4. **Přidávání:** Nové úkoly přidejte na konec příslušné sekce s `#nová-chyba`
5. **Formát:** Udržujte stejný formát pro konzistenci

---

**Soubor vytvořen:** 19. listopadu 2026 (naplněno hloubkovou analýzou repozitáře)


---

**ZÁZNAM Z BĚHU 19.11.2026 (P0.1)**
- ✅ Kódová část hotova: `automation/super_robot.py` nyní čte `POLLINATIONS_API_KEY` z env, klíč nikde v kódu není.
- ⚠️ ZBÝVÁ NA UŽIVATELI: (1) revoke uniklého klíče `sk_SbG7...` v Pollinations UI, (2) vytvořit `.env` s novým klíčem, (3) pročistit git historii (klič zůstává ve starších commitech!).
- Nový blob: `automation/super_robot.py` commit c1f6e97.
