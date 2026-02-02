# Runbook

## Local setup
1) Create venv and install deps:
- `python3 -m venv .venv`
- `source .venv/bin/activate`
- `pip install -r requirements.txt`

2) Copy env file:
- `cp .env.example .env`

3) Start API:
- `uvicorn app.main:app --reload`

## Demo flow
1) Ingest samples:
- `python app/demo_run_samples.py`

2) List pending items:
- `curl "http://127.0.0.1:8000/items?status=pending_review"`

3) Approve an item:
- `curl -X POST http://127.0.0.1:8000/items/<ITEM_ID>/review -H "Content-Type: application/json" -d '{"reviewer":"anesah","action":"approve","reason":"Verified details"}'`

4) View audit:
- `curl http://127.0.0.1:8000/items/<ITEM_ID>/audit`

## Outputs
- SQLite DB: `data/app.db`
- “Sheets” mock: `data/sheet_rows.csv`
- “Airtable/CRM” mock: `data/airtable_rows.jsonl`
- Slack: console mock unless `SLACK_WEBHOOK_URL` is set

## Operational notes
- If ingestion fails, check `/items/<ITEM_ID>` and `/items/<ITEM_ID>/audit` for error details.
