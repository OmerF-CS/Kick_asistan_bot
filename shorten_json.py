import json
import os
import asyncio
from dotenv import load_dotenv
from google import genai

async def main():
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    client = genai.Client(api_key=api_key)
    
    file_path = "C:/Users/omerf/OneDrive/Desktop/Projeler tümü/education_app/Kick_asistan/static_commands.json"
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    prompt = """Aşağıdaki JSON verisinde anahtarlar ve değerler var. Bu bir Twitch/Kick canlı yayın botu için. 
Mevcut cevaplar (değerler) çok uzun. Lütfen her bir cevabı en fazla 1 kısa cümle, vurucu ve net olacak şekilde kısalt.
Emojileri koru veya ekle. Örnek: "Aleyküm selam, yayına hoş geldin kral! Arkana yaslan ve keyfini çıkar." -> "Aleyküm selam, hoş geldin kral! 😎"
Sadece geçerli bir JSON objesi döndür (başka hiçbir markdown veya text yazma).

JSON:
""" + json.dumps(data, ensure_ascii=False)

    print("Kısaltılıyor...")
    response = await asyncio.to_thread(
        client.models.generate_content,
        model="gemini-3.5-flash-lite",
        contents=prompt
    )
    
    text = response.text.strip()
    if text.startswith("```json"):
        text = text[7:-3].strip()
    elif text.startswith("```"):
        text = text[3:-3].strip()
        
    new_data = json.loads(text)
    
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(new_data, f, ensure_ascii=False, indent=2)
        
    print("Tamamlandı. Kısa versiyonlar kaydedildi.")

if __name__ == "__main__":
    asyncio.run(main())
