import os  
import re  
import requests  
from openai import OpenAI  
from dotenv import load_dotenv  
  
load_dotenv()  
  
AG3NTS_API_KEY = os.getenv("AG3NTS_API_KEY")  
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")  
AZURE_ENDPOINT = os.getenv("AZURE_ENDPOINT")  
  
BASE_DOC_URL = "https://hub.ag3nts.org/dane/doc/"  
  
client = OpenAI(  
    base_url=AZURE_ENDPOINT,  
    api_key=OPENAI_API_KEY  
)  
  
  
def fetch(url):  
    r = requests.get(url)  
    r.raise_for_status()  
    return r.text  
  
  
def analyze_image(url):  
  
    completion = client.chat.completions.create(  
        model="gpt-5.3-chat",  
        messages=[  
            {  
                "role": "user",  
                "content": [  
                    {"type": "text", "text": "Odczytaj dokładnie wszystkie dane z dokumentu."},  
                    {"type": "image_url", "image_url": {"url": url}}  
                ]  
            }  
        ]  
    )  
  
    return completion.choices[0].message.content  
  
  
def extract_links(text):  
  
    md_links = re.findall(r'$([^)]+)$', text)  
    include_links = re.findall(r'include file="(.*?)"', text)  
  
    return list(set(md_links + include_links))  
  
  
def collect_docs():  
  
    docs = ""  
  
    index = fetch(BASE_DOC_URL + "index.md")  
    docs += index  
  
    links = extract_links(index)  
  
    for link in links:  
  
        if not link.endswith((".md", ".png", ".jpg", ".jpeg")):  
            continue  
  
        url = BASE_DOC_URL + link  
  
        print("Pobieram:", url)  
  
        try:  
  
            if link.endswith((".png", ".jpg", ".jpeg")):  
                content = analyze_image(url)  
            else:  
                content = fetch(url)  
  
            docs += "\n\n" + content  
  
        except Exception as e:  
            print("Błąd:", url, e)  
  
    return docs  
  
  
def find_route_code(docs):  
  
    completion = client.chat.completions.create(  
        model="gpt-5.3-chat",  
        temperature=1,  
        messages=[  
            {  
                "role": "system",  
                "content": """  
Znajdź w dokumentacji kod trasy dla połączenia:  
  
Gdańsk -> Żarnowiec  
  
Zwróć TYLKO kod trasy dokładnie tak jak w dokumentacji.  
"""  
            },  
            {  
                "role": "user",  
                "content": docs  
            }  
        ]  
    )  
  
    return completion.choices[0].message.content.strip()  
  
  
def generate_declaration(docs, route_code):  
  
    shipment_data = f"""  
Nadawca: 450202122  
Punkt nadawczy: Gdańsk  
Punkt docelowy: Żarnowiec  
Waga: 2800 kg  
Budżet: 0 PP  
Zawartość: kasety z paliwem do reaktora  
Uwagi: brak  
Kod trasy: {route_code}  
"""  
  
    completion = client.chat.completions.create(  
        model="gpt-5.3-chat",  
        temperature=1,  
        messages=[  
            {  
                "role": "system",  
                "content": """  
Znajdź dokładny wzór deklaracji SPK.  
  
Skopiuj go 1:1 i wypełnij polami z danych przesyłki.  
  
Nie zmieniaj formatowania ani separatorów.  
Zwróć wyłącznie gotową deklarację.  
"""  
            },  
            {  
                "role": "user",  
                "content": f"""  
Dokumentacja:  
  
{docs}  
  
Dane:  
  
{shipment_data}  
"""  
            }  
        ]  
    )  
  
    return completion.choices[0].message.content  
  
  
def send_answer(declaration):  
  
    payload = {  
        "apikey": AG3NTS_API_KEY,  
        "task": "sendit",  
        "answer": {  
            "declaration": declaration  
        }  
    }  
  
    r = requests.post(  
        "https://hub.ag3nts.org/verify",  
        json=payload  
    )  
  
    print("\nOdpowiedź HUB:\n")  
    print(r.text)  
  
  
def main():  
  
    docs = collect_docs()  
  
    print("\nSzukam kodu trasy...\n")  
  
    route_code = find_route_code(docs)  
  
    print("Kod trasy:", route_code)  
  
    declaration = generate_declaration(docs, route_code)  
  
    print("\nDEKLARACJA:\n")  
    print(declaration)  
  
    send_answer(declaration)  
  
  
if __name__ == "__main__":  
    main()  
