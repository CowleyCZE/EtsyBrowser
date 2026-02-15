# EtsyBrowser

Automatizační nástroj pro hromadné nahrávání produktů na Etsy bez použití oficiálního API.

## Funkce

- **Selector Recorder** - Automatická detekce a konfigurace CSS selektorů
- **Režim jednoho produktu** - Nahrání jednoho produktu pro testování
- **Hromadný režim** - Nahrání všech produktů z CSV souboru
- **Automatizace podobná lidskému modelu** - Náhodná zpoždění, scrollování, pohyby myši
- **Dynamické selektory** - Snadná aktualizace při změnách Etsy UI

## Rychlý start

### 1. Instalace

```bash
git clone https://github.com/CowleyCZE/EtsyBrowser.git
cd EtsyBrowser
pip install -r requirements.txt
```

Více v [setup.md](./setup.md)

### 2. Konfigurace

Upravte `config.json` s vašimi přihlašovacími údaji:

```json
{
  "etsy_url": "https://www.etsy.com/your/shops/NAZEV_OBCHODU/manage",
  "email": "vas_email@email.com",
  "password": "vase_heslo"
}
```

### 3. Konfigurace selektorů

```bash
python src/selector_recorder.py \
  --url "https://www.etsy.com/your/shops/NAZEV/listings/new" \
  --mode both
```

### 4. Spuštění

```bash
# Hromadné nahrávání
python src/uploader.py --mode bulk

# Jeden produkt (testování)
python src/uploader.py --mode single --product-id 1
```

## Dokumentace

| Soubor | Popis |
|--------|-------|
| [setup.md](./setup.md) | Kompletní návod k instalaci |
| [manual.md](./manual.md) | Podrobný návod k použití |
| [SELECTOR_RECORDER.md](./SELECTOR_RECORDER.md) | Dokumentace Selector Recorderu |

## Tech Stack

- **Python 3.10+**
- **Selenium 4.15.2** - Prohlížečová automatizace
- **WebDriver Manager 4.0.1** - Správa ChromeDriver
- **Pandas 2.1.4** - Práce s CSV
- **Pillow 10.1.0** - Zpracování obrázků
- **Selenium Stealth 1.0.6** - Ochrana před detekcí botů

## Podporovaná pole Etsy

### Povinné
- Název produktu
- Popis (HTML)
- Cena
- Množství (999 pro digitální)
- Obrázky (až 10)

### Volitelné
- Štítky (max 13)
- Kategorie
- Sekce obchodu
- Digitalní produkt ( automaticky nastaveno)

## Struktura projektu

```
EtsyBrowser/
├── src/
│   ├── uploader.py           # Hlavní skript pro nahrávání
│   ├── selector_recorder.py # Nástroj pro zaznamenávání selektorů
│   ├── browser_utils.py     # Pomocné funkce pro Selenium
│   ├── fill_csv.py          # Zpracování CSV
│   ├── logger.py            # Logování
│   └── selectors.json       # Konfigurace selektorů
├── images/                  # Obrázky produktů
├── products.csv             # Data produktů
├── config.json             # Konfigurace
├── setup.md                # Návod k instalaci
├── manual.md               # Návod k použití
└── requirements.txt        # Python závislosti
```

## CSV formát

```csv
title,description,price,tags,category_path,image_paths,shop_section
"Název","<b>Popis</b>",12.99,"tag1,tag2,tag3","Art&Collectibles:Prints:DigitalPrints","./images/img1.jpg","Sekce"
```

## Řešení problémů

### Selektory nefungují
Spusťte Selector Recorder znovu:
```bash
python src/selector_recorder.py --url "URL" --mode both
```

### Detekce botů
- Zvyšte `delay_min` a `delay_max` v config.json
- Vypněte headless režim

### Captcha
- Řešte manuálně v prohlížeči
- Skript pokračuje automaticky po vyřešení

## Bezpečnostní upozornění

⚠️ Tento nástroj může být v rozporu s podmínkami služby Etsy. Používejte na vlastní riziko.

Doporučení:
- Používejte nižší rychlosti nahrávání
- Pravidelně kontrolujte váš účet
- Nepronehrávat příliš mnoho produktů za hodinu

## Licence

MIT License
