# ADR 003 — Data Storage Strategy

**Status:** Accepted
**Date:** 2026-03-10
**Author:** anesah

---

## Context

The system needs persistent storage for four entities: work items (the primary operational record), audit log entries (append-only), LLM call logs (for cost tracking and debugging), and batch job metadata. The storage layer must:

1. Work on a developer laptop with zero infrastructure setup (`docker-compose up` or plain `uvicorn app.main:app`)
2. Work in CI against a Postgres instance (GitHub Actions)
3. Support idempotency checks by `message_id` (unique constraint)
4. Support the append-only audit log pattern without complex ORMs

Options considered: SQLite only, Postgres only, SQLite for dev + Postgres for prod (via Alembic), a document store (MongoDB), and an in-memory store (for tests only).

---

## Decision

**Use SQLite for development and testing; use Postgres 16 for CI and production. Alembic manages schema migrations for both.**

The `DATABASE_URL` environment variable selects the database:
- If set: used directly (supports `postgresql://...` and `sqlite:///...`)
- If not set: falls back to `SQLITE_PATH` (defaults to `data/app.db`)

All migrations use raw SQL with `CREATE TABLE IF NOT EXISTS` so they are safe to re-run on both fresh databases and databases with pre-existing tables.

---

## Rationale

**SQLite for zero-config dev.** A developer can clone the repo, run `alembic upgrade head`, and start the API without installing or configuring any external database. SQLite is also used in all unit and integration tests via an in-memory or temp-file database, which means tests run fast and in isolation with no external dependencies.

**Postgres for CI and production.** SQLite does not support concurrent writes from multiple processes, and its type system differs from Postgres in ways that can hide bugs (e.g. date handling, text vs. integer coercion). Running CI tests against Postgres catches schema and query issues that SQLite would silently accept.

**Alembic for migrations.** The Alembic revision history is the single source of truth for the schema. Using `op.execute("CREATE TABLE IF NOT EXISTS ...")` rather than SQLAlchemy ORM operations makes each migration idempotent and avoids the `batch_alter_table` pattern that assumes prior table state.

**Raw SQL over ORM.** The repository layer uses raw SQL via `sqlite3` / `aiosqlite` rather than SQLAlchemy ORM. The data access patterns are simple (insert, select by ID, select by status, append) and do not benefit from ORM abstractions at this scale. Raw SQL is easier to audit and avoids ORM-specific N+1 patterns.

**Append-only audit log.** The `audit_log` table has no update or delete operations. Every state change creates a new row. This makes the audit trail tamper-evident within the constraints of the database and simplifies the repository interface (no update logic).

---

## Consequences

- Switching a deployment from SQLite to Postgres requires only changing `DATABASE_URL`. No code changes needed.
- The CI pipeline must start a Postgres service and run `alembic upgrade head` before tests. This adds ~15 seconds to CI time.
- SQLite does not enforce foreign key constraints by default. The repository layer does not rely on foreign key cascade behaviour; referential integrity is maintained at the application level.
- If the system is deployed with multiple replicas, SQLite is not viable — Postgres is required. This is a known limitation documented in the `.env.example` file.

---

## Alternatives Rejected

**Postgres only.** Rejected because it eliminates zero-config local development. Requiring a local Postgres instance raises the barrier for contributors and breaks the "demoable from `docker-compose up`" requirement.

**MongoDB / document store.** Rejected because the data model is relational (items have audit entries; audit entries reference items). A document store would require embedding audit history in the item document or maintaining two collections with application-level joins. The relational model is simpler and more auditable.

**In-memory store (dicts / Redis) for tests.** Rejected because it creates a divergence between the test storage layer and production. Integration tests that exercise the real `Storage` class have caught several bugs (duplicate key handling, NULL coercion, audit log ordering) that a mock would have missed.
