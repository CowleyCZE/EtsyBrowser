# EtsyBrowser - Manuál

Kompletní návod k použití automatizačního nástroje pro hromadné nahrávání produktů na Etsy.

## Obsah

1. [Selector Recorder](#selector-recorder)
2. [Uploader](#uploader)
3. [CSV formát](#csv-formát)
4. [Pokročilé použití](#pokročilé-použití)
5. [Řešení problémů](#řešení-problémů)

---

## Selector Recorder

Nástroj pro automatické zaznamenávání CSS selektorů z Etsy formulářů. Umožňuje dynamickou konfiguraci bez nutnosti ruční úpravy kódu.

### Proč používat Selector Recorder?

Etsy pravidelně mění své webové rozhraní. Selektory v kódu mohou přestat fungovat. Selector Recorder vám umožní:

- Automaticky najít elementy na stránce
- Interaktivně kliknout na elementy a zaznamenat jejich selektory
- Uložit konfiguraci pro budoucí použití

### Režimy

#### Automatický režim

Automaticky prohledá stránku a pokusí se najít běžné elementy Etsy.

```bash
python src/selector_recorder.py \
  --url "https://www.etsy.com/your/shops/NAZEV/listings/new" \
  --mode auto
```

**Co hledá:**

| Typ elementu | Popis |
|--------------|-------|
| `login_email` | Pole pro email |
| `login_password` | Pole pro heslo |
| `title_input` | Název produktu |
| `description_editor` | Editor popisu |
| `price_input` | Cena |
| `quantity_input` | Množství |
| `image_upload` | Upload obrázků |
| `tags_input` | Štítky |
| `digital_checkbox` | Digitální produkt |
| `publish_button` | Tlačítko publikovat |

#### Interaktivní režim

Manuální zaznamenávání selektorů klikáním na elementy.

```bash
python src/selector_recorder.py \
  --url "https://www.etsy.com/your/shops/NAZEV/listings/new" \
  --mode interactive
```

**Postup:**

1. Spustí se prohlížeč s Etsy
2. Přihlaste se manuálně (pokud je třeba)
3. Klikněte na element, který chcete zaznamenat
4. V konzoli zadejte typ elementu
5. Opakujte pro další elementy
6. Stiskněte `s` pro uložení

**Klávesové zkratky:**

| Klávesa | Akce |
|---------|------|
| `1` | title_input |
| `2` | description_editor |
| `3` | price_input |
| `4` | quantity_input |
| `5` | image_upload |
| `6` | tags_input |
| `7` | digital_checkbox |
| `8` | category_button |
| `9` | publish_button |
| `0` | save_draft_button |
| `l` | Zobrazit dostupné typy |
| `d` | Smazat poslední |
| `s` | Uložit a ukončit |
| `q` | Ukončit bez uložení |
| `h` | Nápověda |

#### Kombinovaný režim

Spustí automatický režim, pak umožní ruční doladění.

```bash
python src/selector_recorder.py \
  --url "https://www.etsy.com/your/shops/NAZEV/listings/new" \
  --mode both
```

### Pokročilé možnosti

```bash
# S existujícím profilem prohlížeče
python src/selector_recorder.py \
  --url "URL" \
  --user-data-dir "C:/Users/Uzivatel/AppData/Local/Google/Chrome/User Data"

# Výstup do jiného souboru
python src/selector_recorder.py \
  --url "URL" \
  --output "custom_selectors.json"

# Headless režim
python src/selector_recorder.py \
  --url "URL" \
  --headless
```

---

## Uploader

Hlavní skript pro hromadné nahrávání produktů na Etsy.

### Základní použití

#### Hromadný režim (všechny produkty z CSV)

```bash
python src/uploader.py --mode bulk
```

#### Jeden produkt

```bash
python src/uploader.py --mode single --product-id 1
```

#### S vlastním CSV

```bash
python src/uploader.py --mode bulk --csv moje_produkty.csv
```

#### S vlastními selektory

```bash
python src/uploader.py \
  --mode bulk \
  --selectors "src/selectors.json"
```

### Parametry příkazové řádky

| Parametr | Popis | Výchozí |
|----------|-------|---------|
| `--mode` | Režim: `single` nebo `bulk` | `bulk` |
| `--csv` | Cesta k CSV souboru | `products.csv` |
| `--config` | Konfigurační soubor | `config.json` |
| `--selectors` | Selektory soubor | `src/selectors.json` |
| `--product-id` | ID produktu (pro single mode) | - |
| `--headless` | Spustit bez GUI | Ne |

### Průběh nahrávání

1. **Přihlášení** - Otevře Etsy a přihlásí se
2. **Načtení CSV** - Načte produkty ze souboru
3. **Cyklus produktů:**
   - Navigace na stránku nového inzerátu
   - Vyplnění údajů (název, popis, cena, množství)
   - Nahrání obrázků
   - Nastavení štítků
   - Publikování
   - Zpoždění (proti detekci botů)
4. **Výsledky** - Souhrn úspěšných/neúspěšných

### Výstup

```
==================================================
UPLOAD RESULTS
==================================================
Total products: 10
Successful: 8
Failed: 2
Time elapsed: 1542.3s
==================================================
```

---

## CSV formát

### Struktura souboru

```csv
title,description,price,tags,category_path,image_paths,shop_section
```

### Popis sloupců

| Sloupec | Povinný | Popis | Příklad |
|---------|---------|-------|---------|
| `title` | Ano | Název produktu (max 140 znaků) | "Neon City Print" |
| `description` | Ano | Popis (HTML povoleno, max 5000 znaků) | "<b>Digital print</b>..." |
| `price` | Ano | Cena v USD | 12.99 |
| `tags` | Ano | 13 štítků oddělených čárkami | "digital,art,neon,modern" |
| `category_path` | Doporučeno | Cesta ke kategorii | "Art&Collectibles:Prints:DigitalPrints" |
| `image_paths` | Doporučeno | Cesty k obrázkům (max 10, oddělené `;`) | "./images/img1.jpg;./images/img2.jpg" |
| `shop_section` | Volitelně | Sekce obchodu | "Digital Prints" |

### Příklad

```csv
title,description,price,tags,category_path,image_paths,shop_section
"Neon Cityscape","<b>AI-generated neon cityscape digital print</b>. Perfect for modern wall decor. High resolution 300 DPI. Instant download.",14.99,"digital art,neon,cityscape,modern,wall art,printable,AI art,abstract,night city","Art&Collectibles:Prints:DigitalPrints","./images/neon01.jpg;./images/neon02.jpg","AI Digital Prints"
"Abstract Waves","<b>Beautiful abstract waves</b> with calming blue tones. Perfect for bedroom or office. Digital download ready.",12.99,"digital art,abstract,waves,ocean,blue,modern art,printable","Art&Collectibles:Prints:DigitalPrints","./images/waves01.jpg","AI Digital Prints"
```

### Tipy pro CSV

1. **Uvozovky** - Používejte pro texty s čárkami
2. **HTML v popisu** - Podporováno: `<b>`, `<i>`, `<br>`, `<ul>`, `<li>`
3. **Obrázky** - Maximálně 10 na produkt
4. **Štítky** - Maximálně 13, každý max 20 znaků

---

## Pokročilé použití

### Použití existujícího profilu Chrome

Pokud chcete zachovat přihlášení a nastavení prohlížeče:

```bash
# Windows
python src/uploader.py --mode bulk --user-data-dir "C:/Users/VaseJmeno/AppData/Local/Google/Chrome/User Data"

# macOS
python src/uploader.py --mode bulk --user-data-dir "/Users/VaseJmeno/Library/Application Support/Google/Chrome"

# Linux
python src/uploader.py --mode bulk --user-data-dir "/home/VaseJmeno/.config/google-chrome"
```

### Úprava zpoždění

Upravte v `config.json`:

```json
{
  "delay_min": 5,
  "delay_max": 15,
  "max_products_per_hour": 30
}
```

Vyšší hodnoty = menší riziko detekce, ale pomalejší nahrávání.

### Rate limiting

Automaticky se zpomalí po 10 produktech (30s pauza).

### Logy

Logy se ukládají do složky `logs/`:

```
logs/
├── etsy_uploader_20240215_143022.log
├── error_login_failed_20240215_143045.png
└── error_upload_error_20240215_144512.png
```

---

## Řešení problémů

### Selektory nefungují

1. Spusťte Selector Recorder znovu
2. Zkontrolujte `src/selectors.json`
3. Použijte interaktivní režim

### Detekce botů

- Zvyšte `delay_min` a `delay_max`
- Vypněte headless režim
- Použijte existující profil prohlížeče

### Přihlášení selže

- Zkontrolujte přihlašovací údaje
- Vypněte 2FA dočasně
- Použijte `--user-data-dir` s vaším profilem

### Captcha

- Řešte manuálně v otevřeném prohlížeči
- Po vyřešení pokračuje skript automaticky

### Chybějící obrázky

- Zkontrolujte cesty v CSV
- Používejte relativní cesty od umístění skriptu

### Chyby s CSV

- Ověřte formát v Excelu/LibreOffice
- Používejte UTF-8 kódování
- Zkontrolujte záhlaví sloupců

---

## Aktualizace při změně Etsy UI

Když Etsy aktualizuje rozhraní:

```bash
# 1. Zálohovat selektory
cp src/selectors.json src/selectors.json.backup

# 2. Spustit recorder
python src/selector_recorder.py \
  --url "https://www.etsy.com/your/shops/NAZEV/listings/new" \
  --mode both

# 3. Otestovat
python src/uploader.py --mode single --product-id 1
```

---

## Bezpečnostní upozornění

⚠️ **Důležité:**

1. Tento nástroj může být v rozporu s podmínkami Etsy
2. Etsy může pozastavit účet při podezřelé aktivitě
3. Používejte s rozvahou a na vlastní riziko
4. Doporučujeme nižší rychlosti nahrávání
5. Pravidelně kontrolujte váš Etsy účet
