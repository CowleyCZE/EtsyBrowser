# EtsyBrowser - Instalace

Automatizační nástroj pro hromadné nahrávání produktů na Etsy bez použití API.

## Požadavky

| Požadavek | Verze |
|-----------|-------|
| Python | 3.10+ |
| Google Chrome | Nejnovější |
| pip | Aktuální |

## Kroky instalace

### 1. Stažení projektu

```bash
git clone https://github.com/CowleyCZE/EtsyBrowser.git
cd EtsyBrowser
```

### 2. Instalace Python závislostí

```bash
pip install -r requirements.txt
```

Nainstalují se tyto balíčky:
- `selenium==4.15.2` - Prohlížečová automatizace
- `webdriver-manager==4.0.1` - Automatická správa ChromeDriver
- `pandas==2.1.4` - Práce s CSV soubory
- `pillow==10.1.0` - Zpracování obrázků
- `selenium-stealth==1.0.6` - Ochrana před detekcí botů
- `python-dotenv==1.0.0` - Práce s proměnnými prostředí

### 3. Konfigurace

#### Upravte `config.json`

Otevřete soubor `config.json` a vyplňte vaše údaje:

```json
{
  "etsy_url": "https://www.etsy.com/your/shops/NAZEV_VASHOBCHODU/manage",
  "email": "vas_email@email.com",
  "password": "vase_heslo",
  "headless": false,
  "delay_min": 2,
  "delay_max": 10,
  "max_products_per_hour": 50,
  "csv_file": "products.csv"
}
```

| Parametr | Popis |
|----------|-------|
| `etsy_url` | URL vašeho obchodu na Etsy |
| `email` | Email účtu Etsy |
| `password` | Heslo účtu Etsy |
| `headless` | `true` = bez GUI, `false` = s GUI (doporučeno) |
| `delay_min` | Minimální zpoždění mezi akcemi (sekundy) |
| `delay_max` | Maximální zpoždění mezi akcemi (sekundy) |
| `max_products_per_hour` | Maximální počet produktů za hodinu |
| `csv_file` | Cesta k CSV souboru s produkty |

### 4. Příprava produktů

#### Formát CSV souboru

Vytvořte nebo upravte soubor `products.csv`:

```csv
title,description,price,tags,category_path,image_paths,shop_section
"Název produktu","<b>Popis</b> ve formátu HTML",12.99,"tag1,tag2,tag3","Art&Collectibles:Prints:DigitalPrints","./images/foto1.jpg;./images/foto2.jpg","Sekce obchodu"
```

| Sloupec | Povinný | Popis |
|---------|---------|-------|
| `title` | Ano | Název produktu |
| `description` | Ano | Popis (HTML formátování povoleno) |
| `price` | Ano | Cena v USD |
| `tags` | Ano | Štítky oddělené čárkami (max 13) |
| `category_path` | Doporučeno | Cesta ke kategorii |
| `image_paths` | Doporučeno | Cesty k obrázkům oddělené středníkem |
| `shop_section` | Volitelně | Sekce obchodu |

#### Příprava obrázků

1. Vytvořte složku `images/`
2. Vložte obrázky produktů (JPG, PNG)
3. V CSV odkazujte na obrázky relativní cestou

### 5. Konfigurace selektorů (volitelné)

#### Automatická konfigurace

Spusťte Selector Recorder pro automatickou detekci elementů:

```bash
python src/selector_recorder.py \
  --url "https://www.etsy.com/your/shops/NAZEV/listings/new" \
  --mode both
```

Více v sekci [Selector Recorder](./manual.md#selector-recorder).

---

## Ověření instalace

### Test konfigurace

```bash
# Spustit v testovacím režimu (jeden produkt)
python src/uploader.py --mode single --product-id 1
```

Pokud se otevře prohlížeč a začne proces nahrávání, instalace je úspěšná.

---

## Řešení problémů při instalaci

### "command not found: pip"

```bash
# Windows
py -m pip install -r requirements.txt

# Linux/Mac
python3 -m pip install -r requirements.txt
```

### ChromeDriver chyba

```bash
# Automatická instalace
pip install webdriver-manager
```

### Import chyby

```bash
# Aktualizujte pip
pip install --upgrade pip
```

---

## Další kroky

Po úspěšné instalaci pokračujte do [Manual](./manual.md) pro použití nástroje.
