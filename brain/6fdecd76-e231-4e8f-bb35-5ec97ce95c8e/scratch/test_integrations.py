import os
import sys
from pathlib import Path

# Add backend to path
sys.path.append(str(Path("d:/projects/GOOGLE-PROJECT").absolute()))

from backend.core.integration_manager.integration_store import integration_store
from dotenv import load_dotenv

load_dotenv("d:/projects/GOOGLE-PROJECT/backend/.env")

def test():
    user_id = "default"
    connected = integration_store.get_user_integrations(user_id)
    print(f"Connected integrations: {[c['service'] for c in connected]}")
    for c in connected:
        print(f" - {c['service']}: {c.get('note', 'no note')}")

if __name__ == "__main__":
    test()
