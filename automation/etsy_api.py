import os
import json
import requests
from typing import Optional, Dict, Any

class EtsyClient:
    """Klient pro komunikaci s Etsy API v3."""
    
    BASE_URL = "https://openapi.etsy.com/v3"
    
    def __init__(self, api_key: str, shop_id: str, access_token: str):
        self.api_key = api_key
        self.shop_id = shop_id
        self.access_token = access_token
        self.headers = {
            "x-api-key": self.api_key,
            "Authorization": f"Bearer {self.access_token}"
        }

    def get_shop_info(self) -> Optional[Dict[Any, Any]]:
        """Získá základní informace o obchodě pro ověření spojení."""
        url = f"{self.BASE_URL}/application/shops/{self.shop_id}"
        try:
            response = requests.get(url, headers=self.headers)
            if response.status_code == 200:
                return response.json()
            else:
                print(f"❌ Chyba při získávání informací o obchodě: {response.status_code} - {response.text}")
                return None
        except Exception as e:
            print(f"❌ Výjimka při komunikaci s Etsy: {e}")
            return None

    def create_listing(self, data: Dict[str, Any]) -> Optional[str]:
        """Vytvoří nový listing jako draft.
        
        Args:
            data: Slovník s daty (quantity, title, description, price, who_made, when_made, taxonomy_id, tags)
        Returns:
            Listing ID při úspěchu, jinak None.
        """
        url = f"{self.BASE_URL}/application/shops/{self.shop_id}/listings"
        try:
            response = requests.post(url, headers=self.headers, data=data)
            if response.status_code == 201:
                listing_id = response.json().get("listing_id")
                print(f"✅ Listing vytvořen! ID: {listing_id}")
                return listing_id
            else:
                print(f"❌ Chyba při vytváření listingu: {response.status_code} - {response.text}")
                return None
        except Exception as e:
            print(f"❌ Výjimka při vytváření listingu: {e}")
            return None

    def upload_listing_image(self, listing_id: str, image_path: str, rank: int = 1) -> bool:
        """Nahraje obrázek k existujícímu listingu.
        
        Args:
            listing_id: ID listingu
            image_path: Cesta k souboru s obrázkem
            rank: Pořadí obrázku (1 je hlavní)
        """
        url = f"{self.BASE_URL}/application/shops/{self.shop_id}/listings/{listing_id}/images"
        try:
            with open(image_path, 'rb') as img_file:
                files = {'image': img_file}
                data = {'rank': rank}
                response = requests.post(url, headers=self.headers, files=files, data=data)
                
            if response.status_code == 201:
                print(f"✅ Obrázek {os.path.basename(image_path)} nahrán.")
                return True
            else:
                print(f"❌ Chyba při nahrávání obrázku: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            print(f"❌ Výjimka při nahrávání obrázku: {e}")
            return False

if __name__ == "__main__":
    # Testovací kód (pokud jsou dostupné environment proměnné)
    from dotenv import load_dotenv
    load_dotenv()
    
    api_key = os.getenv("ETSY_API_KEY")
    shop_id = os.getenv("ETSY_SHOP_ID")
    access_token = os.getenv("ETSY_ACCESS_TOKEN")
    
    if api_key and shop_id and access_token:
        client = EtsyClient(api_key, shop_id, access_token)
        print("Provádím test spojení s Etsy...")
        info = client.get_shop_info()
        if info:
            print(f"Spojení úspěšné! Obchod: {info.get('shop_name')}")
        else:
            print("Spojení selhalo.")
    else:
        print("Chybí API klíče v .env pro testování.")
