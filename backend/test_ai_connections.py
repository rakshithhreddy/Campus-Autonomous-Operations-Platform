import asyncio
import httpx
import os
import json
from dotenv import load_dotenv
from pathlib import Path

# Load env
load_dotenv(dotenv_path=Path('backend/.env'), override=True)

async def test_provider(name, url, key, model, payload_gen):
    print(f"\n--- Testing {name} ---")
    print(f"URL: {url}")
    print(f"Model: {model}")
    
    if not key and name != "Ollama":
        print(f"Result: [FAIL] Key not set")
        return False
    
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    
    payload = payload_gen(model)
    
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            print(f"Status Code: {resp.status_code}")
            if resp.status_code == 200:
                data = resp.json()
                content = ""
                if name == "Ollama":
                    content = data.get("message", {}).get("content", "")
                else:
                    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                
                if content:
                    print(f"Result: [OK] Working! Response: {content[:50].strip()}...")
                    return True
                else:
                    print(f"Result: [WARN] Connected but empty response. Data: {data}")
                    return False
            else:
                print(f"Result: [FAIL] Failed. Status: {resp.status_code}. Error: {resp.text[:200]}")
                return False
    except Exception as e:
        print(f"Result: [ERROR] Exception: {str(e)}")
        return False

def openai_payload(model):
    return {
        "model": model,
        "messages": [{"role": "user", "content": "Say 'Provider Working'"}],
        "max_tokens": 10
    }

def ollama_payload(model):
    return {
        "model": model,
        "messages": [{"role": "user", "content": "Say 'Provider Working'"}],
        "stream": False
    }

async def main():
    results = {}
    
    # 1. Kimi
    results["Kimi"] = await test_provider(
        "Kimi", 
        "https://api.moonshot.ai/v1/chat/completions", 
        os.getenv("KIMI_API_KEY"), 
        os.getenv("KIMI_MODEL", "moonshot-v1-8k"),
        openai_payload
    )
    
    # 2. OpenAI
    results["OpenAI"] = await test_provider(
        "OpenAI", 
        "https://api.openai.com/v1/chat/completions", 
        os.getenv("OPENAI_API_KEY"), 
        os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        openai_payload
    )
    
    # 3. Ollama
    ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    results["Ollama"] = await test_provider(
        "Ollama", 
        f"{ollama_url}/api/chat", 
        None, 
        os.getenv("OLLAMA_MODEL", "llama3.1:8b"),
        ollama_payload
    )

    print("\n" + "="*30)
    print("FINAL STATUS REPORT:")
    for p, status in results.items():
        print(f"{p}: {'[OK] WORKING' if status else '[FAIL] FAILED'}")
    print("="*30)

if __name__ == "__main__":
    asyncio.run(main())
