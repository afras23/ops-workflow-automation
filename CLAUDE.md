# Project Standards

You are upgrading this project to production-grade 10/10 standard.

## Code Rules (Non-Negotiable)
- Type hints on ALL function signatures and return types
- Docstrings on ALL public functions and classes (Args, Returns, Raises)
- Structured logging with logger.info/warning/error and extra={} — NEVER print()
- Pydantic models for all data crossing boundaries — NEVER raw dicts
- Async for all I/O (database, API calls, file operations)
- Specific exception handling — NEVER bare except or except Exception
- Dependency injection — NEVER create instances inside functions
- All config via environment variables with Pydantic Settings
- datetime.now(timezone.utc) — NEVER datetime.utcnow()
- Domain-specific variable names — NEVER data, result, info, item, obj
- No function exceeds 30 lines of logic
- f-strings NEVER in logger calls — use extra={} dict

## Architecture
- Routes: validate input → delegate to service → format response
- Services: business logic orchestration
- AI: client wrapper + versioned prompts + evaluation
- Repositories: data access layer
- Core: exceptions, logging, config, shared utilities

## Simplicity Constraint
- No abstraction without current usage (no BaseRepository with 10 generic methods when you need 2 specific ones)
- No generic frameworks or factory patterns unless 3+ implementations exist right now
- Every file, class, and layer must be justified by actual use in THIS project
- If a function is only called once and doesn't need to be independently testable, inline it
- Prefer explicit over clever — a junior engineer should understand every function

## Cost Constraints (AI Projects)
- All AI features must operate within realistic cost limits
- Default daily limit: $10 (configurable via MAX_DAILY_COST_USD in Settings)
- System must degrade gracefully when limit reached (refuse new requests, don't crash)
- Cost tracking must be per-request AND daily aggregate
- Every AI call logs: model, tokens_in, tokens_out, cost_usd, latency_ms

## Demoability Requirement
- The project must be demoable from a single command: docker-compose up
- Sample input data must exist in tests/fixtures/sample_inputs/
- A working demo script or endpoint must process sample data end-to-end
- README "How to Run" must work for someone with zero context in under 5 minutes

## Portfolio Consistency Rules (Same Across ALL Projects)
- Logging format: structured JSON with correlation_id in every entry
- Error structure: BaseAppError with status_code, error_code, message, context dict
- API response format: {"status": "...", "data": {...}, "metadata": {...}} or {"status": "error", "error": {...}, "metadata": {...}}
- Naming: snake_case for files/functions/variables, PascalCase for classes
- Docker: multi-stage, Python 3.12-slim, non-root user, HEALTHCHECK
- CI: ruff check + ruff format --check + mypy + pytest with real Postgres
- Makefile targets: dev, test, lint, format, typecheck, migrate, docker, clean, evaluate
- Health endpoints: /api/v1/health, /api/v1/health/ready, /api/v1/metrics
- Config: Pydantic Settings, .env.example with descriptions for every variable

## Definition of Done (MANDATORY — Check Before EVERY Commit)

Before completing ANY commit, validate against this checklist.
If ANY item is not met, list the failures explicitly and fix them before proceeding.

### Code Quality
- [ ] Type hints on all function signatures
- [ ] Docstrings on all public functions and classes
- [ ] No print() statements — structured logging only
- [ ] No bare except or except Exception
- [ ] No hardcoded config values — all from Settings
- [ ] No TODO/FIXME in committed code
- [ ] Domain-specific variable names throughout

### Architecture
- [ ] Clear separation: routes / services / models / repositories
- [ ] Dependency injection (not global imports of stateful objects)
- [ ] Pydantic models on all boundaries
- [ ] Retry with backoff on external calls
- [ ] Async where appropriate

### AI / LLM (if applicable to this commit)
- [ ] AI client wrapper with cost tracking
- [ ] Prompt templates versioned and separated from code
- [ ] Schema validation on AI outputs (Pydantic)
- [ ] Cost tracked per call (tokens + USD)

### Infrastructure (by final commit)
- [ ] Dockerfile (multi-stage, non-root, health check)
- [ ] docker-compose.yml (app + database + health checks)
- [ ] CI pipeline (ruff + mypy + pytest)
- [ ] .env.example, .gitignore, Makefile, pyproject.toml
- [ ] Alembic migrations

### Testing (by final commit)
- [ ] 40+ tests total
- [ ] Unit, integration, parameterised, error recovery, security
- [ ] All external services mocked
- [ ] make test passes

### Documentation (by final commit)
- [ ] README as case study with evaluation results
- [ ] Architecture diagram (Mermaid)
- [ ] 3+ ADRs in docs/decisions/
- [ ] Runbook in docs/runbook.md
- [ ] Sample data in tests/fixtures/sample_inputs/

## Testing: 40+ tests per project
## Infrastructure: Docker (multi-stage, non-root, health check), CI, Makefile, Alembic
## Git: 20+ commits, format: <type>: <description>