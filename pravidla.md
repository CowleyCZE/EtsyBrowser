# 📂 PRAVIDLA ORGANIZACE DAT

PROJEKT STORK PILOT v2.0
Autor: Cowley
Status: Aktivní (Závazný protokol)
Cíl: Standardizace souborového systému pro maximální efektivitu a budoucí automatizaci (Etsy API).

1. ZÁKLADNÍ FILOZOFIE (The Prime Directives)
Atomarita: Každý produkt (Single nebo Bundle) je samostatná entita uzavřená ve vlastní složce.Unikátnost: Každý produkt má unikátní identifikátor (SKU), který se nemění.Oddělení rolí: Zdrojová data (Source), Tisková data (Production) a Marketingová data (Mockups) jsou striktně oddělena.Strojová čitelnost: Názvy souborů a struktura složek musí být čitelné skriptem bez lidského zásahu.

2. NOMENKLATURA (Systém pojmenování)
Všechny složky produktů a kritické soubory musí začínat unikátním SKU kódem.Formát SKU: SP-{YYMMDD}-{SEQ}-{TYPE}SP: Prefix projektu (Stork Pilot).YYMMDD: Datum vytvoření (např. 260208 pro 8. února 2026).SEQ: Pořadové číslo produktu v daný den (např. 01, 02).TYPE: Typ produktu (S = Single, B = Bundle).Příklady:SP-260208-01-S (První samostatný obraz dne)SP-260208-02-B (Druhý produkt dne, což je balíček obrazů)

3. ADRESÁŘOVÁ MAPA (Directory Map)
Kořenový adresář: Etsy_StorkPilot_Workspace/

├── 00_Input_Queue/           # [VSTUP] Surové materiály čekající na zpracování
│   ├── _To_Edit/             # Obrázky pro manuální úpravu/upscale
│   └── _Batch_Lists/         # JSON seznamy promptů pro hromadnou výrobu
│
├── 01_System_Core/           # [MOZEK] Skripty a konfigurační soubory
│   ├── super_robot.py        # Hlavní výkonný skript
│   ├── Assets/               # Loga, vodoznaky, fonty
│   ├── Templates_Mockup/     # PSD/PNG šablony pro mockupy
│   └── Configs/              # Prompty, nastavení API
│
├── 02_Warehouse/             # [VÝSTUP] Hotové produkty připravené k prodeji
│   ├── Singles/              # Složky pro samostatné obrazy
│   └── Bundles/              # Složky pro sady (set of 3, set of 6...)
│
└── 03_Archive/               # [HISTORIE] Staré nebo vyřazené projekty
    └── YYYY_MM/              # Archivace po měsících
4. STRUKTURA PRODUKTOVÉ SLOŽKY
Každý produkt ve složce 02_Warehouse musí dodržovat tuto striktní strukturu.
A. Varianta SINGLE (Jeden obraz)
Název složky: {SKU}_{KlicoveSlovo}(Např: SP-260208-01-S_AbstractGeometric)📁 SP-260208-01-S_AbstractGeometric/

├── 📄 00_Master_Source.png         # Původní generace (záloha, nikdy nemazat)
├── 📂 01_Print_Files/              # Soubory pro zákazníka (High Quality JPG/PDF)
│   ├── SP-...-S_ISO-A1.jpg         # Poměr ISO (A1-A5)
│   ├── SP-...-S_Ratio-2x3.jpg      # Poměr 2:3
│   ├── SP-...-S_Ratio-3x4.jpg      # Poměr 3:4
│   └── SP-...-S_Ratio-4x5.jpg      # Poměr 4:5
├── 📂 02_Marketing_Assets/         # Obrázky pro Etsy galerii
│   ├── 01_Main_Thumbnail.jpg       # Hlavní upoutávka (první viditelná)
│   ├── 02_Interior_LivingRoom.jpg  # Mockup v interiéru
│   └── 03_Size_Guide.jpg           # Infografika velikostí
└── 📂 03_Metadata/                 # Textová data
    └── listing_data.json           # Title, Tags, Description, Price (pro API)
B. Varianta BUNDLE (Sada obrazů)
Název složky: {SKU}_{NazevSady}(Např: SP-260208-02-B_BotanicalSet3)📁 SP-260208-02-B_BotanicalSet3/
├── 📂 00_Masters/                  # Zdrojové soubory všech částí sady
│   ├── Art_A.png
│   ├── Art_B.png
│   └── Art_C.png
├── 📂 01_Print_Files_Ready/        # Finální struktura pro zákazníka
│   ├── 📁 Art_A/                   # Rozřezané velikosti pro obraz A
│   │   ├── Art_A_ISO.jpg
│   │   └── ...
│   ├── 📁 Art_B/
│   │   └── ...
│   └── 📦 COMPLETE_SET.zip         # ZIP archiv (pokud Etsy povolí velikost)
├── 📂 02_Marketing_Assets/
│   ├── 01_Bundle_Collage.jpg       # Koláž všech obrazů v sadě
│   ├── 02_Room_View_All.jpg        # Všechny obrazy na jedné zdi
│   └── ...
└── 📂 03_Metadata/
    └── listing_data.json
5. STANDARDY SOUBORŮ5.1 Tisková data (Print Files)Formát: JPG (Quality 95-100) nebo PDF (Print Ready).DPI: Minimálně 300 DPI pro cílovou velikost.Barevný profil: sRGB (pro digitální downloady standard).Pojmenování: Musí obsahovat poměr stran (Ratio) nebo formát (ISO).5.2 Mockupy (Marketing)Formát: JPG (optimalizováno pro web, šířka cca 2000-2500px).Pojmenování: Číslované 01_, 02_pro určení pořadí v galerii.5.3 Metadata (JSON)Formát pro listing_data.json:{
  "sku": "SP-260208-01-S",
  "title": "Abstract Geometric Wall Art...",
  "description_generated": "Elevate your space...",
  "seo_tags": ["geometric", "mid century", "wall decor"],
  "pricing": {
    "currency": "USD",
    "amount": 5.90
  },
  "file_paths": {
    "print_iso": "./01_Print_Files/SP-260208-01-S_ISO-A1.jpg"
  }
}
6. AUTOMATIZAČNÍ PRAVIDLA (Logika skriptu)Inkrementace: Skript před vytvořením nového produktu zkontroluje 02_Warehouse a najde poslední použité číslo SEQ pro dnešní datum.Validace: Před přesunem do Warehouse skript ověří existenci všech povinných variant (Upscale + Ratios).Bundle Logic:Iteruje přes všechny obrazy v sadě.Generuje ZIP soubor z 01_Print_Files_Ready.Vytváří koláž (Collage) pro hlavní miniaturu.Ochrana zdrojů: Složka 00_Master_Source je "Read-Only". Skript do ní zapisuje pouze při generování, nikdy při úpravách.Konec protokolu.
