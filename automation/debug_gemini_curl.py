import requests
import json
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

url = "https://api.geminigen.ai/uapi/v1/generate_image"

headers = {
    "x-api-key": "geminiai-eb8858d180dfe000e2dfe441ecf014f3"
}

url = "https://api.geminigen.ai/uapi/v1/generate_image"

headers = {
    "x-api-key": "geminiai-eb8858d180dfe000e2dfe441ecf014f3"
}

models = [
    "stable-diffusion-v1-5",
    "stable-diffusion-v2-1",
    "dreamshaper",
    "anything-v5",
    "absolute-reality",
    "v1",
    "standard",
    "turbo"
]

print("--- Testing Models with Form Data ---")
for m in models:
    print(f"\nModel: {m}")
    try:
        data = {
            "prompt": "A beautiful sunset",
            "model": m
        }
        # Requests automatically sets Content-Type to application/x-www-form-urlencoded
        r = requests.post(url, headers=headers, data=data, timeout=10, verify=False)
        print(f"Status: {r.status_code}")
        print(f"Body: {r.text[:200]}")
        if r.status_code == 200:
             print("🎉 SUCCESS!")
             break
    except Exception as e: print(e)
