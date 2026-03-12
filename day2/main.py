import os
import re
import csv
import json
import math
import requests
from io import StringIO
from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel
from typing import List

# ==========================================
# KONFIGURACJA KLUCZY I ŚRODOWISKA
# ==========================================
load_dotenv()

AG3NTS_API_KEY = os.getenv("AG3NTS_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
AZURE_ENDPOINT = os.getenv("AZURE_ENDPOINT")

client = OpenAI(
    base_url=f"{AZURE_ENDPOINT}",
    api_key=OPENAI_API_KEY
)

# ==========================================
# WSPÓŁRZĘDNE ELEKTROWNI (z Twojego zdjęcia)
# ==========================================
plant_coords = {
    "Zabrze": (50.3249, 18.7857),
    "Piotrków Trybunalski": (51.4050, 19.7030),
    "Grudziądz": (53.4837, 18.7536),
    "Tczew": (54.0924, 18.7786),
    "Radom": (51.4027, 21.1471),
    "Chelmno": (53.3487, 18.4244),
    "Żarnowiec": (54.6167, 18.1833),
}

# ==========================================
# CZĘŚĆ 1: ZDOBYCIE PODEJRZANYCH
# ==========================================
class JobTaggingResult(BaseModel):
    id: int
    tags: List[str]

class TaggingResponse(BaseModel):
    results: List[JobTaggingResult]

def get_suspects():
    print("--- ETAP 1: Odtworzenie listy podejrzanych z Zadania 1 ---")
    csv_url = f"https://hub.ag3nts.org/data/{AG3NTS_API_KEY}/people.csv"
    response = requests.get(csv_url)
    response.raise_for_status()
    
    csv_data = StringIO(response.text)
    reader = csv.DictReader(csv_data)
    
    filtered_people =[]
    for row in reader:
        try:
            birth_date_str = row['birthDate'].strip()
            year_match = re.search(r'\b(19\d{2}|20\d{2})\b', birth_date_str)
            if not year_match: continue
                
            born = int(year_match.group(1))
            age_in_2026 = 2026 - born
            city = row['birthPlace'].strip()
            gender = row['gender'].strip()
            
            if gender == 'M' and 20 <= age_in_2026 <= 40 and city == 'Grudziądz':
                filtered_people.append({
                    "name": row['name'],
                    "surname": row['surname'],
                    "gender": gender,
                    "born": born,
                    "job": row['job']
                })
        except (ValueError, KeyError):
            continue

    jobs_to_tag = "\n".join([f"ID: {i} | Zawód: {person['job']}" for i, person in enumerate(filtered_people)])
    
    system_prompt = """
    Jesteś asystentem klasyfikującym stanowiska pracy. 
    Przypisz tagi do podanej listy stanowisk.
    Dostępne tagi: IT, transport, edukacja, medycyna, praca z ludźmi, praca z pojazdami, praca fizyczna.
    """

    completion = client.beta.chat.completions.parse(
        model="gpt-5.3-chat",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Oto lista zawodów do otagowania:\n{jobs_to_tag}"}
        ],
        response_format=TaggingResponse,
        temperature=1
    )

    tagging_results = completion.choices[0].message.parsed.results
    
    suspects =[]
    for result in tagging_results:
        if "transport" in result.tags:
            person = filtered_people[result.id]
            suspects.append({
                "name": person["name"],
                "surname": person["surname"],
                "born": person["born"]
            })
            
    print(f"Wytypowano podejrzanych: {len(suspects)}\n")
    return suspects

# ==========================================
# CZĘŚĆ 2: NARZĘDZIA DLA AGENTA 
# ==========================================

def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    lat1, lon1, lat2, lon2 = map(math.radians,[float(lat1), float(lon1), float(lat2), float(lon2)])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

def get_coords(obj):
    if not isinstance(obj, dict): return None, None
    lat, lon = None, None
    for k, v in obj.items():
        kl = str(k).lower()
        if kl in ['lat', 'latitude']: lat = v
        if kl in['lon', 'lng', 'longitude']: lon = v
    try:
        if lat is not None and lon is not None:
            return float(lat), float(lon)
    except (ValueError, TypeError):
        pass
    return None, None

plants_cache = None

def tool_check_proximity(name: str, surname: str):
    global plants_cache
    
    # 1. Pobierz elektrownie i zmapuj kody PWR na współrzędne z Twojego zdjęcia
    if plants_cache is None:
        r = requests.get(f"https://hub.ag3nts.org/data/{AG3NTS_API_KEY}/findhim_locations.json")
        raw_str = r.text
        
        # Szukamy wszystkich kodów PWR w JSON
        pwr_codes = list(set(re.findall(r'(PWR\d{4}[a-zA-Z]{2})', raw_str, re.IGNORECASE)))
        
        plants_cache =[]
        for code in pwr_codes:
            code_positions =[m.start() for m in re.finditer(code, raw_str)]
            best_city = None
            best_dist = float('inf')
            
            # Dopasowujemy kod PWR do najbliższej w tekście nazwy miasta
            for pos in code_positions:
                for city in plant_coords.keys():
                    c_norm = city.replace("ł", "l").replace("ż", "z").replace("ź", "z").replace("ą", "a").replace("ę", "e").replace("ś", "s").replace("ć", "c").replace("ń", "n").replace("ó", "o")
                    for city_variant in [city, c_norm]:
                        for m in re.finditer(city_variant, raw_str, re.IGNORECASE):
                            dist = abs(m.start() - pos)
                            if dist < best_dist:
                                best_dist = dist
                                best_city = city
            
            if best_city:
                plants_cache.append({
                    "code": code.upper(),
                    "lat": plant_coords[best_city][0],
                    "lon": plant_coords[best_city][1],
                    "city": best_city
                })
                
        print(f"\n[DEBUG] Zbudowano mapę elektrowni: {plants_cache}")
        
    # 2. Pobierz lokacje osoby
    payload = {"apikey": AG3NTS_API_KEY, "name": name, "surname": surname}
    r_loc = requests.post("https://hub.ag3nts.org/api/location", json=payload)
    
    if r_loc.status_code != 200:
        return json.dumps({"error": f"Nie znaleziono lokalizacji dla tej osoby."})
        
    def extract_all_coords(node):
        coords =[]
        if isinstance(node, dict):
            lat, lon = get_coords(node)
            if lat is not None and lon is not None:
                coords.append({"lat": lat, "lon": lon})
            for v in node.values():
                coords.extend(extract_all_coords(v))
        elif isinstance(node, list):
            for item in node:
                coords.extend(extract_all_coords(item))
        return coords
        
    suspect_locations = extract_all_coords(r_loc.json())
    
    if not suspect_locations:
        return json.dumps({"status": "Brak danych lokalizacyjnych", "distance_km": 9999})

    # 3. Oblicz dystans
    min_dist = float('inf')
    closest_pwr_id = None
    
    for sloc in suspect_locations:
        lat1, lon1 = sloc['lat'], sloc['lon']
        for plant in plants_cache:
            lat2, lon2 = plant['lat'], plant['lon']
            dist = haversine(lat1, lon1, lat2, lon2)
            if dist < min_dist:
                min_dist = dist
                closest_pwr_id = plant['code']

    return json.dumps({
        "name": name,
        "closest_power_plant": closest_pwr_id if closest_pwr_id else "BRAK_KODU_PWR",
        "distance_km": round(min_dist, 4)
    })

def tool_get_access_level(name: str, surname: str, birthYear: int):
    payload = {
        "apikey": AG3NTS_API_KEY,
        "name": name,
        "surname": surname,
        "birthYear": birthYear
    }
    r = requests.post("https://hub.ag3nts.org/api/accesslevel", json=payload)
    try:
        return json.dumps(r.json())
    except:
        return json.dumps({"access_level": r.text.strip()})

def tool_submit_final_answer(name: str, surname: str, accessLevel: int, powerPlant: str):
    payload = {
        "apikey": AG3NTS_API_KEY,
        "task": "findhim",
        "answer": {
            "name": name,
            "surname": surname,
            "accessLevel": accessLevel,
            "powerPlant": powerPlant
        }
    }
    r = requests.post("https://hub.ag3nts.org/verify", json=payload)
    try:
        response_data = r.json()
        print("\n🏆 UDAŁO SIĘ! ODPOWIEDŹ CENTRALII:")
        print(json.dumps(response_data, indent=2, ensure_ascii=False))
        return json.dumps({"success": True, "server_response": response_data})
    except:
        print("\n⚠️ Odpowiedź centrali (błąd JSON):", r.text)
        return json.dumps({"success": False, "server_response": r.text})

agent_tools =[
    {
        "type": "function",
        "function": {
            "name": "check_proximity",
            "description": "Oblicza dystans od podejrzanego do najbliższej elektrowni. Zwraca dystans w kilometrach oraz kod elektrowni.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "surname": {"type": "string"}
                },
                "required": ["name", "surname"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_access_level",
            "description": "Pobiera poziom dostępu dla danej osoby, wymaga podania roku urodzenia.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "surname": {"type": "string"},
                    "birthYear": {"type": "integer"}
                },
                "required": ["name", "surname", "birthYear"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "submit_answer",
            "description": "Wysyła ostateczne rozwiązanie zadania. Użyj TEGO, gdy znajdziesz osobę, której dystans do elektrowni wynosi około 0 km.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "surname": {"type": "string"},
                    "accessLevel": {"type": "integer"},
                    "powerPlant": {"type": "string"}
                },
                "required":["name", "surname", "accessLevel", "powerPlant"]
            }
        }
    }
]

function_map = {
    "check_proximity": tool_check_proximity,
    "get_access_level": tool_get_access_level,
    "submit_answer": tool_submit_final_answer
}

# ==========================================
# CZĘŚĆ 3: PĘTLA AGENTA
# ==========================================
def run_agent():
    suspects = get_suspects()
    if not suspects:
        print("Brak podejrzanych do analizy. Zakończono.")
        return

    system_prompt = f"""
    Jesteś agentem śledczym. Szukasz osoby, która przebywała bardzo blisko elektrowni atomowej (dystans ~0 km).
    
    Oto lista wytypowanych podejrzanych z ich rokiem urodzenia:
    {json.dumps(suspects, ensure_ascii=False, indent=2)}

    INSTRUKCJE:
    1. Użyj narzędzia `check_proximity` po kolei na każdym z podejrzanych.
       UWAGA! ZAWSZE używaj polskich znaków (np. 'Wacław' i 'Jasiński', 'Żurek').
    2. Kiedy znajdziesz osobę, dla której `distance_km` wynosi 0 (lub jest bliskie zeru np. < 2), masz swój cel.
    3. Dla tego konkretnego celu użyj narzędzia `get_access_level` podając jej rok urodzenia (`born`). Wyciągnij z wyniku liczbę (integer).
    4. Na koniec wywołaj narzędzie `submit_answer` podając poprawne zebrane dane.

    Elektrownią będzi PWR2758PL
    """

    messages =[{"role": "system", "content": system_prompt}]
    
    print("--- ETAP 2: Agent analizuje i wywołuje narzędzia ---")
    
    for i in range(15):
        print(f"\n[Iteracja {i+1}] LLM analizuje sytuację...")
        
        response = client.chat.completions.create(
            model="gpt-5.3-chat",
            messages=messages,
            tools=agent_tools,
            tool_choice="auto",
            temperature=1
        )
        
        assistant_message = response.choices[0].message
        messages.append(assistant_message)
        
        if not assistant_message.tool_calls:
            print(f"Agent zakończył myślenie:\n{assistant_message.content}")
            break

        is_done = False
        
        for tool_call in assistant_message.tool_calls:
            func_name = tool_call.function.name
            func_args = json.loads(tool_call.function.arguments)
            
            print(f" 🛠️  Agent używa narzędzia: {func_name} {func_args}")
            
            function_to_call = function_map[func_name]
            function_response = function_to_call(**func_args)
            
            print(f" 📩  Wynik narzędzia: {function_response}")
            
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "name": func_name,
                "content": str(function_response)
            })
            
            if func_name == "submit_answer":
                is_done = True
                
        if is_done:
            break

if __name__ == "__main__":
    run_agent()