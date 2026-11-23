# EtsyBrowser - TODO List

**Poslední aktualizace:** 22. listopadu 2026
**Pravidlo:** 100% hotové úkoly se při aktualizaci odstraňují (historie zůstává v gitu). Částečně hotové zůstávají s poznámkou.
**Stav ověření:** automatické testy (`python -m pytest tests`) prošly, GUI startuje a jeho stránky vracejí 200, Chrome se spouští z Pythonu (headless test s example.com), stránka Mockupy byla ručně vyzkoušena. NEOVĚŘENO za běhu s reálnými daty: generování (Groq/Pollinations), publikace přes Etsy API, Selenium upload na Etsy, editor šablon, migrace a veškeré „napsáno“ níže.

---

## P0 - KRITICKÉ (Okamžitá akce)

### Bezpečnost
- [ ] **Zneplatnit uniklý Pollinations klíč `sk_SbG7...`** - ZBÝVÁ NA UŽIVATELI #nová-chyba
  - Klíč byl odstraněn z kódu i z historie gitu, ale musí být zrušen v Pollinations UI (revokace původního tokenu).
- [ ] **Rotace přihlašovacích údajů** - ZBÝVÁ NA UŽIVATELI #nová-chyba
  - Obsah kořenového `.env` (heslo k Etsy účtu, Groq a Pollinations klíč) i `oauth/.env` (shared secret) byl zobrazen v AI konverzaci. Změnit heslo k Etsy a vygenerovat nové API klíče.
  - Smazat složku `_to_delete/` (starý Next.js scaffold a duplicitní `oauth/env`). Ověřit `git status`.

---

## P1 - DŮLEŽITÉ (Vysoká priorita)

### Správnost publikace na Etsy
Pozn.: následující změny jsou napsané, ale NEOTESTOVANÉ proti živému Etsy API.

- [ ] **Ověřit publikaci na reálném draftu** - ČÁSTEČNĚ HOTOVO #nová-chyba
  - Hotovo: `taxonomy_id` z taxonomie (nebo `ETSY_TAXONOMY_ID`), tags jako řetězec, titulek ≤140, max 13 tagů ≤20 znaků, AI disclosure v popisu, ZIPy do `04_Delivery/`, `upload_listing_file`, `update_listing_state`, zveřejnění až po potvrzení, `etsy.listing_id` v `listing_data.json` brání duplicitám. Z GUI jde publikovat z detailu produktu (tlačítka „Nahrát jako draft“ a „Zveřejnit“).
  - Zbývá: spustit na jednom produktu, ověřit formát `tags` (řetězec vs. pole) a nalezené `taxonomy_id`, případně opravit.
- [x] **Etsy vrací 400 při nahrávání digitálního souboru (PDF s odkazem)** - OPRAVENO retry (ověřit) #nová-chyba
  - Příznaky (24. 11. 04:01, listing 4623552003): `{"error":"An error ocurred while uploading your file, please try again."}`, PDF se nehodilo na draft, obrázky ano. Endpoint pro soubory občas vrací 400 i pro platný požadavek (typicky krátce po vytvoření listingu); kód navíc dělal druhý pokus (ASCII název) jen při diakritice, tedy pro čistě ASCII názvy jen jeden pokus.
  - OPRAVENO v `automation/etsy_api.py`: `upload_listing_file` opakuje pokusy (3× s čekáním 5/20/60 s), při diakritice zkusí i ASCII název, posílá MIME typ podle přípony a po každé chybě ověří, zda soubor na listingu přesto není. Ověřit opakovaným nahráním PDF na draft;
- [x] **Limit Etsy 5 souborů × 20 MB vs. velikost tiskových souborů** - OPRAVENO (viz B-4), ověřit #nová-chyba
  - Bundle (5 artů × 5 velikostí JPEG q95) se do limitu nevejde; `build_delivery_zips` to detekuje a draft nevytvoří. Rozhodnout: PDF s odkazem ke stažení, nižší kvalita/menší sada velikostí pro doručení, nebo jiný způsob doručení.

---

## P2 - STŘEDNÍ PRIORITA

### Příprava na GUI (refaktory)
- [ ] **Oddělit logiku od příkazové řádky** - ČÁSTEČNĚ HOTOVO #nová-chyba
  - Hotovo: `run_generation_mode(theme, interactive)`, `run_solo_mode(interactive)` a publikační funkce se dají volat bez `input()`; vrací výsledek a hlásí průběh přes `src/progress.py`. GUI i CLI volají totéž.
  - Zbývá: `automate_folder_processing` a `browse_and_create_mockup` jsou dál čistě CLI; `run_list_mode` duplikuje sestavení bundlu (viz níže).
- [ ] **Odstranit vedlejší efekty při importu** - ČÁSTEČNĚ HOTOVO #nová-chyba
  - Hotovo: import už nevytváří složky (`ensure_dirs()`), `reload_config()` znovu načte `.env`, ceny, Groq a šablony (GUI ji volá před každou úlohou).
  - Zbývá: při importu se stále čte `.env`, `config.json` a `mockup_templates.json` (neškodné); sjednotit do třídy `Config`.
- [ ] **Nahradit `print` logováním přes `src/logger.py`** - ČÁSTEČNĚ HOTOVO #nová-chyba
  - Hotovo: fronta úloh zachytává `print`/stderr z vlákna úlohy do logu úlohy (`logs/jobs/<id>.log`), takže GUI log funguje i s `print`.
  - Zbývá: opravdu přejít na `logging` (úrovně, formát) a vyřešit denní rotaci (P3).
- [ ] **Fronta úloh na pozadí** - HOTOVO, ověřeno testy jednotek, v GUI neotestováno
  - `src/jobs.py` + `src/progress.py`: běh po jedné úloze, průběh v %, kooperativní zrušení, historie (`data/jobs_history.json`), log na úlohu. Po ověření v GUI bod odstranit.
- [ ] **Rozšířit `etsy_api.py` o metody pro GUI** - ČÁSTEČNĚ HOTOVO #nová-chyba
  - Hotovo: `upload_listing_file`, `update_listing_state`, `get_listing`, taxonomie. Zbývá: seznam listingů obchodu, smazání draftu.

### Chyby a úklid kódu
- [ ] **Zpracované obrázky se po SOLO nearchivují** - OPRAVENO (viz S-6), ověřit #nová-chyba
  - `run_solo_mode` nechává zdrojové obrázky v `_To_Edit`; druhé spuštění vytvoří duplicitní produkty. `archive_old_files` navíc přesouvá jen soubory v kořeni `_To_Edit`, ne podsložky `Batch_*`. Po úspěšném zpracování zdroj přesunout do `03_Archive/`.
- [ ] **`run_list_mode` duplikuje sestavení bundlu** - OPRAVENO: obě cesty volají `build_bundle(client, trend, prompts, progress)`, ověřit #nová-chyba
  - Kroky (SKU, složky, obrázky, tiskové soubory, mockupy, SEO, metadata) jsou zkopírované z `run_generation_mode`. Vytáhnout do jedné funkce `build_bundle(theme, style, prompts)`.
- [x] **Sjednotit konfiguraci promptů: prompts.json vs prompts2.json vs promptsvzor.json** #nová-chyba
  - Určit jednu aktivní verzi, zbytek přesunout do `data/archive/`; dvě README (`README.md`, `README_auto_etsy.md`) sloučit.
- [x] **`fill_csv.py` mapování je nevyužité a nekonzistentní** #nová-chyba
  - `ETSY_FIELDS` mapuje `shop_section -> shop_section_id`, ale `generate_etsy_csv` vypisuje sloupec `shop_section`. Mapování se nikde nepoužívá. Sloučit a uklidit.
- [x] **Závislosti: zastaralé pinování a kompletnost** #nová-chyba
  - `requirements.txt` pinuje `groq==0.4.2`; zkontrolovat, že obsahuje vše, co kód importuje, a jak se liší od `oauth/requirements.txt`. V `uploader.py` zůstal nepoužitý import `generate_etsy_csv`. Pro testy GUI přibyly `pytest` a `httpx`.
- [ ] **`automate_folder_processing` vypisuje předstíraný průběh menu** #nová-chyba
  - Funkce tiskne texty, jako by uživatel zadával volby ("AUTOMATICKá volba"). Zjednodušit na skutečný průběh se smysluplným logem.
- [ ] **Singles mají generický titulek a tagy** - OPRAVENO (viz S-5), ověřit #nová-chyba
  - `run_solo_mode` vždy používá "wall art, printable, digital download". Generovat SEO přes LLM i pro singly (po vyřešení bodu o titulcích v P1).

---

## P2 - GUI: FUNKCE (cíl: ovládat z jednoho místa vše, co aplikace umí)

Poznámka: GUI poběží lokálně na tvém počítači (`127.0.0.1`), klíče a hesla se do prohlížeče nikdy neposílají. Selenium upload otevírá reálné okno Chrome; 2FA/captchu musí uživatel vyřešit ručně.

Poznámka: vše níže označené „napsáno“ je NEOTESTOVANÉ. Nejdřív spustit (`bash start.sh`) a ověřit, zejména tlačítko „Připojit k Etsy“, uložení nastavení, běh jedné úlohy a náhled mockupu. Pak body odstranit.

- [ ] **GUI-0: Kostra aplikace** - NAPSÁNO, neotestováno. Zbývá sekce `README` s návodem ke spuštění.
- [ ] **GUI-1: Dashboard** - NAPSÁNO, neotestováno. Obsahuje poslední úlohy; chybí rychlá tlačítka.
- [ ] **GUI-2: Připojení k Etsy** - NAPSÁNO, neotestováno. Opraveno: tlačítko dřív nenašlo `ETSY_API_KEY` uložený v kořenovém `.env` (OAuth skript čte jen `oauth/.env`).
- [ ] **GUI-3: Nastavení** - NAPSÁNO, neotestováno. Chybí nastavení cest ke složkám (závisí na refaktoru `Config`).
- [ ] **GUI-4: Sklad produktů** - NAPSÁNO, neotestováno: seznam s náhledy, hledání, filtr stavu, úprava titulku, popisu, tagů a ceny. Chybí smazání a zobrazení tiskových souborů.
- [ ] **GUI-5: Generování Bundle (automatické)** - NAPSÁNO, neotestováno (stránka Generovat: vlastní téma nebo průzkum trhu, průběh, log, zrušení).
- [ ] **GUI-6: Generování ze seznamu a editor promptů** - ČÁSTEČNĚ: spuštění `data/prompts.json` z GUI je napsáno; chybí formulářový editor promptů.
- [ ] **GUI-7: SOLO zpracování** - NAPSÁNO, neotestováno: nahrání obrázků do fronty (výběr souborů), zpracování, archivace. Chybí přetažení myší a náhledy.
- [ ] **GUI-8: Mockupy** - OVĚŘENO uživatelem v prohlížeči (`gui/mockups.py`, stránka Mockupy): nahrání obrázku (nebo `TEST_ART_PATH` jako testovací obrázek), výběr šablony s miniaturami a stavem konfigurace, náhled vykreslený stejnou funkcí `render_mockup` jako při generování, stažení v plné velikosti. Zbývá: výběr obrázku z fronty nebo ze skladu produktů, uložení mockupu přímo k produktu. Test `test_mockup_preview_and_download` prošel (28/28 testů OK, GUI nastartovalo a `/` vrátilo 200); ruční zkouška proběhla bez chyby.
- [ ] **GUI-9: Editor šablon (kalibrace rohů)** - NAPSÁNO, neotestováno v prohlížeči (`/mockups/editor`): klikání 4 rohů (perspektiva) nebo 2 rohů (obdélník), přetahování bodů, výběr/založení kategorie, uložení do `mockup_templates.json`, smazání konfigurace. Validace pořadí rohů a hranic je v `gui/mockups.py` s testem `test_template_editor_saves_validates_and_removes` (nespuštěn). Zbývá: odstranit `data/mereni.html` a `run_config_server` v `super_robot.py` po ověření editoru.
- [ ] **GUI-10: Publikace na Etsy přes API** - ČÁSTEČNĚ: tlačítka „Nahrát jako draft“ a „Zveřejnit“ (s potvrzením poplatku) v detailu produktu, běží jako úlohy. Chybí kontrolní náhled před odesláním a zobrazení stavu přímo z Etsy.
- [ ] **GUI-11: Selenium dávkový upload a CSV** - NAPSÁNO, neotestováno (`/uploader`, `gui/csvtools.py`): editor `products.csv` (přidání, mazání, validace titulku/ceny/tagů, upozornění na chybějící obrázky, nezobrazené sloupce se zachovají), spuštění uploaderu jako úlohu (viditelné okno / headless, průběh po produktech, zrušení zavře prohlížeč, shrnutí v Úlohy). Při 2FA/captche ve viditelném okně uploader počká až 5 minut na ruční dokončení. Test `test_uploader_csv_editor_and_run` nespuštěn; skutečný upload na Etsy zatím nedoběhl: první pokus ze GUI selžel při startu Chrome (`Exec format error` u chromedriveru z webdriver-manageru), opraveno v `src/browser_utils.py` (Selenium Manager + oprava cesty), ověřit znovu. Login a start Chrome fungují. Chyba „Uh oh! page not found“: uploader otevíral neexistující `/listings/new`; opraveno na `/your/shops/<obchod>/tools/listings/create` (přepsatelné `new_listing_url` v `config.json`), neověřeno. Další krok: selektory formuláře jsou nalezeny (`selectors_found.json`, `selectors_report.md`) a zapracovány do nového `upload_single_product` (fotky, kategorie `inline-category-6844`, texty, štítky, radia, AI disclosure, digitální soubory ze sloupce `digital_files` v CSV, výchozí je uložení konceptu, `publish_listings: true` v `config.json` publikuje); OTESTOVÁNO 23. 11.: přihlášení, fotky, kategorie Digital Prints + typ Digital, texty, štítky, radia, uložení konceptu probehlo (1/1). Zbývá: ověřit koncept na Etsy, přidat sloupec `digital_files` do CSV (upload digitálních souborů zatím netestován), případně přepsat `src/selectors.json` (soubor je stále prázdný) a smazat `_upload_single_product_legacy` a `_login_legacy`. Zbývá: ovládání Selector Recorderu z GUI, generování CSV ze skladu produktů.
- [ ] **GUI-12: Archivace a migrace** - NAPSÁNO, neotestováno: archivace fronty je tlačítko na stránce Generovat; migrace starých produktů (`/migrate`, `automation/migrate_products.py`) s náhledem plánu (dry-run), potvrzením a během jako úloha. Migrace přiděluje SKU z perzistentního čítače (dřív vzniklo každé spuštění od 01), zapisuje do `automation/02_Warehouse`, původní složky nemění a evidence hotových je v `data/migrated_products.json`. CLI: `python automation/migrate_products.py --source CESTA [--apply]`. Testy `tests/test_migrate.py` a `test_migrate_page_and_run` nespuštěny (kód a testy prošly jen statickou kontrolou, bez nalezených chyb).
- [ ] **GUI-13: Logy a historie úloh** - ČÁSTEČNĚ HOTOVO: stránka Úlohy, detail s průběhem a logem, zrušení, stažení logu. Chybí filtr chyb a živé obnovování bez reloadu stránky.
- [ ] **GUI-14: Postupné nasazení** - doporučené pořadí: (1) kostra + dashboard + připojení k Etsy + nastavení, (2) sklad produktů + publikace, (3) generování a SOLO, (4) mockupy a editor šablon, (5) uploader, archivace, logy

---

## P3 - NÍZKÁ PRIORITA

- [ ] **Sjednotit jazyk kódové báze** - mix CZ/EN v log zprávách, docstringách a README. Zvolit jednu konvenci (např. CZ pro logy a UI, EN pro docstrings).
- [ ] **logger.py: nový log soubor na každý běh** - `setup_logger` vytváří soubor podle timestampu, každý modul tedy generuje vlastní soubor per run. Použít denní rotující handler.
- [ ] **`TEST_ART_PATH` v `super_robot.py`** - výchozí je Windows cesta; na Linuxu nastavit přes `.env` (GUI: Nastavení). `migrate_products.py` už má parametr `--source` a rozumný default.
- [ ] **dry-run mód pro uploader** (`--dry-run`) - projít CSV, validovat formát a obrázky bez publikování.
- [ ] **User-agent (OPRAVENO v `src/browser_utils.py`, neověřeno spuštěním; po reálném uploadu bod odstranit) nesedí s versí prohlížeče** - UA se sestavuje ze skutečné hlavní verze Chrome (`build_user_agent`). Dodatečně opraveno: `selenium_stealth.stealth()` bez parametru `user_agent` UA znovu přepisoval původním (Linux) UA, takže předchozí přepis nepůsobil; nyní se UA předává i do `stealth()`. Ověřit: `driver.execute_script('return navigator.userAgent')` musí vrátit Chrome/<skutečná verze> s Windows NT a `navigator.platform` = Win32.

---

## P4 - DLOUHODOBÉ

- [ ] **Přejít ze Selenium na oficiální Etsy API v3 všude** - `automation/etsy_api.py` umí draft, obrázky a automatickou obnovu tokenu. Selenium upload podléhá banům a změnám Etsy UI; udržovat jen jako fallback.
- [ ] **Testy a CI** - ČÁSTEČNĚ HOTOVO: `tests/test_seo.py` (parsování SEO, payload), `tests/test_jobs.py` (fronta úloh), `tests/test_gui_smoke.py` (stránky, ochrana localhostu, nahrávání; vyžaduje `httpx`). Zbývají unit testy pro `fill_csv.py`, `generate_sku`, obnovu tokenu (mock HTTP) a GitHub Actions pro lint a testy. Testy GUI zatím nikdy neběžely.
- [ ] **Vyplnit src/selectors.json reálnými selektory** - šablona je prázdná (všechny `primary: ""`), takže Selenium běží jen na `DEFAULT_SELECTORS`. Spustit Selector Recorder a commitnout výsledek.
- [ ] **Persistní evidence nasazených listingů** - SQLite/JSON log SKU -> listing_id, aby opakované běhy neduplikovaly produkty (základ pro stav ve skladu v GUI-4).
- [ ] **Jednoduché spuštění pro nováčka** - ČÁSTEČNĚ HOTOVO: `start.sh` existuje; zbývá krátký návod v README.

---

## STATISTIKA

- P0 (Kritické): 2
- P1 (Důležité): 2
- P2 (Střední): 12 (příprava a úklid) + 15 (GUI) = 27
- P3 (Nízké): 5
- P4 (Dlouhodobé): 5
- **Celkem otevřeno: 41**

---

## REVIZE 23. 11. 2026: „Nový Bundle (5 obrazů)“ a „Vlastní obrázky (SOLO → Single produkty)“

Zkontrolováno čtením kódu (`gui/tasks.py`, `automation/super_robot.py`, `gui/templates/generate.html`). Nic z toho nebylo spuštěno; opravy označené níže jako opravené je nutné ověřit (`python -m pytest tests` a ruční běh).

### Opravené chyby (ověřit)
- [ ] **B-1 Bundle nejde vygenerovat: `TypeError: Client.__init__() got an unexpected keyword argument 'proxies'`** (historie úloh 22. 11. 23:11). Příčina: `groq==0.4.2` je nekompatibilní s `httpx>=0.28`. OPRAVENO v `requirements.txt` (`groq>=0.18`), **je nutné spustit `pip install -U -r requirements.txt` ve `.venv`** a znovu vyzkoušet. Týká se i Generování ze seznamu (SEO texty).
- [ ] **B-2 Selhání se tvářilo jako „hotovo“.** `generate_bundle` vracel `False` a SOLO nevracelo nic, úloha tedy skončila jako úspěšná i bez jediného produktu. OPRAVENO v `gui/tasks.py` a `run_solo_mode` (vrací počet ok/failed, při 0 úspěších vyhodí chybu; výsledek úlohy ukazuje „Vytvořeno X, selhalo Y“). Ověřit, že `tests/test_gui_smoke.py` s tím počítá.
- [ ] **S-1 „Archivovat frontu“ nearchivovala podsložky `Batch_*`.** Fronta v GUI je ukazuje (`queue_files` používá `rglob`), ale `archive_old_files` brala jen soubory v kořeni, takže obrázky z generování ze seznamu zůstávaly a po dalším „Zpracovat“ vznikaly duplicitní produkty. OPRAVENO: prochází podsložky, používá `shutil.move` (`os.rename` selhává mezi disky) a maže prázdné `Batch_*`.
- [ ] **S-2 Diakritika v názvu souboru zničila název produktu.** `Mělník.png` → `Mlnk` (písmena s diakritikou zmizela úplně) a titulek „MontSaintMichel Wall Art…“ byl bez mezer. OPRAVENO: `_ascii_slug` (Mělník → Melnik) pro složky a `_title_from_filename` (rozdělí na slova). Stejně se čistí téma bundlu; složka je omezena na 40 znaků.
- [ ] **S-3 Rozpracovaný produkt zůstal ve skladu při chybě.** OPRAVENO: složka se při chybě smaže (SKU se přesto spotřebuje, aby zůstalo unikátní).
- [ ] **S-4 Fotky z telefonu byly otočené** (EXIF orientace se ignorovala). OPRAVENO: `ImageOps.exif_transpose`. Přidáno také varování při rozlišení pod 1500 px na kratší straně.
- [ ] **B-3 Bundle s jiným počtem promptů než 5.** LLM občas vrátí jiný počet nebo jiný typ položek, bundle by měl méně obrazů s titulkem „Set of 5“. OPRAVENO: `get_prompts` vždy vrací přesně 5 (chybějící doplní variantami). `market_research` navíc ověřuje klíče odpovědi, jinak použije záložní téma.

### Neopravené chyby a rizika (potřebují rozhodnutí)
- [ ] **B-4 (P0) Bundle se nedá nahrát na Etsy přes API.** OPRAVENO, varianta A (ověřit): bundle se doručuje jako jediné PDF s klikacím odkazem (`write_link_pdf`, `build_external_delivery`). Na stránce produktu: „Připravit ZIP ke stažení“ (`prepare_download_archive` → `04_Delivery/<SKU>_Full_Print_Files.zip`), pole „Odkaz ke stažení“ (ukládá se do `listing_data.json` → `delivery.download_url`). Bez odkazu se draft bundlu nevytvoří. Nahrání ZIPu na Drive/Dropbox zůstává ruční. Původní popis: Jeden single dává 5 tiskových souborů a 3 ZIPy (~55 MB). Bundle má 5 obrazů × 5 velikostí = 25 souborů, tedy zhruba 15 ZIPů, ale Etsy dovoluje max. 5 souborů po 20 MB. `build_delivery_zips` to správně zablokuje a nahrávání skončí chybou. Návrhy: (a) tiskové soubory bundlu dát na externí úložiště a do ZIPu uložit jen PDF s odkazem, (b) snížit kvalitu JPEG (95 → 85) a velikosti pro bundle, (c) rozdělit bundle na dva až tři listingy. Doporučeno (a). Odhad velikosti vychází z logu singlu, skutečné velikosti ověřit.
- [ ] **B-5 (P1) Tisky ořezávané ze čtverce.** OPRAVENO, varianta A (ověřit): Pollinations generuje 3:4 (1536×2048), tiskové sady podle orientace zdroje (`print_sizes_for`, čtvercové 12×12/16×16/20×20 pro čtvercový zdroj), prompty žádají okraje kolem motivu. Původní popis: Pollinations generuje 1024×1024 a tisk se ořezává na střed na 16:9, 20:11, 24:13 (~44 % výšky se ztratí) a na 15:20, 16:20 (~25 % šířky). Motiv se může useknout. Návrh: generovat v poměru 3:4 a přidat čtvercové velikosti (např. 12×12, 16×16), případně motiv dogenerovat (outpainting), nebo v GUI dát náhled ořezů.
- [ ] **B-6 (P1) Zvětšení z 1024 px na 7200 px (7×).** OPRAVENO, varianta A (ověřit): výchozí rozlišení 1536×2048 (`config.json` → `image.width/height` přepíše), zvětšení je tedy zhruba 3×. Nutné ověřit, že plán Pollinations 2048 px zvládne (při chybě 4xx zkus nižší hodnotu v `config.json`). Původní popis: Výsledek je měkký i s UnsharpMask. Návrh: vyšší výchozí rozlišení z Pollinations (např. 2048) nebo AI upscaler (Real-ESRGAN) před tiskem; upozornění v popisu produktu na reálné rozlišení.
- [ ] **B-7 (P1) Mockupy bundlu ukazují vždy jen jeden obraz.** OPRAVENO, varianta A (ověřit): `01_Main_Thumbnail` je přehledová koláž všech obrazů (`create_bundle_overview`), ostatní mockupy používají obrazy cyklicky a šablony bez opakování (`make_mockups`). Původní popis: `random.choice(images)` pro každý z 8 mockupů, přitom soubory se jmenují „02_Bundle_Overview“ a „07_Size_Comparison“. Návrh: přehledový mockup/koláž všech 5 obrazů (hlavní prodejní obrázek bundlu).
- [ ] **B-8 (P2) Pollinations bez opakování.** OPRAVENO (ověřit): 3 pokusy se zpožděním 0/8/20 s; bundle s méně obrazy se označí `incomplete` + varování v GUI, názvy `Art_A…` jsou souvislé. Původní popis: `generate_image` při chybě 429/5xx nebo timeoutu hned vrací `None` a obraz se přeskočí, bundle pak může mít méně obrazů a mezery v názvech (`Art_A`, `Art_C`). Návrh: 3 pokusy s rostoucím zpožděním a při neúspěchu celý bundle označit jako neúplný.
- [ ] **B-9 (P2) `create_mockup` selže potichu.** OPRAVENO (ověřit): `create_mockup` hlásí kategorii bez šablon, použije náhradní, `make_mockups` vrací počet selhání, ty se zapíšou do `warnings` v `listing_data.json` a zobrazí na stránce produktu. Původní popis: Když kategorie šablon neexistuje (názvy jsou česky s diakritikou, např. „Obyčejný byt“) nebo chybí soubor šablony, mockup nevznikne a nikdo o tom neví; Etsy pak dostane méně než 8 obrázků. Návrh: vracet výsledek, hlásit varování a použít náhradní kategorii. Šablonu také vybírat bez opakování, ať se 8 obrázků neopakuje.
- [ ] **B-10 (P2) Fallback SEO pro bundle** má jen 3 obecné tagy a prázdný popis. Návrh: při selhání Groq zopakovat dotaz, doplnit tagy z tématu a produkt označit jako „neúplné SEO“ (blokovat publikaci).
- [ ] **S-5 (P1) SOLO nemá žádné SEO.** OPRAVENO, varianta A (ověřit): pole „téma / klíčová slova“ u každého obrázku ve frontě (`automation/00_Input_Queue/topics.json`), Groq z něj + názvu souboru vytvoří titulek, popis a 13 tagů (`generate_solo_seo`); bez Groq klíče nebo při chybě se použijí obecné texty a produkt má `seo_generated: false` (upozornění v detailu). Původní popis: Titulek je jen název souboru + „Wall Art - Digital Download Printable“, tagy jsou 3 obecné a popis prázdný (přes API se použije jen „Digital printable wall art. Instant download.“). Návrh: pole „téma/klíčová slova“ pro každý obrázek v GUI a generování titulku, popisu a 13 tagů přes Groq (případně vision modelem z náhledu obrázku).
- [ ] **S-6 (P1) Zpracované obrázky zůstávají ve frontě** OPRAVENO, varianta A (ověřit): po úspěšném zpracování se zdroj přesune do `03_Archive/RRRR_MM` (`archive_queue_file`), při chybě zůstává ve frontě; `archive_old_files` používá stejnou funkci. Původní popis: a při dalším „Zpracovat frontu“ se zpracují znovu (nový SKU, duplicitní produkt). GUI to jen popisuje v textu. Návrh: po úspěšném zpracování obrázek automaticky přesunout do `03_Archive/RRRR_MM` (nebo si pamatovat zpracované soubory podle hashe) a v GUI ukazovat stav u každého souboru.
- [ ] **S-7 (P2) Poměr stran se neřeší.** Portrétní zdroj se ořezává na široké formáty a naopak. Návrh: náhled ořezů v GUI, výběr vyráběných velikostí a varování, když by se ořezalo víc než 30 % obrazu.
- [ ] **S-8 (P2) Průběh jen po souborech.** Jeden single trvá desítky sekund (5 velikostí + 8 mockupů). Návrh: průběh po krocích (tisky, mockupy, metadata) a volitelně vícevláknové zpracování.
- [ ] **S-9 (P2) Nahrávání souborů v GUI.** `save_upload` kontroluje typ a limit 80 MB, ale ověření obrázku proběhne až po uložení a bez náhledu. Návrh: miniatury ve frontě, mazání jednotlivých souborů z fronty, nahrávání přetažením (navazuje na GUI-7).
- [ ] **X-1 (P2) Měna.** OPRAVENO (ověřit): metadata, migrace, uložení produktu v GUI i popisek ceny používají EUR. Původní popis: `create_listing_data` zapisuje `"currency": "USD"`, ale obchod počítá v EUR (Etsy ukazuje „EUR 3.99“). Cena se přes API posílá v měně obchodu, takže 5,90 / 9,90 jsou eura. Sjednotit popisek a ceny v `config.json`.
- [ ] **X-2 (P3) `TEST_ART_PATH`** má v `super_robot.py` výchozí Windows cestu (`c:\Users\cowle\...`), na Linuxu nefunguje. Nastavit v `.env` nebo použít obrázek ze složky `images/`.

### Co ověřit po opravách
1. `pip install -U -r requirements.txt`, pak `python -m pytest tests`.
2. V GUI → Generovat: „Nový Bundle“ s vlastním tématem (úloha nesmí skončit chybou `proxies`, vznikne 5 obrazů).
3. Nahrát obrázek s diakritikou v názvu (např. `Mělník.png`) → složka `SP-…-S_Melnik`, titulek „Melnik Wall Art - …“.
4. „Archivovat frontu“ po generování ze seznamu (podsložky `Batch_*` musí zmizet z fronty).
5. `python -m pytest tests` včetně nového `tests/test_delivery_and_seo.py` (doručení přes odkaz, mockupy, bundle, SOLO SEO a archivace).
6. Bundle: Generovat → Sklad produktů → detail: „Připravit ZIP“, nahrát na Drive/Dropbox, vložit odkaz, „Nahrát jako draft“. Na Etsy má být jedno PDF s klikacím odkazem a 8 obrázků, první je koláž.
7. SOLO: nahrát obrázek, vyplnit téma, „Zpracovat frontu“: titulek/popis/13 tagů odpovídají tématu a obrázek zmizí z fronty (je v `automation/03_Archive/`).

---

## POKYNY PRO AI

1. **Priorita:** P0 > P1 > P2 > P3 > P4
2. **Odškrtávání:** Změňte `- [ ]` na `- [x]` pro hotové úkoly
3. **Úklid:** Dokončené úkoly při aktualizaci dokumentu odstraňte (historie zůstává v gitu)
4. **Přidávání:** Nové úkoly přidejte na konec příslušné sekce s `#nová-chyba`
5. **Formát:** Udržujte stejný formát pro konzistenci
6. **Postup:** Před pokračováním ověřte, že naposledy označený bod skutečně funguje (spuštění/test), teprve pak pokračujte dalším bodem
