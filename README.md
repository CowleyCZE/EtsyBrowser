# Nástroj pro hromadné nahrávání do prohlížeče Etsy pro StorkVisionArt

Automatizační nástroj založený na technologii Selenium pro hromadné nahrávání digitálních produktů na Etsy bez použití oficiálního API.

## Funkce

- **Režim rychlé úpravy**: Automatické vyplňování formuláře Etsy z dat CSV
- **Režim hromadné úpravy**: Stáhněte si šablonu Etsy CSV, naplňte daty, nahrajte zpět
- **Nahrávání obrázků**: Přetáhněte a vložte nebo vyberte soubor až pro 10 obrázků na produkt
- **Inteligentní vyplňování**: Rozbalovací nabídka kategorií, automaticky generované štítky, ověření ceny
- **Automatizace podobná lidskému modelu**: Náhodné zpoždění, posouvání, pohyby myši, aby se zabránilo detekci botů

## Podporovaná pole Etsy

### Povinné
- název
- popis (HTML)
- cena
- množství (999 pro digitální)
- obrázky (až 10)

### Kategorie
- Umění a sběratelské předměty > Tisky > Digitální tisky/Nástěnné umění

### Stav nabídky
- Stav: Aktivní
- Kdo vytvořil: AI_GENERATED
- Je digitální: ANO

### Štítky
- 13 automaticky generovaných štítků (např. „digitální umění, tisk AI, nástěnná dekorace, moderní umění...“)

### Doprava
- Digitální stažení (ne (doprava (vyžadováno)

## Tech Stack

- Python 3.10+
- Selenium 4.15.2
- WebDriver Manager 4.0.1
- Pandas 2.1.4
- Pillow 10.1.0

## Struktura projektu

```
├── config.json # Přihlášení a nastavení Etsy
├── products.csv # Zdrojová data produktu
├── requirements.txt # Závislosti Pythonu
├── src/
│ ├── __init__.py
│ ├── browser_utils.py # Nastavení a pomocníci prohlížeče Selenium
│ ├── fill_csv.py # Výplň CSV
│ ├── logger.py # Konfigurace protokolování
│ └── uploader.py # Hlavní skript pro nahrávání
├── images/ # Adresář obrázků produktu
└── logs/ # Snímky obrazovky a protokoly chyb
```

## Struktura CSV (products.csv)

```csv
title, description, price, tags, category_path, image_paths, shop_section
"Neonový tisk městské krajiny","<b>Digitální tisk městské krajiny vygenerovaný umělou inteligencí</b>. Okamžité stažení.",12.99,"digital art,neon,cityscape,modern,wall art,printable","Art&Collectibles:Prints:DigitalPrints","./images/neon01.jpg;./images/neon02.jpg","Digitální tisky vygenerované umělou inteligencí"
```

## Pracovní postup

1. **START** → Přihlaste se na etsy.com/your/shops/StorkVisionArt/manage
2. **MODE1 (Jednotlivě)**: Přidat inzerát → Vyplnit formulář → Nahrát obrázky → Publikovat
3. **REŽIM2 (Hromadně)**: Nástroje → Hromadná úprava CSV → Stáhnout šablonu → Vyplnit → nahrát
4. **OVĚŘENÍ**: Kontrola úspěchu → uložit listing_id → další produkt
5. **ŘEŠENÍ CHYB**: Snímek obrazovky + opakovat 3x → přeskočit → protokolovat
6. **HOTOVO**: Zpráva (X/100 úspěšné, uplynulý čas)

## Instalace

```bash
git clone <repo>
pip install -r requirements.txt
cp config.example.json config.json # Přidat e-mail/heslo
python fill_csv.py # Vyplnit šablonu Etsy z vašeho CSV
python uploader.py --mode bulk --headless
```

## Konfigurace

Upravte `config.json` pomocí svých přihlašovacích údajů Etsy:

```json
{
"etsy_url": "https://www.etsy.com/your/shops/StorkVisionArt/manage",
"email": "your@email.com",
"password": "your_password",
"headless": false,
"delay_min": 2,
"delay_max": 10,
"max_products_per_hour": 50
}
```

## Použití

### Režim jednoho produktu
```bash
python uploader.py --mode single --product-id 1
```

### Hromadný režim
```bash
python uploader.py --mode bulk --headless
```

### S vlastním CSV
```bash
python uploader.py --csv custom_products.csv
```

## Výhody oproti API

- ✅ Není vyžadováno schválení API (funguje ihned po instalaci)
- ✅ Podporuje varianty, personalizaci, slevy
- ✅ Aktualizace Etsy se aplikují automaticky
- ✅ Náhled před publikováním

## Omezení a alternativní řešení

### Detekce botů
- **Řešení**: selenium-stealth, náhodní uživatelští agenti, lidské zpoždění

### Limity rychlosti (~10/min)
- **Řešení**: 30s pauza mezi produkty, max. 50/hod

### Captcha
- **Řešení**: Záložní přihlášení 2FA, příznak ručního zásahu
