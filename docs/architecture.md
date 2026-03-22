# System Architecture

## Overview

The ops workflow automation system is a FastAPI service that ingests unstructured email messages, extracts structured fields via an LLM, routes items through a confidence-scored pipeline, and maintains a full audit trail. It is designed for at-least-once webhook delivery (idempotent by `message_id`) and supports both synchronous single-item ingestion and asynchronous batch processing.

---

## Full System Diagram

```mermaid
flowchart TB
    subgraph Clients
        WH["Webhook caller\n(e.g. email forwarder)"]
        OP["Ops reviewer\n(approve / reject)"]
        MON["Monitoring\n(health / metrics)"]
    end

    subgraph API["FastAPI — app/api/routes/"]
        R_INGEST["POST /api/v1/ingest"]
        R_BATCH["POST /api/v1/batch"]
        R_BATCH_STATUS["GET /api/v1/batch/:job_id"]
        R_REVIEW["POST /api/v1/items/:id/review"]
        R_ITEMS["GET /api/v1/items"]
        R_ITEM["GET /api/v1/items/:id"]
        R_AUDIT["GET /api/v1/items/:id/audit"]
        R_HEALTH["GET /api/v1/health\nGET /api/v1/health/ready"]
        R_METRICS["GET /api/v1/metrics"]
    end

    subgraph Middleware
        CID["CorrelationIDMiddleware\n(UUID4 per request;\nX-Correlation-ID header)"]
    end

    subgraph Services["app/services/"]
        WF["WorkflowService\norchestrates the pipeline"]
        EX["ExtractionService\ncalls AI client;\nvalidates JSON schema"]
        CS["ConfidenceScorer\ncompleteness 40%\ncompliance 40%\nai_confidence 20%"]
        RT["RoutingService\nauto_approve > 0.85\npending_review 0.50–0.85\nauto_reject < 0.50"]
    end

    subgraph AI["app/services/ai/"]
        AIC["AIClient protocol\n(AnthropicAIClient | MockAIClient)"]
        CB["CircuitBreaker\nfailure_threshold=5\nwindow=60s"]
        RETRY["_call_with_retry\nmax_attempts=3\nexponential backoff"]
        COST["DailyCostTracker\nper-call + daily aggregate\nMAX_DAILY_COST_USD limit"]
        PROMPT["Versioned prompt templates\napp/services/ai/prompts.py\nVERSION = email_extraction_v1"]
    end

    subgraph Storage["app/repositories/"]
        STORE["Storage\nSQLite (dev) / Postgres (prod)"]
        subgraph Tables
            T_ITEMS[(items)]
            T_AUDIT[(audit_log)]
            T_LLM[(llm_call_log)]
            T_BATCH[(batch_jobs)]
        end
    end

    WH --> CID
    OP --> CID
    MON --> CID
    CID --> R_INGEST
    CID --> R_BATCH
    CID --> R_BATCH_STATUS
    CID --> R_REVIEW
    CID --> R_ITEMS
    CID --> R_ITEM
    CID --> R_AUDIT
    CID --> R_HEALTH
    CID --> R_METRICS

    R_INGEST --> WF
    R_BATCH --> WF
    R_REVIEW --> WF

    WF -->|"check message_id"| STORE
    WF --> EX
    EX --> AIC
    AIC --> CB
    CB --> RETRY
    RETRY -->|"HTTP + cost"| COST
    EX --> PROMPT
    WF --> CS
    WF --> RT

    WF --> STORE
    STORE --> T_ITEMS
    STORE --> T_AUDIT
    STORE --> T_LLM
    STORE --> T_BATCH
```

---

## Request Flow — Single Ingest

```mermaid
sequenceDiagram
    participant Caller
    participant Middleware
    participant IngestRoute
    participant WorkflowService
    participant ExtractionService
    participant AIClient
    participant ConfidenceScorer
    participant RoutingService
    participant Storage

    Caller->>Middleware: POST /api/v1/ingest {message_id, from, subject, body}
    Middleware->>Middleware: attach correlation_id
    Middleware->>IngestRoute: forward request

    IngestRoute->>WorkflowService: ingest(message)

    WorkflowService->>Storage: find_by_message_id(message_id)
    alt duplicate
        Storage-->>WorkflowService: existing WorkItem
        WorkflowService-->>IngestRoute: idempotent_return
    else new
        WorkflowService->>ExtractionService: extract(message)
        ExtractionService->>AIClient: call(prompt)
        AIClient->>AIClient: circuit_breaker check
        AIClient->>AIClient: _call_with_retry (max 3)
        AIClient-->>ExtractionService: AICallResult {text, tokens, cost}
        ExtractionService->>ExtractionService: JSON parse + Pydantic validate
        ExtractionService-->>WorkflowService: Extraction

        WorkflowService->>ConfidenceScorer: score(extraction)
        ConfidenceScorer-->>WorkflowService: float [0.0, 1.0]

        WorkflowService->>RoutingService: route(extraction, confidence)
        RoutingService-->>WorkflowService: RoutingDecision {status, routed_to, reasons}

        WorkflowService->>Storage: create_item(WorkItem)
        WorkflowService->>Storage: append_audit(ingested event)
        Storage->>Storage: log llm_call

        WorkflowService-->>IngestRoute: WorkItem
    end

    IngestRoute-->>Caller: 200 {item_id, status, confidence, routed_to}
```

---

## Confidence Scoring

The composite confidence score is computed from three weighted components:

```
confidence = (completeness × 0.40) + (type_compliance × 0.40) + (ai_confidence × 0.20)
```

**Completeness** — fraction of expected fields present for the request type:
- `purchase_request`: expects company + line_items + priority
- `customer_issue`: expects company + priority
- `ops_change`: expects priority
- `other`: no required fields (completeness = 0.5 baseline)

**Type compliance** — checks that extracted fields are consistent with the request type:
- Purchase requests should have line items
- Customer issues should have a company (penalised if absent)
- Penalises when line items appear on non-purchase types

**AI confidence** — the raw confidence value returned by the LLM in its JSON response, clamped to [0.0, 1.0].

---

## Routing Thresholds

| Score range | Decision | Rationale |
|---|---|---|
| > 0.85 | auto\_approve | High completeness + type consistency; safe to process without review |
| 0.50 – 0.85 | pending\_review | Missing fields or borderline type; human review required |
| < 0.50 | auto\_reject | Insufficient information to act on; caller should resend with more detail |

Thresholds are configurable via `APPROVAL_THRESHOLD` and `REJECTION_THRESHOLD` in Settings.

---

## AI Client Resilience

```mermaid
flowchart LR
    A["AIClient.call()"] --> B{"CircuitBreaker\nopen?"}
    B -->|"yes"| C["raise RetryableError\n(Circuit breaker open)"]
    B -->|"no"| D["attempt 1"]
    D -->|"TimeoutError\nConnectionError\nOSError"| E["record_failure()\nwait backoff"]
    E --> F["attempt 2"]
    F -->|"fail again"| G["wait backoff²"]
    G --> H["attempt 3"]
    H -->|"success"| I["return AICallResult\ntrack cost"]
    H -->|"fail"| J["re-raise last exception"]
    D -->|"success"| I
    F -->|"success"| I
```

- Base delay: 1.0s (overridable in tests via `base_delay=0.0`)
- Backoff multiplier: 2× per attempt
- Circuit breaker opens after 5 failures within a 60-second window
- Daily cost limit enforced before each AI call; `CostLimitExceeded` raised if exceeded

---

## Data Model

```mermaid
erDiagram
    items {
        TEXT item_id PK
        TEXT message_id UK
        TEXT request_type
        TEXT priority
        TEXT company
        TEXT line_items_json
        REAL confidence
        TEXT status
        TEXT routed_to
        TEXT review_reasons_json
        TEXT reviewer
        TEXT reviewer_note
        TEXT created_at
        TEXT updated_at
    }

    audit_log {
        INTEGER id PK
        TEXT item_id FK
        TEXT event_type
        TEXT actor
        TEXT details_json
        TEXT created_at
    }

    llm_call_log {
        INTEGER id PK
        TEXT item_id FK
        TEXT model
        INTEGER tokens_in
        INTEGER tokens_out
        REAL cost_usd
        REAL latency_ms
        TEXT prompt_version
        TEXT created_at
    }

    batch_jobs {
        TEXT job_id PK
        TEXT status
        INTEGER total
        INTEGER processed
        INTEGER failed
        TEXT created_at
        TEXT updated_at
    }

    items ||--o{ audit_log : "item_id"
    items ||--o{ llm_call_log : "item_id"
```

---

## Deployment

```mermaid
flowchart LR
    subgraph Docker Compose
        APP["app container\n(python:3.12-slim)\nnon-root: appuser\nport 8000\nHEALTHCHECK /api/v1/health"]
        DB["postgres:16-alpine\nport 5432\nHEALTHCHECK pg_isready"]
    end

    APP -->|"DATABASE_URL"| DB
    APP -->|"alembic upgrade head\non startup"| DB
    CALLER["External caller"] --> APP
```

Multi-stage Dockerfile: builder stage installs dependencies; runtime stage copies only the installed packages. Non-root `appuser` with UID 1001. Health check polls `/api/v1/health` every 30s.
