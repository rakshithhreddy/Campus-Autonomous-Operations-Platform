import base64
import json
import urllib.request

mermaid_code = """
graph TD
    classDef user fill:#ffecb3,stroke:#ffb300,stroke-width:2px,color:#000;
    classDef frontend fill:#bbdefb,stroke:#1e88e5,stroke-width:2px,color:#000;
    classDef backend fill:#c8e6c9,stroke:#43a047,stroke-width:2px,color:#000;
    classDef engine fill:#e1bee7,stroke:#8e24aa,stroke-width:2px,color:#000;
    classDef storage fill:#ffccbc,stroke:#e53935,stroke-width:2px,color:#000;

    User(( User )):::user

    subgraph "Frontend (React + Vite)"
        UI["Chat Workspace"]:::frontend
        Sidebar["Task Panel"]:::frontend
    end

    subgraph "Backend API (FastAPI)"
        Security["Rate Limits & IP Blocks"]:::backend
        Router["API Router"]:::backend
    end

    subgraph "AI Core & Task Engine"
        Orchestrator["Task Orchestrator"]:::engine
        Brain["AI Brain"]:::engine
    end

    subgraph "Memory & Data"
        Session["Session Memory"]:::storage
        DB[("Database")]:::storage
    end

    User -- "1. Sends Prompt" --> UI
    UI -- "2. API Call" --> Security
    Security -- "3. Validated" --> Router
    Router -- "4. Routes Request" --> Orchestrator
    Orchestrator -- "5. Checks Context" --> Session
    Orchestrator -- "6. Processes Steps" --> Brain
    Brain -. "7. AI Processing" .-> Brain
    Brain -- "8. AI Response" --> Orchestrator
    Orchestrator -- "9. Saves State" --> DB
    Orchestrator -- "10. Task ID + Text" --> Router
    Router -- "11. Updates UI" --> UI
    UI -- "12. Adds Task" --> Sidebar
    Sidebar -. "13. User clicks Iterate" .-> User
"""

state = {
    "code": mermaid_code,
    "mermaid": {"theme": "default"}
}

json_str = json.dumps(state)
b64_str = base64.b64encode(json_str.encode('utf-8')).decode('utf-8')

url = f"https://mermaid.ink/img/{b64_str}"

try:
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req) as response, open('D:\\GOOGLE PROJECT\\Architecture_Diagram.png', 'wb') as out_file:
        out_file.write(response.read())
    print("SUCCESS")
except Exception as e:
    print(f"FAILED: {e}")
