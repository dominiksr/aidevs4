import requests
import os
from dotenv import load_dotenv

load_dotenv()

# Skonfiguruj poniższe:
TWOJ_URL = "https://udddddddddlink"  # np. "https://asdfg-123.a.pinggy.io"
AG3NTS_API_KEY = os.getenv("AG3NTS_API_KEY")

payload = {
    "apikey": AG3NTS_API_KEY,
    "task": "proxy",
    "answer": {
        "url": TWOJ_URL,
        "sessionID": "sesja_testowa_123"
    }
}

print("Zgłaszam zadanie 'proxy' do weryfikacji...")
verify_url = "https://hub.ag3nts.org/verify"
verify_response = requests.post(verify_url, json=payload)

try:
    print("Odpowiedź centrali:")
    print(verify_response.json())
except Exception:
    print(verify_response.text)