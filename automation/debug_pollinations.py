import os
import requests
import time
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("POLLINATIONS_API_KEY")
if not api_key:
    raise ValueError("POLLINATIONS_API_KEY není nastaven v .env ani proměnných prostředí.")

prompt = "A futuristic stork robot delivering a package, detailed, 8k, flux style"
url = f"https://gen.pollinations.ai/image/{prompt}"

headers = {
    "Authorization": f"Bearer {api_key}"
}

params = {
    "model": "flux",
    "width": 1024,
    "height": 1024,
    "seed": 42
}

print(f"Generuji obrazek pres Pollinations.ai (Flux)...")
print(f"URL: {url}")

try:
    start_time = time.time()
    response = requests.get(url, headers=headers, params=params, timeout=60)
    
    print(f"Status Code: {response.status_code}")
    
    if response.status_code == 200:
        with open("pollinations_test.jpg", "wb") as f:
            f.write(response.content)
        print(f"Obrázek uložen jako 'pollinations_test.jpg'")
        print(f"Cas: {time.time() - start_time:.2f}s")
    else:
        print(f"Chyba: {response.text[:500]}")

except Exception as e:
    print(f"❌ Exception: {e}")
