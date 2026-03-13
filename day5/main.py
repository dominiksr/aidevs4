import os
import time
import json
import requests
from openai import OpenAI
from dotenv import load_dotenv

# Wczytanie zmiennych środowiskowych
load_dotenv()

AG3NTS_API_KEY = os.getenv("AG3NTS_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
AZURE_ENDPOINT = os.getenv("AZURE_ENDPOINT")

# Inicjalizacja klienta OpenAI (tak jak w Twoim przykładzie)
client = OpenAI(
    base_url=f"{AZURE_ENDPOINT}",
    api_key=OPENAI_API_KEY
)

VERIFY_URL = "https://hub.ag3nts.org/verify"

def handle_rate_limits(headers):
    """
    Funkcja analizująca nagłówki HTTP pod kątem limitów zapytań
    i usypiająca skrypt do momentu resetu.
    """
    headers_lower = {k.lower(): v for k, v in headers.items()}
    
    # Szukamy nagłówków związanych z limitami (często X-RateLimit-Reset lub Retry-After)
    reset_header = headers_lower.get('x-ratelimit-reset') or headers_lower.get('ratelimit-reset')
    retry_after = headers_lower.get('retry-after')

    sleep_time = 0

    if reset_header:
        try:
            reset_val = float(reset_header)
            # Jeśli wartość jest ogromna, to prawdopodobnie timestamp UNIX
            if reset_val > 1000000000: 
                sleep_time = max(0, reset_val - time.time())
            else:
                sleep_time = reset_val
        except ValueError:
            pass
            
    if retry_after and sleep_time == 0:
        try:
            sleep_time = float(retry_after)
        except ValueError:
            pass

    if sleep_time > 0:
        print(f"   [⏳] Wykryto limit API. Oczekiwanie {sleep_time:.2f} sekund do resetu limitu...")
        time.sleep(sleep_time + 1) # +1 sekunda marginesu błędu

def send_to_api(answer_payload):
    """
    Funkcja wysyłająca zapytanie do API, radząca sobie z błędami 503 oraz Rate Limitami.
    """
    payload = {
        "apikey": AG3NTS_API_KEY,
        "task": "railway",
        "answer": answer_payload
    }
    
    while True:
        print(f"\n[->] Wysyłanie do API: {json.dumps(answer_payload)}")
        response = requests.post(VERIFY_URL, json=payload)
        
        # 1. Obsługa Rate Limitów na podstawie nagłówków (wykonywana zawsze)
        handle_rate_limits(response.headers)
        
        # 2. Obsługa intencjonalnych błędów 503 (przeciążenie)
        if response.status_code == 503:
            print("   [!] Błąd 503: Serwer przeciążony (symulacja). Ponawiam próbę za 3 sekundy...")
            time.sleep(3)
            continue
            
        # 3. Obsługa kodu 429 Too Many Requests (jeśli nagłówki wyżej nie wystarczyły)
        if response.status_code == 429:
            print("   [!] Błąd 429: Przekroczono limit zapytań. Odczekam dodatkowe 5 sekund...")
            time.sleep(5)
            continue
            
        try:
            data = response.json()
            print(f"[<-] Odpowiedź API: {json.dumps(data, indent=2, ensure_ascii=False)}")
            return data
        except json.JSONDecodeError:
            print(f"[<-] Odpowiedź nie jest JSONem: {response.text}")
            return {"raw_text": response.text}

def main():
    print("=== Rozpoczynam zadanie RAILWAY (Autonomiczny Agent) ===\n")
    
    # 1. Startujemy od akcji 'help' zgodnie z instrukcją
    current_answer = {"action": "help"}
    
    # 2. Inicjujemy historię rozmowy z LLM
    # Definiujemy dla LLMa rolę agenta parsującego API
    messages =[
        {
            "role": "system",
            "content": (
                "Jesteś automatycznym skryptem integrującym się z nieznanym API. "
                "Twoim ostatecznym celem jest aktywowanie trasy kolejowej o nazwie 'X-01'.\n"
                "W każdej wiadomości podam Ci poprzednie zapytanie i odpowiedź serwera. "
                "Twoim zadaniem jest na tej podstawie wygenerować KOLEJNY krok - czyli obiekt JSON, "
                "który ma zostać wysłany. Zwracaj WYŁĄCZNIE CZYSTY JSON (klucze i wartości), bez znaczników markdown (np. bez ```json), "
                "ponieważ Twoja odpowiedź leci bezpośrednio do funkcji requests.post(). "
                "Uważnie czytaj instrukcje z odpowiedzi (np. z komendy help) i wykonuj je krok po kroku."
            )
        }
    ]
    
    max_steps = 15 # Zabezpieczenie przed nieskończoną pętlą
    
    for step in range(1, max_steps + 1):
        print(f"\n--- KROK {step} ---")
        
        # Wykonaj fizyczne zapytanie do API zadań
        api_response = send_to_api(current_answer)
        
        # Sprawdź, czy serwer nie zwrócił flagi w odpowiedzi
        response_str = json.dumps(api_response)
        if "FLG:" in response_str or "{{FLG:" in response_str:
            print("\n🎉 ZADANIE ZAKOŃCZONE SUKCESEM! OTO TWOJA FLAGA 🎉")
            break
            
        # Dodaj historię akcji i reakcji do kontekstu dla LLM
        messages.append({"role": "assistant", "content": json.dumps(current_answer)})
        messages.append({"role": "user", "content": f"Odpowiedź serwera:\n{response_str}"})
        
        print("   [🤖] Analizuję odpowiedź i generuję następny krok przez LLM...")
        
        # Używamy modelu GPT jako agenta analitycznego (korzystamy z JSON Object, aby wymusić format)
        completion = client.chat.completions.create(
            model="gpt-5.3-chat", # lub "gpt-4o" zależy jak zdefiniowałeś w środowisku
            messages=messages,
            temperature=1, # Zerowa temperatura = pełen determinizm (nie chcemy by wymyślał akcje)
            response_format={"type": "json_object"}
        )
        
        llm_reply = completion.choices[0].message.content.strip()
        
        try:
            # Ustawiamy odpowiedź wygenerowaną przez LLM jako argument do następnego cyklu
            current_answer = json.loads(llm_reply)
        except json.JSONDecodeError:
            print(f"   [❌] Błąd parsowania odpowiedzi od LLM: {llm_reply}")
            break

if __name__ == "__main__":
    main()