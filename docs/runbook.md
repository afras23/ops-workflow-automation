# Runbook — Ops Workflow Automation

## Table of Contents

1. [Health Checks](#health-checks)
2. [Common Failure Modes](#common-failure-modes)
3. [Adding New Extraction Fields](#adding-new-extraction-fields)
4. [Updating Prompt Versions](#updating-prompt-versions)
5. [Monitoring and Alerting](#monitoring-and-alerting)
6. [Operational Procedures](#operational-procedures)

---

## Health Checks

### Liveness

```bash
curl -s http://localhost:8000/api/v1/health | jq .
```

Expected response:
```json
{"status": "ok", "timestamp": "2026-03-22T10:00:00+00:00"}
```

Returns `200 OK` if the process is running. Does not check dependencies.

### Readiness

```bash
curl -s http://localhost:8000/api/v1/health/ready | jq .
```

Expected response:
```json
{"status": "ready", "database": "ok", "timestamp": "2026-03-22T10:00:00+00:00"}
```

Returns `200 OK` only if the database is reachable. Returns `503` if the database is down. Use this for load balancer health checks.

### Metrics

```bash
curl -s http://localhost:8000/api/v1/metrics | jq .
```

Returns item counts by status, total AI call count, total cost today, and average confidence. Use this for dashboard queries.

---

## Common Failure Modes

### HTTP 422 — Extraction failed (AI returned non-JSON)

**Symptom:** `POST /api/v1/ingest` returns 422 with `"detail": "... non-JSON response ..."`.

**Cause:** The AI provider returned a response that could not be parsed as JSON — either a refusal ("I'm sorry, I can't help with that"), a prose explanation, or a truncated response.

**Recovery:**
1. Check the `llm_call_log` table for the failed call: `SELECT * FROM llm_call_log ORDER BY created_at DESC LIMIT 5;`
2. If the AI provider is returning errors consistently, check the provider status page.
3. If the input email contains unusual content (very long body, non-UTF-8 characters), the extraction prompt may need updating — see [Updating Prompt Versions](#updating-prompt-versions).
4. The caller should retry with the same `message_id`. The idempotency layer will not block retries on failed items.

### HTTP 429 — Daily cost limit reached

**Symptom:** `POST /api/v1/ingest` returns 429 with `"error_code": "cost_limit_exceeded"`.

**Cause:** The system has spent more than `MAX_DAILY_COST_USD` (default: $10) on AI calls today.

**Recovery:**
1. Review `GET /api/v1/metrics` to see today's total cost.
2. If the limit is being hit regularly, increase `MAX_DAILY_COST_USD` in the environment or investigate whether unexpected high-volume ingestion is occurring.
3. The cost resets at midnight UTC. Requests will succeed again after the reset.

### HTTP 500 — Database write failed

**Symptom:** `POST /api/v1/ingest` returns 500.

**Cause:** The database is unreachable, the disk is full, or there is a schema mismatch (migration not run).

**Recovery:**
1. Check `GET /api/v1/health/ready` — if it returns 503, the database is down.
2. If using Docker: `docker-compose ps` to check container status; `docker-compose logs db` for Postgres errors.
3. If the migration has not been run: `alembic upgrade head` (or inside the container: `docker exec <app-container> alembic upgrade head`).
4. Check disk usage: `df -h /data` (or wherever the SQLite file is stored).

### Circuit breaker open — AI calls failing

**Symptom:** Logs show `RetryableError: Circuit breaker open` repeatedly. Extractions fail with 503 or 500.

**Cause:** The AI provider has failed 5+ times in the last 60 seconds. The circuit breaker is open to prevent cascading failures.

**Recovery:**
1. The circuit breaker resets automatically after the 60-second window with no new failures.
2. Check the AI provider status page.
3. If the provider is down for an extended period, set `AI_PROVIDER=mock` temporarily — the mock client will classify emails using keyword matching and the system will continue processing without making real AI calls. Note that classification accuracy will be lower.

### Items stuck in `pending_review`

**Symptom:** `GET /api/v1/items?status=pending_review` returns a growing list with no items being processed.

**Cause:** No one is reviewing. This is expected behaviour — the review queue requires human action.

**Resolution:**
1. List pending items: `curl -s http://localhost:8000/api/v1/items?status=pending_review | jq '.[] | {item_id, request_type, confidence, review_reasons}'`
2. Approve an item: `curl -s -X POST http://localhost:8000/api/v1/items/<ITEM_ID>/review -H "Content-Type: application/json" -d '{"reviewer": "your-name", "action": "approve", "reason": "Verified all fields"}'`
3. Reject an item: same endpoint with `"action": "reject"`.

---

## Adding New Extraction Fields

To add a new field (e.g. `due_date`) to the extraction output:

1. **Add to the Pydantic model** — update `app/models/email.py`, adding the field to `Extraction` with `Optional[...]` and a default of `None`.

2. **Update the prompt** — edit `app/services/ai/prompts.py`. Add the new field to the JSON schema section of the system prompt. Increment `VERSION` (e.g. `email_extraction_v1` → `email_extraction_v2`).

3. **Update the database schema** — create a new Alembic migration:
   ```bash
   alembic revision --autogenerate -m "add due_date to items"
   # Review the generated file, then:
   alembic upgrade head
   ```
   The migration should use `op.execute("ALTER TABLE items ADD COLUMN due_date TEXT")`.

4. **Update the Storage layer** — edit `app/repositories/storage.py` to include the new field in `create_item` and `get_item` SQL.

5. **Update ConfidenceScorer** (if relevant) — if the new field should affect completeness scoring, add it to the relevant type's expected field list in `app/services/confidence_scorer.py`.

6. **Add test cases** — add parametrized test cases to `tests/unit/test_extraction_parametrized.py` covering the new field being present and absent.

7. **Update eval test set** — add test cases to `eval/test_set.jsonl` with `expected.due_date` assertions, then re-run `make evaluate`.

---

## Updating Prompt Versions

The extraction prompt is in `app/services/ai/prompts.py`. The `VERSION` constant is logged with every LLM call and included in evaluation reports.

**To update the prompt:**

1. Edit the `EXTRACTION_SYSTEM_PROMPT` or `build_extraction_prompt()` function.
2. Increment `VERSION`: e.g. `email_extraction_v1` → `email_extraction_v2`.
3. Run the evaluation pipeline to measure the impact:
   ```bash
   AI_PROVIDER=anthropic ANTHROPIC_API_KEY=sk-... make evaluate
   ```
4. Compare the new `eval/results/eval_YYYY-MM-DD.json` against the previous run.
5. If accuracy improves or stays the same, commit the change. If it regresses, investigate before deploying.

**Versioning rationale:** The `prompt_version` field in `llm_call_log` allows you to correlate classification quality with prompt changes in production. If a prompt update causes unexpected misclassifications, you can identify affected items by their `prompt_version`.

---

## Monitoring and Alerting

### Key metrics to watch

| Metric | Warning threshold | Critical threshold |
|---|---|---|
| `pending_review` queue depth | > 20 items | > 100 items |
| Extraction error rate (422s) | > 5% of requests | > 20% of requests |
| Daily AI cost | > 80% of `MAX_DAILY_COST_USD` | = `MAX_DAILY_COST_USD` |
| API latency P95 | > 3s | > 10s |
| Circuit breaker trips | Any | Any sustained |

### Recommended alerts

1. **Queue depth alert** — poll `GET /api/v1/metrics` every 5 minutes; alert if `pending_review_count > 20`.
2. **Cost limit warning** — alert when daily cost reaches 80% of the limit so reviewers have time to act before requests start failing.
3. **Health check failure** — if `/api/v1/health/ready` returns non-200, page on-call immediately.
4. **High 422 rate** — if the 422 rate over any 5-minute window exceeds 10%, investigate the AI provider.

### Log structure

All logs are structured JSON with the following fields:

```json
{
  "timestamp": "2026-03-22T10:00:00.000Z",
  "level": "INFO",
  "message": "extraction completed",
  "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
  "request_type": "purchase_request",
  "confidence": 0.87,
  "model": "claude-3-5-haiku-20241022",
  "tokens_in": 450,
  "tokens_out": 120,
  "cost_usd": 0.000263,
  "latency_ms": 612.4
}
```

Filter by `correlation_id` to trace a single request across all log entries.

---

## Operational Procedures

### Restart the service

```bash
# Docker
docker-compose restart app

# Systemd
systemctl restart ops-workflow-automation
```

The service is stateless — all state is in the database. Restarts are safe at any time.

### Run migrations manually

```bash
# Local
alembic upgrade head

# Inside Docker container
docker exec ops-workflow-automation-app-1 alembic upgrade head

# Check current revision
alembic current
```

### View recent audit events

```bash
# All events for an item
curl -s http://localhost:8000/api/v1/items/<ITEM_ID>/audit | jq .

# Raw SQL (SQLite)
sqlite3 data/app.db "SELECT item_id, event_type, actor, created_at FROM audit_log ORDER BY created_at DESC LIMIT 20;"
```

### Re-run evaluation

```bash
# With mock AI (free, offline)
make evaluate

# With real Anthropic API
AI_PROVIDER=anthropic ANTHROPIC_API_KEY=sk-... python eval/evaluate.py

# Against a custom test set
python eval/evaluate.py --test-set path/to/custom_test_set.jsonl
```

### Clear the database (development only)

```bash
# SQLite — delete the file and re-run migrations
rm data/app.db
alembic upgrade head

# Docker — remove the volume
docker-compose down -v
docker-compose up --build
```
