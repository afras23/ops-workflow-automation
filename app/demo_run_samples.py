import json
import os
from pathlib import Path
import httpx

API_URL = os.getenv("API_URL", "http://127.0.0.1:8000")

def main():
    folder = Path("samples/inbox")
    files = sorted(folder.glob("*.json"))
    if not files:
        raise SystemExit("No sample files found in samples/inbox")

    for f in files:
        payload = json.loads(f.read_text(encoding="utf-8"))
        r = httpx.post(f"{API_URL}/ingest", json=payload, timeout=10)
        print(f"\n==> {f.name} {r.status_code}")
        print(r.json())

if __name__ == "__main__":
    main()
