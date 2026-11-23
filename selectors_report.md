# Zpráva o nalezených selektorech pro Etsy Listing Editor

Tento report shrnuje ověřené a stabilní selektory pro formulář nového inzerátu na Etsy (`/your/shops/me/listing-editor/create`), získané a analyzované z živé DOM struktury přes Playwright / Chrome profil.

---

## 1. Zásadní poznatky o chování nového formuláře Etsy

1. **Quick list vs. Standard list:**
   - Etsy nově standardně otevírá rozhraní v režimu *Quick list* (průvodce).
   - Pro přepnutí do plného formuláře je nutné kliknout na tlačítko obsahující text `Switch to standard list` a potvrdit dialog tlačítkem `Discard and switch`.

2. **Volba Digital vs. Physical:**
   - Ve starším formuláři bývala samostatná volba typu produktu (Physical / Digital) formou radio buttonů.
   - V novém rozhraní je typ určen **vybranou kategorií**.
   - Například volba kategorie `Clip Art & Image Files` (nebo obecně digitální kategorie) automaticky přepne inzerát do digitálního režimu a dynamicky vloží do DOM sekci `#field-digitalFiles` a sekci dotazu na tvorbu digitálního obsahu.

3. **Sekce tvorby a AI (AI Disclosure):**
   - Po zvolení digitální kategorie se v sekci *How it's made* objeví dotaz **How is this digital content created?** se třemi možnostmi pod radio skupinou `name="whatContent"`:
     - `Created by me` (`value="original"`)
     - `Compiled by me` (`value="compiled"`)
     - `With an AI generator` (`value="ai_gen"`)
   - Tlačítko `Add info` v sekci Legal and Compliance slouží pro GPSR bezpečnostní a výrobní informace, zatímco pro výrobní partnery slouží tlačítko s textem `Add production partners`.

4. **Vyhýbání se náhodným UUID:**
   - Etsy pro většinu radio buttonů generuje dynamická ID ve formátu `wt-radio-<uuid>`.
   - Všechny selektory pro tyto prvky (`whoMade`, `isSupply`, `whatContent`) byly navrženy stabilně pomocí atributů `name`, `value`, indexů v rámci sekce (`#field-whoMade`, `#field-isSupply`), případně přes asociované `<label>`.

---

## 2. Přehled prvků objevujících se až po akci

| Prvek | Podmínka zobrazení | Selektor |
|---|---|---|
| **Sekce Digital files** | Výběr digitální kategorie | `#field-digitalFiles` |
| **Input pro digitální soubory** | Výběr digitální kategorie | `#field-digitalFiles input[type='file']` |
| **Tlačítko Add file** | Výběr digitální kategorie | `#field-digitalFiles button:has-text('Add file')` |
| **Dotaz na AI tvorbu** | Výběr digitální kategorie | `input[name='whatContent'][value='ai_gen']` |
| **Návrhy kategorií** | Zápis textu do vyhledávače kategorií | `.le-category-search__results li` |
| **Potvrzení publikace** | Kliknutí na primární tlačítko Publish | `#confirmPublishOverlay__container` |
| **Upozornění při ukládání** | Ukládání inzerátu bez fotek apod. | `#listing_warnings_overlay_container` |

---

## 3. Křehkost selektorů a doporučení pro údržbu

1. **Fotografie vs. Digitální soubory:**
   - `input[type='file']` pro fotografie se nachází v `.le-video-multiple-upload-area`.
   - `input[type='file']` pro digitální soubory se nachází uvnitř `#field-digitalFiles`.
   - Vždy je nutné selektovat file input v kontextu příslušného obalujícího kontejneru, nikoli globálně.

2. **Tlačítko Publish:**
   - Na stránce se nachází více tlačítek s textem `Publish` (jedno v dolní liště, druhé v potvrzovacím dialogu).
   - Pro primární kliknutí je nejstabilnější selektor `button[data-testid='publish']`.
   - Pro potvrzení v dialogu je nutné cílit na `#confirmPublishOverlay__container button#shop-manager--listing-publish`.

3. **Chybové hlášky formuláře:**
   - Etsy kombinuje zprávy třídy `.wt-validation__message` u jednotlivých polí s obecnými informačními a stavovými hláškami v `div[role='alert']` a `.wt-alert`.

---

Výsledný strojově čitelný soubor se selektory: `selectors_found.json`
