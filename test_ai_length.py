import asyncio
import os
from dotenv import load_dotenv
from ai_brain import AIBrain

async def main():
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("API Key not found.")
        return
    
    brain = AIBrain(api_key=api_key, bot_name="TestBot")
    resp = await brain.generate_response("TestUser", "Bana Türkiye'nin tarihini uzun uzun 5 cümleyle anlatır mısın? Neden kelimeler kesiliyor görelim.")
    print("Response:")
    print(resp)
    print("Length:", len(resp))

if __name__ == "__main__":
    asyncio.run(main())
