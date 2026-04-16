# 🤖 STORK PILOT - Etsy Automation System (auto_etsy)

Automatizovaný systém pro generování, úpravu a nahrávání digitálního umění (Wall Art) na Etsy. Tento nástroj využívá AI (Flux, Groq, Gemini) k vytvoření kompletního produktu od průzkumu trhu až po nahrání draftu do vašeho obchodu.

## 🚀 Rychlý start

### 1. Instalace závislostí
Ujistěte se, že máte nainstalovaný Python a potřebné knihovny:
```bash
pip install requests pillow numpy groq python-dotenv
```

### 2. Konfigurace (API Klíče)
Přejmenujte soubor `.env.example` na `.env` a doplňte své údaje:
- **GROQ_API_KEY**: Pro generování promptů a SEO textů (Llama 3).
- **GEMINI_GEN_API_KEY**: (Volitelné) Pro pokročilou analýzu.
- **ETSY_API_KEY / SHOP_ID**: Vaše údaje z Etsy Developer Console.
- **ETSY_ACCESS_TOKEN**: Váš OAuth2 Access Token pro nahrávání.

### 3. Spuštění
Hlavní skript spustíte příkazem:
```bash
python super_robot.py
```

---

## 🎮 Ovládání systému (Menu)

Po spuštění se zobrazí interaktivní menu s následujícími volbami:

1. **Spustit Generátor (Full Flow)**:
   - Robot provede průzkum trhu.
   - Vygeneruje 5 tematických obrazů (Bundle).
   - Vytvoří tiskové soubory v různých poměrech stran.
   - Vygeneruje 8 profesionálních mockupů.
   - Připraví SEO metadata a nabídne nahrání na Etsy.

2. **Spustit SOLO úpravy**:
   - Zpracuje všechny obrázky, které ručně vložíte do složky `00_Input_Queue/_To_Edit`.
   - Pro každý obrázek vytvoří samostatný produkt (Single), mockupy a metadata.

3. **Generovat ze seznamu**:
   - Načte prompty ze souboru `prompts.json` a hromadně vygeneruje umění.

4. **Browser Mode (Mockupy)**:
   - Interaktivní režim pro procházení složek a ruční generování mockupů.

5. **Testování mockupu**:
   - Umožňuje vyzkoušet konkrétní šablonu na jednom obrázku.

6. **Kalibrační Server**:
   - Spustí lokální webový server (`mereni.html`) pro přesné nastavení pozic obrazů v mockup šablonách.

7. **Archivovat staré soubory**:
   - Přesune zpracované vstupy do složky `03_Archive` podle měsíce.

---

## 📁 Struktura projektu (Dle pravidla.md)

- `00_Input_Queue/`: Místo pro vaše vstupy (obrázky k úpravě, seznamy promptů).
- `01_System_Core/`: Jádro systému (skripty, šablony mockupů, konfigurace).
- `02_Warehouse/`: Hotové produkty připravené k prodeji.
  - `Singles/`: Jednotlivé obrazy.
  - `Bundles/`: Sady obrazů.
- `03_Archive/`: Historie zpracovaných souborů.

---

## 🛠️ Integrace s Etsy

Systém po dokončení každého produktu (volba 1 a 2) položí dotaz:
`❓ Chceš tento produkt nahrát na Etsy jako draft? (y/n)`

Při volbě **y** dojde k:
1. Vytvoření nového listingu jako **Draft**.
2. Automatickému nahrání všech 8 vygenerovaných mockupů.
3. Nastavení názvu, tagů a ceny dle vygenerovaných metadat.

---

## 📝 Poznámky
- **Kvalita tisku**: Generátor automaticky vytváří soubory s vysokým rozlišením (300 DPI) vhodné pro velkoformátový tisk.
- **Mockupy**: Šablony se nacházejí v `1_Mockup_Sablony`. Jejich koordináty lze ladit přes Kalibrační Server.
