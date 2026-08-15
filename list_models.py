import asyncio
import os
from dotenv import load_dotenv
from google import genai

async def main():
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("API Key not found.")
        return
    
    client = genai.Client(api_key=api_key)
    try:
        models = client.models.list()
        for m in models:
            print(f"Model: {m.name}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
