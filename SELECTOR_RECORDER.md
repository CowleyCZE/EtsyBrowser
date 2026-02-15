# Selector Recorder - Návod k použití

Nástroj pro automatické zaznamenávání CSS selektorů z Etsy formulářů. Umožňuje dynamickou konfiguraci bez nutnosti ruční úpravy kódu.

## Obsah

1. [Rychlý start](#rychlý-start)
2. [Instalace](#instalace)
3. [Použití Selector Recorderu](#použití-selector-recorderu)
   - [Automatický režim](#automatický-režim)
   - [Interaktivní režim](#interaktivní-režim)
   - [Kombinovaný režim](#kombinovaný-režim)
4. [Použití Uploaderu](#použití-uploaderu)
5. [Řešení problémů](#řešení-problémů)

---

## Rychlý start

```bash
# 1. Nainstalovat závislosti
pip install -r requirements.txt

# 2. Spustit selector recorder (oba režimy)
python src/selector_recorder.py --url "https://www.etsy.com/your/shops/NAZEV_OBCHODU/listings/new" --mode both

# 3. Nakonfigurovat přihlašovací údaje v config.json

# 4. Spustit hromadné nahrávání
python src/uploader.py --mode bulk
```

---

## Instalace

### Požadavky

- Python 3.10+
- Google Chrome
- pip

### Kroky

```bash
# Klonovat repozitář
git clone https://github.com/CowleyCZE/EtsyBrowser.git
cd EtsyBrowser

# Nainstalovat Python závislosti
pip install -r requirements.txt

# Nakonfigurovat přihlašovací údaje
# Upravte soubor config.json
```

### Konfigurace config.json

```json
{
  "etsy_url": "https://www.etsy.com/your/shops/VASE_JMENO_OBCHODU/manage",
  "email": "vas_email@email.com",
  "password": "vase_heslo",
  "headless": false,
  "delay_min": 2,
  "delay_max": 10,
  "max_products_per_hour": 50,
  "csv_file": "products.csv"
}
```

---

## Použití Selector Recorderu

### Autmatický režim

Automaticky prohledá stránku a pokusí se najít běžné elementy Etsy.

```bash
python src/selector_recorder.py \
  --url "https://www.etsy.com/your/shops/NAZEV/listings/new" \
  --mode auto
```

**Výstup:**
```
INFO: ====================
INFO: AUTO MODE - Automatická detekce elementů
INFO: ====================
INFO: Hledám: title_input
INFO:   ✓ NALEZEN: input[name="title"]
INFO: Hledám: description_editor
INFO:   ✗ NENALEZEN
...
INFO: AUTO MODE DOKONČEN
INFO: Nalezeno: 8/16
```

### Interaktivní režim

Manuální zaznamenávání selektorů klikáním na elementy.

```bash
python src/selector_recorder.py \
  --url "https://www.etsy.com/your/shops/NAZEV/listings/new" \
  --mode interactive
```

**Průběh:**

1. Otevře se prohlížeč s Etsy stránkou
2. Přihlaste se manuálně (pokud ještě nejste)
3. Klikněte na element, který chcete zaznamenat (např. pole "Název")
4. V konzoli zadejte typ elementu (např. `1` pro title_input)
5. Opakujte pro další elementy
6. Stiskněte `s` pro uložení

**Klávesové zkratky v interaktivním režimu:**

| Klávesa | Akce |
|---------|------|
| `1-9,0` | Zaznamenat jako typ (1=title, 2=price, ...) |
| `a-z` | Zaznamenat jako vlastní název |
| `Enter` | Zaznamenat jako další volný typ |
| `l` | Zobrazit dostupné typy |
| `d` | Smazat poslední záznam |
| `s` | Uložit a ukončit |
| `q` | Ukončit bez uložení |

### Kombinovaný režim

Spustí nejprve automatický, pak interaktivní režim.

```bash
python src/selector_recorder.py \
  --url "https://www.etsy.com/your/shops/NAZEV/listings/new" \
  --mode both
```

### Pokročilé možnosti

```bash
# S existujícím profilem prohlížeče (zachová přihlášení)
python src/selector_recorder.py \
  --url "URL" \
  --user-data-dir "C:/Users/Uzivatel/AppData/Local/Google/Chrome/User Data"

# Výstup do jiného souboru
python src/selector_recorder.py \
  --url "URL" \
  --output "custom_selectors.json"

# Headless režim (pro automatizaci)
python src/selector_recorder.py \
  --url "URL" \
  --headless
```

---

## Použití Uploaderu

### Hromadný režim

```bash
python src/uploader.py --mode bulk
```

### Jeden produkt

```bash
python src/uploader.py --mode single --product-id 1
```

### S vlastním CSV

```bash
python src/uploader.py --mode bulk --csv moje_produkty.csv
```

### S vlastními selektory

```bash
python src/uploader.py \
  --mode bulk \
  --selectors "src/selectors.json"
```

---

## Výstupní soubor selectors.json

Po spuštění recorderu se vytvoří soubor `src/selectors.json`:

```json
{
  "title_input": {
    "primary": "input[name=\"title\"]",
    "fallback": [
      "input[placeholder*=\"title\" i]",
      "input[id*=\"title\" i]"
    ],
    "xpath": "//input[@name='title']",
    "tag": "input",
    "text": ""
  },
  "price_input": {
    "primary": "input[name=\"price\"]",
    "fallback": [],
    "xpath": "//input[@name='price']",
    "tag": "input",
    "text": ""
  }
}
```

### Formát

| Pole | Popis |
|------|-------|
| `primary` | Hlavní (nejspolehlivější) CSS selektor |
| `fallback` | Alternativní selektory, pokud primární selže |
| `xpath` | XPath selektor (záložní varianta) |
| `tag` | HTML tag elementu |
| `text` | Text obsahu elementu |

---

## Řešení problémů

### Selektory nefungují

1. Spusťte recorder znovu - Etsy mění UI
2. Zkontrolujte `src/selectors.json`
3. Použijte interaktivní režim pro ruční zaznamenání

### Detekce botů

- Zvyšte `delay_min` a `delay_max` v config.json
- Vypněte headless režim
- Použijte `--headless=false` při spuštění

### Přihlášení selže

- Použijte existující profil prohlížeče: `--user-data-dir "CESTA_K_PROFILU"`
- Vypněte 2FA dočasně
- Zkontrolujte přihlašovací údaje v config.json

### Chybějící obrázky

- Zkontrolujte, že složka `images/` obsahuje obrázky
- Cesty v CSV musí být správné (relativní nebo absolutní)

---

## Aktualizace při změně Etsy UI

Když Etsy aktualizuje své rozhraní:

```bash
# 1. Zálohovat stávající selektory
cp src/selectors.json src/selectors.json.backup

# 2. Spustit recorder znovu
python src/selector_recorder.py \
  --url "https://www.etsy.com/your/shops/NAZEV/listings/new" \
  --mode both

# 3. Otestovat uploader
python src/uploader.py --mode single --product-id 1
```

---

## Další zdroje

- [Selenium dokumentace](https://www.selenium.dev/documentation/)
- [CSS Selectors Reference](https://www.w3schools.com/cssref/css_selectors.asp)
- [XPath Tutorial](https://www.w3schools.com/xml/xpath_intro.asp)
