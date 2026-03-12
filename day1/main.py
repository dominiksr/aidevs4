import csv
import json
import requests
from io import StringIO
from openai import OpenAI
from pydantic import BaseModel
from typing import List

import os
from dotenv import load_dotenv

# Wczytanie zmiennych z pliku .env
load_dotenv()

# Przypisanie klucza do zmiennej w Pythonie
agent_api_key = os.getenv("AG3NTS_API_KEY")
openai_api_key = os.getenv("OPENAI_API_KEY")

# ==========================================
# KONFIGURACJA KLUCZY API
# ==========================================
AG3NTS_API_KEY = agent_api_key
OPENAI_API_KEY = openai_api_key

# Inicjalizacja klienta OpenAI
client = OpenAI(api_key=OPENAI_API_KEY)

# ==========================================
# DEFINICJA STRUKTURY DLA STRUCTURED OUTPUTS
# ==========================================
class JobTaggingResult(BaseModel):
    id: int
    tags: List[str]

class TaggingResponse(BaseModel):
    results: List[JobTaggingResult]

def main():
    print("1. Pobieranie danych z huba...")
    csv_url = f"https://hub.ag3nts.org/data/{AG3NTS_API_KEY}/people.csv"
    response = requests.get(csv_url)
    response.raise_for_status()
    
    # Przetwarzanie CSV
    csv_data = StringIO(response.text)
    reader = csv.DictReader(csv_data)
    
    print("2. Wstępne filtrowanie danych...")
    filtered_people =[]
    
    for row in reader:
        # Zakładamy standardowe nazwy kolumn na podstawie przykładu JSON i opisu
        # (Jeśli plik CSV ma inne nazwy kolumn, np. 'rok_urodzenia' zamiast 'born', 
        #  należy je tutaj odpowiednio dostosować)
        try:
            born = int(row['born'])
            age_in_2026 = 2026 - born
            city = row['city'].strip()
            gender = row['gender'].strip()
            
            # Warunki: Mężczyzna, wiek 20-40 lat w 2026 r., urodzony w Grudziądzu
            if gender == 'M' and 20 <= age_in_2026 <= 40 and city == 'Grudziądz':
                filtered_people.append({
                    "name": row['name'],
                    "surname": row['surname'],
                    "gender": gender,
                    "born": born,
                    "city": city,
                    "job": row['job']
                })
        except (ValueError, KeyError) as e:
            # Ignoruj wiersze z uszkodzonymi danymi (jeśli takie istnieją)
            continue

    print(f"   Znaleziono {len(filtered_people)} osób spełniających kryteria bazowe.")

    if not filtered_people:
        print("Brak osób spełniających kryteria! Sprawdź nazwy kolumn w pobranym pliku CSV.")
        return

    print("3. Kategoryzacja zawodów (Job Tagging) przy pomocy LLM...")
    
    # Przygotowujemy prompt dla modelu LLM - wysyłamy wszystkie znalezione zawody naraz (Batching)
    jobs_to_tag = "\n".join([f"ID: {i} | Zawód: {person['job']}" for i, person in enumerate(filtered_people)])
    
    system_prompt = """
    Jesteś asystentem klasyfikującym stanowiska pracy. 
    Twoim zadaniem jest przypisać tagi do podanej listy stanowisk.
    
    Dostępne tagi (możesz przypisać wiele do jednego stanowiska):
    - IT
    - transport
    - edukacja
    - medycyna
    - praca z ludźmi
    - praca z pojazdami
    - praca fizyczna
    
    Dla każdego stanowiska przeanalizuj jego nazwę/opis i dopasuj NAJBARDZIEJ PASUJĄCE tagi z powyższej listy.
    """

    # Wykorzystujemy nową metodę .parse() z OpenAI SDK do wymuszenia zgodności ze schematem Pydantic
    completion = client.beta.chat.completions.parse(
        model="gpt-4o-2024-08-06", # Model obsługujący zaawansowane Structured Outputs
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Oto lista zawodów do otagowania:\n{jobs_to_tag}"}
        ],
        response_format=TaggingResponse,
        temperature=0.1 # Niska temperatura dla deterministycznych wyników
    )

    tagging_results = completion.choices[0].message.parsed.results

    print("4. Końcowe filtrowanie i przygotowanie odpowiedzi...")
    final_answer =[]
    
    for result in tagging_results:
        # Sprawdzamy, czy model przypisał tag "transport"
        if "transport" in result.tags:
            # Pobieramy oryginalne dane osoby na podstawie ID
            person = filtered_people[result.id]
            
            # Formatujemy obiekt dokładnie tak, jak wymaga tego zadanie
            final_answer.append({
                "name": person["name"],
                "surname": person["surname"],
                "gender": person["gender"],
                "born": person["born"],
                "city": person["city"],
                "tags": result.tags
            })

    print(f"   Wytypowano {len(final_answer)} osób pracujących w transporcie.")

    print("5. Wysyłanie odpowiedzi do centrali...")
    payload = {
        "apikey": AG3NTS_API_KEY,
        "task": "people",
        "answer": final_answer
    }

    verify_url = "https://hub.ag3nts.org/verify"
    verify_response = requests.post(verify_url, json=payload)
    
    print("\nOdpowiedź serwera:")
    try:
        print(json.dumps(verify_response.json(), indent=2, ensure_ascii=False))
    except json.JSONDecodeError:
        print(verify_response.text)

if __name__ == "__main__":
    main()