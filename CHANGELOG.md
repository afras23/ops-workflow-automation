# Changelog

All notable changes to this project are documented here.

---

## [1.0.0] — 2026-03-22

### Added

**Core pipeline**
- `POST /api/v1/ingest` — single-email ingestion endpoint with idempotency by `message_id`
- `POST /api/v1/batch` — async batch ingestion with job tracking
- `GET /api/v1/batch/:job_id` — batch job status and result counts
- `GET /api/v1/items` — list all items with optional status filter
- `GET /api/v1/items/:id` — retrieve a single item
- `POST /api/v1/items/:id/review` — approve or reject a pending item with reviewer note
- `GET /api/v1/items/:id/audit` — full audit trail for an item

**Observability**
- `GET /api/v1/health` — liveness probe
- `GET /api/v1/health/ready` — readiness probe (checks database connection)
- `GET /api/v1/metrics` — item counts by status, cost summary, average confidence
- `CorrelationIDMiddleware` — UUID4 correlation ID on every request; reads/echoes `X-Correlation-ID` header
- Structured JSON logging with `correlation_id`, `model`, `tokens_in`, `tokens_out`, `cost_usd`, `latency_ms` on every AI call

**AI extraction**
- `ExtractionService` — LLM-based structured field extraction with Pydantic schema validation
- `AnthropicAIClient` — Anthropic Claude integration with token counting and cost tracking
- `MockAIClient` — keyword-based mock client for offline testing and evaluation
- `DailyCostTracker` — per-call and daily aggregate cost tracking; raises `CostLimitExceeded` at configurable limit
- `CircuitBreaker` — opens after 5 failures in 60 seconds; prevents cascading AI provider failures
- `_call_with_retry` — exponential backoff with configurable max attempts and base delay
- Versioned prompt templates (`email_extraction_v1`) in `app/services/ai/prompts.py`

**Confidence scoring and routing**
- `ConfidenceScorer` — composite score: completeness (40%) + type compliance (40%) + AI confidence (20%)
- `RoutingService` — three-tier routing: auto_approve (>0.85), pending_review (0.50–0.85), auto_reject (<0.50)
- Review reasons: human-readable strings explaining why an item was sent to review

**Infrastructure**
- Multi-stage Dockerfile (python:3.12-slim, non-root `appuser`, HEALTHCHECK)
- `docker-compose.yml` with Postgres 16 service and health checks
- GitHub Actions CI: ruff + mypy + pytest against Postgres
- Alembic migrations for SQLite and Postgres (`CREATE TABLE IF NOT EXISTS` pattern)
- Makefile targets: dev, test, lint, format, typecheck, migrate, docker, evaluate, clean
- `.env.example` with descriptions for every variable
- Pydantic Settings with full environment variable support

**Testing**
- 144 tests across unit, integration, parametrized, error recovery, idempotency, security, and performance categories
- `tests/unit/test_extraction_parametrized.py` — 16 parametrized extraction tests
- `tests/integration/test_pipeline.py` — end-to-end pipeline tests with audit trail verification
- `tests/integration/test_error_recovery.py` — retry, circuit breaker, and storage failure tests
- `tests/integration/test_idempotency.py` — single-message and batch deduplication tests
- `tests/integration/test_security.py` — prompt injection and HTML injection resistance tests
- `tests/integration/test_performance.py` — latency budget tests with mock AI

**Evaluation pipeline**
- `eval/test_set.jsonl` — 32 labelled test cases across 6 categories (standard, partial_info, edge_case, multi_format, adversarial, empty_malformed)
- `eval/evaluate.py` — async evaluation runner; outputs `eval/results/eval_YYYY-MM-DD.json`
- `make evaluate` — runs evaluation and prints summary to stdout

**Documentation**
- `README.md` — case study format with architecture diagram, evaluation results, and how-to-run
- `docs/architecture.md` — detailed system diagram with sequence flow, data model, and deployment
- `docs/decisions/001-llm-provider-selection.md` — ADR for Anthropic Claude selection
- `docs/decisions/002-confidence-scoring-approach.md` — ADR for composite confidence scoring
- `docs/decisions/003-data-storage-strategy.md` — ADR for SQLite/Postgres dual-mode strategy
- `docs/runbook.md` — health checks, failure modes, operational procedures, monitoring
- `docs/problem-definition.md` — business context and success criteria
- Sample inputs in `tests/fixtures/sample_inputs/`

---

## Initial commits

| Commit | Description |
|---|---|
| `c01d5a6` | test: add extraction, routing, and workflow test coverage |
| `9707597` | infra: add Docker setup and CI pipeline |
| `88c594f` | chore: update configuration and dependencies |
| `b4b7032` | chore: add prompt templates for AI interactions |
| `350fc78` | chore: remove CI workflow temporarily |
