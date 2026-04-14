#!/usr/bin/env python
"""
Startup script with error handling for debugging
"""
import sys
import traceback

def main():
    try:
        import uvicorn
        print("Starting backend...", flush=True)
        
        # Import app
        from backend.main import app
        print("Backend imported successfully", flush=True)
        
        # Get port
        # Default to 8000 for local dev; hosting providers will set PORT.
        import os
        port = int(os.environ.get("PORT", 8000))
        print(f"Starting on port {port}", flush=True)
        
        # Run server
        uvicorn.run(app, host="0.0.0.0", port=port)
        
    except Exception as e:
        print(f"STARTUP ERROR: {e}", file=sys.stderr, flush=True)
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
