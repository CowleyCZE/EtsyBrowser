# EtsyBrowser - TODO List

**Poslední aktualizace:** 19. listopadu 2026 (fix(P1): ceny + SEO tagy bundlů + SKU registr, commit 869bf8c4)
**Dokument pročištěn:** dokončené úkoly se při aktualizaci odstraňují (historie zůstává ve starších commitech).

---

## P0 - KRITICKÉ (Okamžitá oprava) #nové-chyby

### Bezpečnost
- [x] **Únik API klíče v kódu** - KOMPLETNĚ HOTOVO (commit c1f6e97 + 1601b4a, historie vyčištěna git-filter-repo, force push proveden) #nová-chyba
  - `automation/super_robot.py` a `automation/debug_pollinations.py`: Pollinations API klíč `sk_SbG7...` odstraněn ze všech skriptů.
  - Vytvořen lokální `.env` dle vzoru `.env.example`.
  - Git historie byla kompletně přepsána nástrojem `git-filter-repo`, klíč byl nahrazen `***REMOVED***` a nová historie byla se souhlasem uživatele nahrána na GitHub (`git push --force origin main`).
  - Ověřeno čerstvým klonem z GitHubu – klíč se již v historii ani v kódu nevyskytuje.
  - ⚠️ Doporučení: uživatel provede v UI Pollinations revokaci původního tokenu.
- [x] **config.json s přihlašovacími údaji je commitovaný** - HOTOVO (email/password přesunuty do .env; přidán config.example.json a .env.example) #nová-chyba
  - `config.json` obsahuje pole `email`/`password` a skutečnou URL obchodu a je v gitu. Jakmile se do něj vyplní heslo, unikne.
  - Řešení: přihlašovací údaje přesunout do `.env` (`.gitignore` už má `.env*`), v `config.json` nechat jen non-secret nastavení (delays, headless, csv_file) a přidat `config.example.json`.

### Chyby v kódu
- [x] **Login "uspěje" i když selhal** - HOTOVO (login() nyní detekuje 2FA/captchu a viditelný login formulář, vrací False) #nová-chyba
  - `src/uploader.py` `login()`: při neúspěchu se jen zaloguje warning a vrátí se `True` ("continuing anyway"). Bulk upload pak jede neautentizovaný a každý produkt zbytečně "selže".
  - Řešení: verifikovat úspěch proti reálnému stavu (přítomnost elementu manage stránky / absence login formuláře), při selhání vrátit `False` a ukončit běh s jasnou chybou. Navíc se nekontroluje přesměrování na 2FA/captcha.
- [x] **Nevalidní CSS selektor `:contains()`** - HOTOVO (odstraněny z DEFAULT_SELECTORS, publish/resi XPath fallback) #nová-chyba
  - `src/uploader.py` `DEFAULT_SELECTORS`: `publish_button` a `save_draft_button` používají `'button:contains("Publish")'` / `'button:contains("Save as draft")'`. `:contains` není platný CSS selektor, Selenium vyhodí `InvalidSelectorException`, takže tyto fallbacky nikdy nemohou fungovat.
  - Řešení: použít XPath (`//button[contains(., "Publish")]`), ideálně se selektory zaznamenanými Selector Recorderem.
- [x] **Description vkládaná přes f-string do `innerHTML`** - HOTOVO (bezpečné argumenty místo f-stringu) #nová-chyba
  - `src/uploader.py` `upload_single_product()`: `execute_script(f"arguments[0].innerHTML = '{description}';")`. Popis s apostrofem (v češtině běžný) rozbije JS, zároveň je to vektor skript injection.
  - Řešení: `self.driver.execute_script("arguments[0].innerHTML = arguments[1];", desc_editor, description)`.
- [x] **Nevalidní enumy pro Etsy v3 API** - HOTOVO (commit 1601b4a) #nová-chyba
  - Vytvořen centrální modul `src/etsy_enums.py` se všemi oficiálními enumy Etsy OpenAPI v3 (`WhoMade`, `WhenMade`, `ListingType`, `ListingState`, `AI_DISCLOSURE_TEXT`).
  - `automation/super_robot.py`: opraveno `when_made: "2020_2026"`, `who_made: "i_did"`, přidán `type: "download"`.
  - `src/fill_csv.py`: opraveno `DEFAULT_VALUES["who_made"] = "i_did"` (místo neplatného "AI_GENERATED"), synchronizováno s enumem. Dle Etsy zásad se AI obsah deklaruje jako "i_did" + disclosure v textu popisu listingu.

---

## P1 - DŮLEŽITÉ (Vysoká priorita) #nové-chyby

### Regrese odhalené při verifikaci činnosti CLI agenta (b37282b)
- [x] **ETSY_ROOT NameError v super_robot.py** - OPRAVENO (commit 7e3df94) #nová-chyba
  - Commit 1601b4a přidal `ETSY_BROWSE_ROOT = ETSY_ROOT`, ale `ETSY_ROOT` nikde nebyl definovaný → skript padal na NameError už při importu.
  - Řešení: `ETSY_ROOT = os.environ.get("ETSY_BROWSE_ROOT", ...)` (default ~/Pictures/Etsy).
- [x] **os.startfile v run_mockup_test_mode není na Linuxu** - HOTOVO (commit caaa64c0, helper _open_file_crossplatform Win/mac/Linux) #nová-chyba
  - `os.startfile(output_path)` je Windows-only funkce, na mac/Linux vyhodí AttributeError → test mockupu padá až po vygenerování.
  - Řešení: platform-agnostic otevření souboru (webbrowser.open, subprocess "open"/"xdg-open").

### Chyby v logice
- [x] **Rate limit `max_products_per_hour` se nikdy nepoužije** - HOTOVO (commit 6cc00d74, sliding-window limiter dle configu s logováním) #nová-chyba
  - `run_bulk_upload()` má jen pevnou pauzu 30 s každých 10 produktů. Nastavení `max_products_per_hour: 50` z `config.json` se nikde nečte.
  - Řešení: skutečný sliding-window limiter podle configu, logovat kolik produktů zbývá v aktuálním okně.
- [x] **Detekce úspěchu uploadu je nevěrohodná** - HOTOVO (commit 6cc00d74; chybějící title input => FAIL; žádný publish ani draft => FAIL; self.last_result = published/saved_as_draft) #nová-chyba
  - `upload_single_product()` vrací `True`, i když se nevyplnil title (prázdný selektor), nenahrají obrázky ani neprobehne publish ani save-draft. Statistika `success/failed` je tak zkreslená.
  - Řešení: rozlišit výsledky (published / saved_as_draft / failed_with_reason) a po publish ověřit, že listing opravdu vznikl (redirect na listing URL nebo API check).
- [x] **Chybí validace existence obrázků na disku** - HOTOVO (commit 6cc00d74, os.path.exists před send_keys) #nová-chyba
  - Před `file_input.send_keys(abs_path)` v `upload_image()` se nekontroluje `os.path.exists(abs_path)`. Neexistující cesta vede na kryptickou Selenium chybu.
- [x] **Defaultní ceny hardcodované na více místech a nekonzistentní** - HOTOVO (jednotný zdroj pravdy v config.json sekce `prices.single` / `prices.bundle`, čteno v super_robot.py, uploader.py i migrate_products.py; config.example.json doplněn)
- [x] **Tagy pro bundle se generují z `visual_style` místo z SEO tagů** - HOTOVO (generate_seo_text vrací tagy z LLM výstupu, parse_seo_tags ořezává na 13×20 znaků, fallback tagy při selhání)
- [x] **`generate_sku()` nechrání proti kolizím** - HOTOVO (perzistentní registr data/sku_registry.json per den+typ, sken Warehouse složek zůstává jako pojistka)

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
- P1 (Důležité): 13 (1 vyřešena, 1 nová regression)
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
