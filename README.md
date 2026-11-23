# EtsyBrowser - Kompletní automatizační systém pro Etsy

Automatizační nástroj pro generování, úpravu a nahrávání digitálního umění (Wall Art) na Etsy. Systém kombinuje AI generování (Flux, Groq, Gemini) s automatizovaným nahráváním prostřednictvím Selenium.

## 📌 Systémy

### 1. **Auto Etsy (AI Generování)**
Automatizovaný systém pro generování kompletních produktů od průzkumu trhu až po nahrání draftu.

### 2. **Selenium Uploader**
Automatizace nahrávání produktů na Etsy bez použití oficiálního API.

---

## 🚀 Rychlý start

### Instalace závislostí

```bash
pip install -r requirements.txt
```

### Auto Etsy (AI Systém)

#### Konfigurace
Přejmenujte soubor `.env.example` na `.env` a doplňte své údaje:
- **GROQ_API_KEY**: Pro generování promptů a SEO textů (Llama 3)
- **GEMINI_GEN_API_KEY**: (Volitelné) Pro pokročilou analýzu
- **ETSY_API_KEY / SHOP_ID**: Vaše údaje z Etsy Developer Console
- **ETSY_ACCESS_TOKEN**: Váš OAuth2 Access Token pro nahrávání

#### Spuštění

```bash
python automation/super_robot.py
```

#### Ovládání systému (Menu)

1. **Spustit Generátor (Full Flow)**
   - Robot provede průzkum trhu
   - Vygeneruje 5 tematických obrazů (Bundle)
   - Vytvoří tiskové soubory v různých poměrech stran
   - Vygeneruje 8 profesionálních mockupů
   - Připraví SEO metadata a nabídne nahrání na Etsy

2. **Spustit SOLO úpravy**
   - Zpracuje všechny obrázky v `automation/00_Input_Queue/_To_Edit`
   - Pro každý obrázek vytvoří samostatný produkt (Single), mockupy a metadata

3. **Generovat ze seznamu**
   - Načte prompty ze souboru `data/prompts.json` a hromadně vygeneruje umění

4. **Browser Mode (Mockupy)**
   - Interaktivní režim pro procházení složek a ruční generování mockupů

5. **Testování mockupu**
   - Umožňuje vyzkoušet konkrétní šablonu na jednom obrázku

6. **Kalibrační Server**
   - Spustí lokální webový server pro přesné nastavení pozic obrazů v mockup šablonách

7. **Archivovat staré soubory**
   - Přesune zpracované vstupy do složky `automation/03_Archive` podle měsíce

### Selenium Uploader

#### Konfigurace

Upravte `config.json` s vašimi přihlašovacími údaji:

```json
{
  "etsy_url": "https://www.etsy.com/your/shops/NAZEV_OBCHODU/manage",
  "email": "vas_email@email.com",
  "password": "vase_heslo"
}
```

#### Konfigurace selektorů

```bash
python src/selector_recorder.py \
  --url "https://www.etsy.com/your/shops/NAZEV/listings/new" \
  --mode both
```

#### Spuštění

```bash
# Hromadné nahrávání
python src/uploader.py --mode bulk

# Jeden produkt (testování)
python src/uploader.py --mode single --product-id 1
```

---

## 📁 Struktura projektu

### Auto Etsy

- `automation/00_Input_Queue/`: Místo pro vaše vstupy (obrázky k úpravě, seznamy promptů)
- `automation/01_System_Core/`: Jádro systému (skripty, šablony mockupů, konfigurace)
- `automation/02_Warehouse/`: Hotové produkty připravené k prodeji
  - `Singles/`: Jednotlivé obrazy
  - `Bundles/`: Sady obrazů
- `automation/03_Archive/`: Historie zpracovaných souborů
- `automation/04_Delivery/`: Doručovací soubory (ZIPy)
- `data/prompts.json`: Konfigurační soubor pro generování
- `data/archive/`: Archiv starších verzí konfiguračních souborů

### Selenium Uploader

- `src/uploader.py`: Hlavní skript pro nahrávání
- `src/selector_recorder.py`: Nástroj pro zaznamenávání selektorů
- `src/browser_utils.py`: Pomocné funkce pro Selenium
- `src/fill_csv.py`: Zpracování CSV
- `src/logger.py`: Logování
- `src/selectors.json`: Konfigurace selektorů
- `images/`: Obrázky produktů
- `products.csv`: Data produktů

---

## 🎯 Funkce

### Auto Etsy

- **AI Generování**: Využívá Flux, Groq, Gemini pro vytvoření umění
- **Průzkum trhu**: Analyzuje trendy a konkurenční produkty
- **Mockup generátor**: Vytváří profesionální mockupy pro prezentaci
- **SEO optimalizace**: Generuje titulek, popis a tagy
- **Automatické nahrávání**: Nahrává drafty na Etsy prostřednictvím API

### Selenium Uploader

- **Selector Recorder**: Automatická detekce a konfigurace CSS selektorů
- **Režim jednoho produktu**: Nahrání jednoho produktu pro testování
- **Hromadný režim**: Nahrání všech produktů z CSV souboru
- **Automatizace podobná lidskému modelu**: Náhodná zpoždění, scrollování, pohyby myši
- **Dynamické selektory**: Snadná aktualizace při změnách Etsy UI

---

## 📄 Dokumentace

| Soubor | Popis |
|--------|-------|
| [setup.md](./setup.md) | Kompletní návod k instalaci |
| [manual.md](./manual.md) | Podrobný návod k použití Selenium Uploaderu |
| [SELECTOR_RECORDER.md](./SELECTOR_RECORDER.md) | Dokumentace Selector Recorderu |

---

## 🔧 Technický stack

- **Python 3.10+**
- **Selenium 4.15.2** - Prohlížečová automatizace
- **WebDriver Manager 4.0.1** - Správa ChromeDriver
- **Pandas 2.1.4** - Práce s CSV
- **Pillow 10.1.0** - Zpracování obrázků
- **Selenium Stealth 1.0.6** - Ochrana před detekcí botů
- **Requests** - HTTP požadavky pro API
- **Groq** - AI model pro generování textů
- **Pillow/Numpy** - Zpracování obrázků

---

## 📊 Podporovaná pole Etsy

### Povinná
- Název produktu
- Popis (HTML)
- Cena
- Množství (999 pro digitální)
- Obrázky (až 10)

### Volitelná
- Štítky (max 13)
- Kategorie
- Sekce obchodu
- Digitální produkt (automaticky nastaveno)

---

## 📝 CSV formát

```csv
title,description,price,tags,category_path,image_paths,shop_section_id
"Název","<b>Popis</b>",12.99,"tag1,tag2,tag3","Art&Collectibles:Prints:DigitalPrints","./images/img1.jpg","Sekce"
```

---

## 🔍 Integrace s Etsy

### Auto Etsy (API)
Systém po dokončení každého produktu položí dotaz:
`❓ Chceš tento produkt nahrát na Etsy jako draft? (y/n)`

Při volbě **y** dojde k:
1. Vytvoření nového listingu jako **Draft**
2. Automatickému nahrání všech 8 vygenerovaných mockupů
3. Nastavení názvu, tagů a ceny dle vygenerovaných metadat

### Selenium Uploader
Nahrává produkty prostřednictvím prohlížeče Chrome s automatizovanými akcemi.

---

## ⚠️ Řešení problémů

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

---

## 🛡️ Bezpečnostní upozornění

⚠️ Tento nástroj může být v rozporu s podmínkami služby Etsy. Používejte na vlastní riziko.

Doporučení:
- Používejte nižší rychlosti nahrávání
- Pravidelně kontrolujte svůj účet
- Neprohrávejte příliš mnoho produktů za hodinu

---

## 📝 Poznámky

- **Kvalita tisku**: Generátor automaticky vytváří soubory s vysokým rozlišením (300 DPI) vhodné pro velkoformátový tisk
- **Mockupy**: Šablony se nacházejí v `automation/1_Mockup_Sablony`. Jejich koordináty lze ladit přes Kalibrační Server
- **Konfigurace**: Hlavní konfigurace je v `config.json` (Selenium) a `.env` (Auto Etsy)

---

## 📜 Licence

MIT License
