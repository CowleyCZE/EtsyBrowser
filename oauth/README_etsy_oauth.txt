ETSY OAUTH 2.0 + PKCE – NÁVOD

1) V Etsy Developers otevři Your Apps a zkontroluj, že má aplikace registrovanou přesně tuto Callback URL:
   http://localhost:3003/oauth/redirect

2) Ve stejné složce jako get_etsy_token.py vytvoř soubor .env zkopírováním .env.example:
   cp .env.example .env

3) Do .env doplň ETSY_SHARED_SECRET. ETSY_API_KEY je předvyplněný keystringem z původního nahraného skriptu.
   Keystring a Shared Secret jsou dvě různé hodnoty.

4) Nainstaluj závislost:
   python -m pip install -r requirements.txt

5) Spusť skript:
   python get_etsy_token.py

6) V otevřeném prohlížeči se přihlas k Etsy a autorizaci potvrď. Po návratu do terminálu
   skript uloží tokeny do etsy_tokens.json a pokusí se zjistit SHOP_ID.

BEZPEČNOST
- Nesdílej .env ani etsy_tokens.json.
- Oba soubory jsou v .gitignore. Tokenový soubor skript na POSIX systémech nastaví na práva 600.
- Pokud používáš Git, ověř, že .env a etsy_tokens.json nejsou ve verzovacím systému.
- Redirect URI musí přesně odpovídat adrese registrované u Etsy.

ROZSAH OPRÁVNĚNÍ
Výchozí ETSY_SCOPES zachovává původní nastavení: shops_r listings_r listings_w.
Pokud nepotřebuješ zapisovat nabídky, odeber listings_w. Oprávnění tokenu nelze později rozšířit pouhým refresh tokenem; pro jiné scopes je potřeba znovu autorizovat.

POŽADAVKY
Python 3.10 nebo novější.
