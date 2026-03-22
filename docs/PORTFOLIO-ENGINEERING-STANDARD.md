# PORTFOLIO ENGINEERING STANDARD
## The Complete Specification for Senior-Level, Production-Grade AI Systems

**Purpose:** This document defines the engineering standard that EVERY portfolio project must meet. It is designed to be used as:
- A checklist when building or upgrading any project
- A specification fed into AI coding tools (Cursor, Copilot)
- An evaluation rubric for quality control
- A reference during code review

**Target standard:** Projects should be indistinguishable from production systems built by senior engineers at companies like Stripe, Anthropic, or Vercel. A senior engineer reviewing the repo should think "this person knows what they're doing" within 30 seconds.

---

# SECTION 1: PROJECT STRUCTURE

## 1.1 Required Directory Layout

Every backend/AI project must follow this structure:

```
project-name/
├── .github/
│   └── workflows/
│       └── ci.yml                 # CI pipeline (tests + lint on push)
├── app/
│   ├── __init__.py
│   ├── main.py                    # FastAPI app entry point
│   ├── config.py                  # Configuration management
│   ├── dependencies.py            # Dependency injection
│   ├── api/
│   │   ├── __init__.py
│   │   ├── routes/
│   │   │   ├── __init__.py
│   │   │   ├── health.py          # Health check endpoints
│   │   │   ├── [domain].py        # Domain-specific routes
│   │   │   └── webhooks.py        # Webhook handlers (if applicable)
│   │   ├── middleware/
│   │   │   ├── __init__.py
│   │   │   ├── error_handler.py   # Global error handling
│   │   │   ├── logging.py         # Request/response logging
│   │   │   └── rate_limiter.py    # Rate limiting
│   │   └── schemas/
│   │       ├── __init__.py
│   │       ├── requests.py        # Pydantic request models
│   │       └── responses.py       # Pydantic response models
│   ├── core/
│   │   ├── __init__.py
│   │   ├── exceptions.py          # Custom exception hierarchy
│   │   ├── logging.py             # Structured logging setup
│   │   └── constants.py           # App-wide constants
│   ├── services/
│   │   ├── __init__.py
│   │   ├── [domain]_service.py    # Business logic layer
│   │   └── ai/
│   │       ├── __init__.py
│   │       ├── client.py          # LLM client wrapper
│   │       ├── prompts.py         # Prompt templates (versioned)
│   │       ├── extraction.py      # AI extraction logic
│   │       ├── confidence.py      # Confidence scoring
│   │       └── cost_tracker.py    # Token/cost tracking
│   ├── models/
│   │   ├── __init__.py
│   │   └── [domain].py            # SQLAlchemy/DB models
│   ├── repositories/
│   │   ├── __init__.py
│   │   └── [domain]_repo.py       # Data access layer
│   ├── workers/
│   │   ├── __init__.py
│   │   └── [task]_worker.py       # Background/async workers
│   └── integrations/
│       ├── __init__.py
│       ├── [service]_client.py    # External service clients (CRM, Slack, etc.)
│       └── webhooks/
│           └── handlers.py        # Inbound webhook processing
├── tests/
│   ├── __init__.py
│   ├── conftest.py                # Shared fixtures
│   ├── unit/
│   │   ├── __init__.py
│   │   ├── test_extraction.py
│   │   ├── test_validation.py
│   │   └── test_confidence.py
│   ├── integration/
│   │   ├── __init__.py
│   │   ├── test_pipeline.py
│   │   └── test_api.py
│   └── fixtures/
│       ├── sample_inputs/         # Real-world test data (redacted)
│       └── expected_outputs/      # Expected extraction results
├── docs/
│   ├── architecture.md            # System architecture document
│   ├── decisions/                 # Architecture Decision Records (ADRs)
│   │   └── 001-llm-provider.md
│   ├── runbook.md                 # Operational runbook
│   └── diagrams/
│       └── system-architecture.mermaid
├── scripts/
│   ├── seed_data.py               # Database seeding
│   └── evaluate.py                # AI evaluation pipeline
├── migrations/                    # Alembic DB migrations (if using SQL)
│   └── versions/
├── .env.example                   # Environment variable template
├── .gitignore                     # Comprehensive gitignore
├── Dockerfile                     # Production container
├── docker-compose.yml             # Full local stack
├── pyproject.toml                 # Project config (replaces setup.py)
├── requirements.txt               # Pinned dependencies
├── requirements-dev.txt           # Dev/test dependencies
├── pytest.ini                     # Test configuration
├── README.md                      # Case-study README (see Section 11)
├── CHANGELOG.md                   # Version history
└── Makefile                       # Common commands (optional but senior signal)
```

## 1.2 Files That Must NEVER Be Committed

```gitignore
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
venv/
.venv/
env/
.env
*.egg-info/
dist/
build/

# IDE
.vscode/
.idea/
*.swp
*.swo
.DS_Store

# Project
*.db
*.sqlite3
*.log
node_modules/
.coverage
htmlcov/
.pytest_cache/
.mypy_cache/

# Secrets
*.pem
*.key
credentials.json
```

**CRITICAL:** If venv/, .env, or __pycache__/ exists in any repo, remove from git history with:
```bash
git filter-branch --force --index-filter \
  'git rm -r --cached --ignore-unmatch venv/' \
  --prune-empty -- --all
git push origin --force --all
```

## 1.3 Files That Must ALWAYS Exist

| File | Purpose | Signal to Senior Engineer |
|------|---------|--------------------------|
| Dockerfile | Containerised deployment | "This can be deployed" |
| docker-compose.yml | Full local stack | "I can run this in one command" |
| .github/workflows/ci.yml | Automated testing | "Tests run on every push" |
| .env.example | Environment documentation | "I manage secrets properly" |
| pytest.ini or pyproject.toml | Test configuration | "Testing is a first-class concern" |
| requirements.txt (pinned) | Reproducible dependencies | "I pin versions" |
| README.md (comprehensive) | Project documentation | "I communicate clearly" |

---

# SECTION 2: CODE QUALITY STANDARDS

## 2.1 Python Style

```python
# Every file must have:
# 1. Module docstring explaining purpose
# 2. Type hints on ALL function signatures
# 3. Docstrings on ALL public functions/classes
# 4. No bare except clauses
# 5. No magic numbers (use constants)
# 6. No print statements (use logging)

"""
Email extraction service.

Handles AI-powered extraction of structured data from inbound emails,
including confidence scoring and validation against business rules.
"""

import logging
from typing import Optional

from pydantic import BaseModel, Field

from app.core.exceptions import ExtractionError, ValidationError
from app.services.ai.client import AIClient
from app.services.ai.confidence import calculate_confidence

logger = logging.getLogger(__name__)


class ExtractionResult(BaseModel):
    """Result of an AI extraction operation."""

    fields: dict
    confidence: float = Field(ge=0.0, le=1.0)
    raw_response: str
    tokens_used: int
    cost_usd: float
    extraction_time_ms: float


async def extract_from_email(
    email_body: str,
    schema: dict,
    *,
    max_retries: int = 3,
    confidence_threshold: float = 0.85,
) -> ExtractionResult:
    """
    Extract structured data from an email body using AI.

    Args:
        email_body: Raw email text to extract from.
        schema: Expected output schema (JSON Schema format).
        max_retries: Number of retry attempts on failure.
        confidence_threshold: Minimum confidence for auto-approval.

    Returns:
        ExtractionResult with extracted fields and metadata.

    Raises:
        ExtractionError: If extraction fails after all retries.
        ValidationError: If extracted data doesn't match schema.
    """
    # Implementation...
```

## 2.2 Naming Conventions

```python
# Files: snake_case.py
# Classes: PascalCase
# Functions: snake_case
# Constants: UPPER_SNAKE_CASE
# Private methods: _leading_underscore
# Type aliases: PascalCase

# BAD:
def processEmail(data): ...
class email_processor: ...
RETRIES = 3  # What retries? Be specific.

# GOOD:
def process_inbound_email(raw_email: RawEmail) -> ProcessedEmail: ...
class EmailProcessor: ...
MAX_EXTRACTION_RETRIES = 3
DEFAULT_CONFIDENCE_THRESHOLD = 0.85
```

## 2.3 Import Organization

```python
# Standard library
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

# Third party
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

# Local
from app.core.exceptions import ExtractionError
from app.services.ai.client import AIClient
```

## 2.4 What Immediately Signals "Junior" vs "Senior"

| Junior Signal | Senior Signal |
|--------------|---------------|
| `print()` for debugging | `logger.info()` with structured context |
| Bare `except:` or `except Exception:` | Specific exception types with recovery logic |
| `# TODO: fix later` in committed code | ADR explaining trade-offs, or issue linked |
| No type hints | Full type hints including generics |
| Single test file with 3 tests | Test directory with unit/integration separation |
| Functions that do 5 things | Single-responsibility functions with clear names |
| Hardcoded config values | Environment-based configuration with validation |
| `import *` | Explicit imports |
| Comments explaining WHAT code does | Comments explaining WHY (code explains what) |
| No error handling | Custom exception hierarchy with recovery strategies |
| `time.sleep(5)` for rate limiting | Exponential backoff with jitter |
| Synchronous API calls in a loop | Async with concurrency limits |
| Raw string SQL queries | ORM or parameterised queries |
| `.env` committed | `.env.example` with descriptions, `.env` in gitignore |
| Generic variable names (data, result, info) | Domain-specific names (extraction_result, email_metadata) |

---

# SECTION 3: CONFIGURATION MANAGEMENT

## 3.1 Configuration Pattern

```python
"""
Application configuration.

All configuration loaded from environment variables with validation,
defaults, and clear documentation. Never hardcode secrets or
environment-specific values.
"""

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from environment."""

    # Application
    app_name: str = "ops-workflow-automation"
    app_env: str = Field(default="development", description="development|staging|production")
    debug: bool = False
    log_level: str = "INFO"

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_prefix: str = "/api/v1"

    # Database
    database_url: str = Field(..., description="PostgreSQL connection string")
    db_pool_size: int = 5
    db_max_overflow: int = 10

    # AI Provider
    ai_provider: str = Field(default="anthropic", description="anthropic|openai")
    anthropic_api_key: str = Field(default="", description="Anthropic API key")
    openai_api_key: str = Field(default="", description="OpenAI API key")
    ai_model: str = "claude-sonnet-4-20250514"
    ai_max_tokens: int = 4096
    ai_temperature: float = 0.0

    # Processing
    confidence_threshold: float = Field(
        default=0.85,
        ge=0.0,
        le=1.0,
        description="Minimum confidence for auto-approval",
    )
    max_retries: int = 3
    retry_backoff_base: float = 2.0

    # Cost Controls
    max_daily_cost_usd: float = 50.0
    max_tokens_per_request: int = 8192
    cost_alert_threshold_usd: float = 40.0

    # Monitoring
    enable_metrics: bool = True
    health_check_interval_seconds: int = 30

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
```

## 3.2 .env.example (Required)

```bash
# Application
APP_ENV=development
DEBUG=true
LOG_LEVEL=INFO

# Database
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/ops_workflow

# AI Provider (choose one)
AI_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
# OPENAI_API_KEY=sk-...

# Processing
CONFIDENCE_THRESHOLD=0.85
MAX_RETRIES=3

# Cost Controls
MAX_DAILY_COST_USD=50.0
```

---

# SECTION 4: ERROR HANDLING & RESILIENCE

## 4.1 Custom Exception Hierarchy

```python
"""
Application exception hierarchy.

Every exception has:
- A clear name describing the failure
- An error code for programmatic handling
- A user-friendly message
- Context data for debugging
"""


class AppError(Exception):
    """Base application error."""

    def __init__(
        self,
        message: str,
        error_code: str = "INTERNAL_ERROR",
        details: dict | None = None,
    ):
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        super().__init__(self.message)


class ExtractionError(AppError):
    """AI extraction failed after all retries."""

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message, error_code="EXTRACTION_FAILED", details=details)


class ValidationError(AppError):
    """Extracted data failed schema validation."""

    def __init__(self, message: str, field: str | None = None, details: dict | None = None):
        details = details or {}
        if field:
            details["field"] = field
        super().__init__(message, error_code="VALIDATION_FAILED", details=details)


class ConfidenceTooLow(AppError):
    """Extraction confidence below threshold — requires human review."""

    def __init__(self, confidence: float, threshold: float):
        super().__init__(
            f"Confidence {confidence:.2f} below threshold {threshold:.2f}",
            error_code="CONFIDENCE_LOW",
            details={"confidence": confidence, "threshold": threshold},
        )


class RateLimitExceeded(AppError):
    """AI provider rate limit hit."""

    def __init__(self, retry_after: float | None = None):
        super().__init__(
            "Rate limit exceeded",
            error_code="RATE_LIMITED",
            details={"retry_after_seconds": retry_after},
        )


class CostLimitExceeded(AppError):
    """Daily cost limit reached."""

    def __init__(self, current_cost: float, limit: float):
        super().__init__(
            f"Daily cost ${current_cost:.2f} exceeds limit ${limit:.2f}",
            error_code="COST_LIMIT",
            details={"current_cost": current_cost, "limit": limit},
        )
```

## 4.2 Retry Logic

```python
"""
Retry decorator with exponential backoff and jitter.
"""

import asyncio
import logging
import random
from functools import wraps
from typing import Type

logger = logging.getLogger(__name__)


def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    retryable_exceptions: tuple[Type[Exception], ...] = (Exception,),
    on_retry: callable | None = None,
):
    """
    Retry async function with exponential backoff and jitter.

    Args:
        max_retries: Maximum retry attempts.
        base_delay: Initial delay in seconds.
        max_delay: Maximum delay cap.
        retryable_exceptions: Exception types that trigger retry.
        on_retry: Optional callback(attempt, exception, delay).
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except retryable_exceptions as e:
                    last_exception = e
                    if attempt == max_retries:
                        logger.error(
                            "All retries exhausted",
                            extra={
                                "function": func.__name__,
                                "attempts": attempt + 1,
                                "final_error": str(e),
                            },
                        )
                        raise

                    delay = min(base_delay * (2 ** attempt), max_delay)
                    jitter = random.uniform(0, delay * 0.1)
                    delay += jitter

                    logger.warning(
                        "Retrying after error",
                        extra={
                            "function": func.__name__,
                            "attempt": attempt + 1,
                            "delay_seconds": round(delay, 2),
                            "error": str(e),
                        },
                    )

                    if on_retry:
                        on_retry(attempt + 1, e, delay)

                    await asyncio.sleep(delay)

            raise last_exception
        return wrapper
    return decorator
```

## 4.3 Global Error Handler (FastAPI Middleware)

```python
"""
Global error handling middleware.

Converts all exceptions to structured JSON responses with
appropriate HTTP status codes and error details.
"""

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.exceptions import AppError, ValidationError, RateLimitExceeded


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        try:
            return await call_next(request)
        except AppError as e:
            status_map = {
                "VALIDATION_FAILED": 422,
                "CONFIDENCE_LOW": 202,  # Accepted for review
                "RATE_LIMITED": 429,
                "COST_LIMIT": 503,
                "EXTRACTION_FAILED": 500,
            }
            return JSONResponse(
                status_code=status_map.get(e.error_code, 500),
                content={
                    "error": e.error_code,
                    "message": e.message,
                    "details": e.details,
                },
            )
        except Exception as e:
            logger.exception("Unhandled exception", extra={"path": request.url.path})
            return JSONResponse(
                status_code=500,
                content={
                    "error": "INTERNAL_ERROR",
                    "message": "An unexpected error occurred",
                },
            )
```

---

# SECTION 5: AI / LLM ENGINEERING STANDARDS

## 5.1 LLM Client Wrapper

```python
"""
AI client wrapper with cost tracking, retry logic, and structured output.

Never call LLM APIs directly — always use this wrapper so that:
- Every call is logged with cost
- Retries are handled consistently
- Provider switching is a config change
- Token usage is tracked
"""

import time
import logging
from anthropic import AsyncAnthropic

from app.config import settings
from app.core.exceptions import ExtractionError, RateLimitExceeded

logger = logging.getLogger(__name__)

# Cost per 1M tokens (update as prices change)
COST_PER_MILLION = {
    "claude-sonnet-4-20250514": {"input": 3.0, "output": 15.0},
    "gpt-4o": {"input": 2.5, "output": 10.0},
}


class AICallResult(BaseModel):
    """Result from an AI API call with full tracking metadata."""

    content: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: float


class AIClient:
    """Unified AI client with cost tracking and reliability."""

    def __init__(self):
        self.client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        self._daily_cost = 0.0
        self._request_count = 0

    async def extract(
        self,
        prompt: str,
        system: str = "",
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> AICallResult:
        """
        Send extraction request to LLM with full tracking.

        Returns:
            AICallResult with content, token counts, cost, and latency.

        Raises:
            CostLimitExceeded: If daily cost budget is exhausted.
        """
        if self._daily_cost >= settings.max_daily_cost_usd:
            raise CostLimitExceeded(self._daily_cost, settings.max_daily_cost_usd)

        start = time.monotonic()

        response = await self.client.messages.create(
            model=settings.ai_model,
            max_tokens=max_tokens or settings.ai_max_tokens,
            temperature=temperature if temperature is not None else settings.ai_temperature,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )

        latency_ms = (time.monotonic() - start) * 1000
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens

        model_costs = COST_PER_MILLION.get(settings.ai_model, {"input": 3.0, "output": 15.0})
        cost = (input_tokens * model_costs["input"] + output_tokens * model_costs["output"]) / 1_000_000

        self._daily_cost += cost
        self._request_count += 1

        logger.info(
            "AI request completed",
            extra={
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost_usd": round(cost, 6),
                "latency_ms": round(latency_ms, 1),
                "daily_total_cost": round(self._daily_cost, 4),
                "model": settings.ai_model,
            },
        )

        return AICallResult(
            content=response.content[0].text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            latency_ms=latency_ms,
        )
```

## 5.2 Prompt Management

```python
"""
Prompt templates with versioning.

Prompts are versioned so that:
- Changes are tracked in git
- A/B testing is possible
- Regression is detectable
- Audit trail shows which prompt version produced each result
"""

PROMPTS = {
    "email_extraction_v1": {
        "version": "1.0",
        "system": """You are a data extraction system. Extract structured data
from emails according to the provided schema. Return ONLY valid JSON.
If a field cannot be determined, use null. Never hallucinate values.""",
        "user_template": """Extract the following fields from this email:

Schema:
{schema}

Email:
{email_body}

Return valid JSON matching the schema. Include ONLY the fields specified.""",
    },
    "email_extraction_v2": {
        "version": "2.0",
        "system": """You are a precise data extraction system. Extract structured
data from emails. For each field, also provide a confidence estimate
(high/medium/low) based on how clearly the information appears in the text.
Return ONLY valid JSON.""",
        "user_template": """Extract the following fields from this email.
For each field, include a confidence level.

Schema:
{schema}

Email:
{email_body}

Return JSON with structure: {{"fields": {{...}}, "field_confidence": {{field_name: "high"|"medium"|"low"}}}}""",
    },
}


def get_prompt(name: str, **kwargs) -> tuple[str, str, str]:
    """
    Get a formatted prompt by name.

    Returns: (system_prompt, user_prompt, version)
    """
    template = PROMPTS[name]
    return (
        template["system"],
        template["user_template"].format(**kwargs),
        template["version"],
    )
```

## 5.3 Confidence Scoring

```python
"""
Confidence scoring for AI extraction results.

Confidence is calculated from multiple signals:
- Field completeness (how many required fields were extracted)
- Schema compliance (do values match expected types/formats)
- AI self-reported confidence (if available)
- Historical accuracy for similar inputs
"""

from app.api.schemas.requests import ExtractionSchema


def calculate_confidence(
    extracted: dict,
    schema: ExtractionSchema,
    field_confidence: dict | None = None,
) -> float:
    """
    Calculate overall extraction confidence score (0.0 to 1.0).

    Scoring components:
    - Completeness: % of required fields that are non-null (weight: 0.4)
    - Type compliance: % of fields matching expected type (weight: 0.3)
    - AI confidence: Average self-reported confidence (weight: 0.3)
    """
    required_fields = schema.required_fields
    extracted_fields = {k: v for k, v in extracted.items() if v is not None}

    # Completeness score
    completeness = len(extracted_fields) / max(len(required_fields), 1)

    # Type compliance score
    type_matches = sum(
        1 for field, value in extracted_fields.items()
        if _type_matches(value, schema.field_types.get(field))
    )
    type_compliance = type_matches / max(len(extracted_fields), 1)

    # AI self-reported confidence
    ai_confidence = 1.0
    if field_confidence:
        confidence_map = {"high": 1.0, "medium": 0.7, "low": 0.3}
        scores = [confidence_map.get(c, 0.5) for c in field_confidence.values()]
        ai_confidence = sum(scores) / max(len(scores), 1)

    # Weighted combination
    overall = (completeness * 0.4) + (type_compliance * 0.3) + (ai_confidence * 0.3)

    return round(overall, 3)
```

## 5.4 Evaluation Pipeline

```python
"""
Evaluation pipeline for AI extraction accuracy.

Every AI project MUST include an evaluation script that:
- Runs against a test set of real-world inputs
- Reports accuracy per field
- Reports overall pass rate
- Produces a structured evaluation report
- Can be run in CI to detect regression
"""

# scripts/evaluate.py

import json
import asyncio
from pathlib import Path
from datetime import datetime

from app.services.ai.extraction import extract_from_email


async def run_evaluation(test_set_path: str, output_path: str):
    """
    Run extraction evaluation on test set.

    Test set format (JSONL):
    {"input": "email text...", "expected": {"field1": "value1", ...}}
    """
    test_cases = []
    with open(test_set_path) as f:
        for line in f:
            test_cases.append(json.loads(line))

    results = []
    total_correct = 0
    total_fields = 0
    field_accuracy = {}

    for case in test_cases:
        result = await extract_from_email(case["input"], schema=case.get("schema", {}))
        extracted = result.fields

        case_correct = 0
        for field, expected_value in case["expected"].items():
            total_fields += 1
            actual = extracted.get(field)
            correct = actual == expected_value

            if correct:
                total_correct += 1
                case_correct += 1

            if field not in field_accuracy:
                field_accuracy[field] = {"correct": 0, "total": 0}
            field_accuracy[field]["total"] += 1
            if correct:
                field_accuracy[field]["correct"] += 1

        results.append({
            "input_preview": case["input"][:100],
            "expected": case["expected"],
            "actual": extracted,
            "fields_correct": case_correct,
            "fields_total": len(case["expected"]),
            "confidence": result.confidence,
        })

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_cases": len(test_cases),
        "overall_accuracy": round(total_correct / max(total_fields, 1), 3),
        "field_accuracy": {
            field: round(data["correct"] / max(data["total"], 1), 3)
            for field, data in field_accuracy.items()
        },
        "pass_rate": sum(1 for r in results if r["fields_correct"] == r["fields_total"]) / max(len(results), 1),
        "results": results,
    }

    with open(output_path, "w") as f:
        json.dump(report, f, indent=2)

    print(f"Overall accuracy: {report['overall_accuracy']:.1%}")
    print(f"Pass rate: {report['pass_rate']:.1%}")
    for field, acc in report["field_accuracy"].items():
        print(f"  {field}: {acc:.1%}")
```

---

# SECTION 6: API DESIGN

## 6.1 FastAPI Application Setup

```python
"""
Application entry point.

The app is created via a factory function so that:
- Configuration can be injected
- Middleware is consistently applied
- Testing can use different configs
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api.middleware.error_handler import ErrorHandlerMiddleware
from app.api.routes import health, extraction, review


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic."""
    # Startup: DB connections, AI client init, etc.
    logger.info("Starting application", extra={"env": settings.app_env})
    yield
    # Shutdown: Close connections, flush logs
    logger.info("Shutting down")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        docs_url="/docs" if settings.debug else None,
        lifespan=lifespan,
    )

    # Middleware
    app.add_middleware(ErrorHandlerMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.debug else settings.allowed_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routes
    app.include_router(health.router, prefix="/api/v1", tags=["health"])
    app.include_router(extraction.router, prefix="/api/v1", tags=["extraction"])
    app.include_router(review.router, prefix="/api/v1", tags=["review"])

    return app

app = create_app()
```

## 6.2 Health Check Endpoint (REQUIRED in Every Project)

```python
"""
Health check endpoints.

Every production system must expose:
- /health — basic liveness check
- /health/ready — readiness check (DB, AI provider, etc.)
- /metrics — operational metrics
"""

from fastapi import APIRouter
from datetime import datetime

router = APIRouter()


@router.get("/health")
async def health():
    """Basic liveness check."""
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}


@router.get("/health/ready")
async def readiness(db: AsyncSession = Depends(get_db)):
    """Readiness check — verifies all dependencies are available."""
    checks = {}

    # Database
    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {str(e)}"

    # AI Provider
    try:
        # Quick check that API key is valid
        checks["ai_provider"] = "ok"
    except Exception as e:
        checks["ai_provider"] = f"error: {str(e)}"

    all_ok = all(v == "ok" for v in checks.values())
    return {
        "status": "ready" if all_ok else "degraded",
        "checks": checks,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/metrics")
async def metrics():
    """Operational metrics."""
    return {
        "processed_today": await get_processed_count_today(),
        "success_rate": await get_success_rate(),
        "average_confidence": await get_avg_confidence(),
        "pending_review": await get_pending_review_count(),
        "daily_cost_usd": ai_client.daily_cost,
        "uptime_seconds": get_uptime(),
    }
```

## 6.3 Standard API Response Format

```python
# Every API response follows this structure:

# Success:
{
    "status": "success",
    "data": { ... },
    "metadata": {
        "request_id": "uuid",
        "timestamp": "ISO8601",
        "processing_time_ms": 142
    }
}

# Error:
{
    "status": "error",
    "error": {
        "code": "EXTRACTION_FAILED",
        "message": "Human-readable description",
        "details": { ... }
    },
    "metadata": {
        "request_id": "uuid",
        "timestamp": "ISO8601"
    }
}
```

---

# SECTION 7: TESTING STANDARDS

## 7.1 Test Structure

```
tests/
├── conftest.py              # Shared fixtures: test DB, mock AI client, etc.
├── unit/
│   ├── test_extraction.py   # Test extraction logic in isolation
│   ├── test_validation.py   # Test schema validation
│   ├── test_confidence.py   # Test confidence scoring
│   └── test_routing.py      # Test routing decisions
├── integration/
│   ├── test_pipeline.py     # Test full extraction pipeline
│   ├── test_api.py          # Test API endpoints
│   └── test_database.py     # Test data persistence
└── fixtures/
    ├── sample_inputs/        # Real-world test data
    │   ├── simple_email.txt
    │   ├── complex_email.txt
    │   └── malformed_email.txt
    └── expected_outputs/
        ├── simple_email.json
        └── complex_email.json
```

## 7.2 Test Quality Requirements

```python
# Every test must:
# 1. Have a clear name describing what it tests
# 2. Test ONE thing (single assertion per concept)
# 3. Be independent (no ordering dependencies)
# 4. Use fixtures for shared setup
# 5. Include edge cases and error paths
# 6. Mock external services (never call real APIs in unit tests)

# Minimum test coverage per project:
# - Happy path for every core function
# - Error path for every function that can fail
# - Edge cases (empty input, malformed input, boundary values)
# - At least 1 integration test for the main pipeline
# - At least 3 test fixtures with realistic data

class TestExtractionConfidence:
    """Tests for confidence scoring logic."""

    def test_all_fields_extracted_high_confidence(self):
        """Full extraction with matching types scores above threshold."""
        result = calculate_confidence(
            extracted={"vendor": "Acme Corp", "amount": 1500.00, "date": "2026-03-15"},
            schema=invoice_schema,
            field_confidence={"vendor": "high", "amount": "high", "date": "high"},
        )
        assert result >= 0.85

    def test_missing_required_fields_low_confidence(self):
        """Missing required fields reduce confidence below threshold."""
        result = calculate_confidence(
            extracted={"vendor": "Acme Corp", "amount": None, "date": None},
            schema=invoice_schema,
        )
        assert result < 0.85

    def test_empty_extraction_zero_confidence(self):
        """Completely empty extraction returns near-zero confidence."""
        result = calculate_confidence(extracted={}, schema=invoice_schema)
        assert result < 0.2

    def test_mixed_confidence_weighted_correctly(self):
        """AI-reported mixed confidence affects overall score."""
        result = calculate_confidence(
            extracted={"vendor": "Acme Corp", "amount": 1500.00, "date": "2026-03-15"},
            schema=invoice_schema,
            field_confidence={"vendor": "high", "amount": "low", "date": "medium"},
        )
        assert 0.5 < result < 0.85
```

---

# SECTION 8: OBSERVABILITY & LOGGING

## 8.1 Structured Logging

```python
"""
Structured logging configuration.

ALL logs must be structured JSON in production:
- Every log entry has a consistent schema
- Context is passed via 'extra' dict, not string formatting
- Log levels are used correctly:
  - DEBUG: Detailed diagnostic info
  - INFO: Normal operations (request processed, job completed)
  - WARNING: Recoverable issues (retry triggered, fallback used)
  - ERROR: Operation failed but system continues
  - CRITICAL: System-wide failure
"""

import logging
import json
import sys


class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_entry = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "extra"):
            log_entry.update(record.extra)
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry)
```

## 8.2 Audit Trail (Required for All AI Decisions)

```python
"""
Audit trail for every AI decision.

Every extraction, classification, or routing decision must be logged
with enough context to:
- Reproduce the decision
- Understand why it was made
- Debug incorrect decisions
- Satisfy compliance requirements
"""

class AuditEntry(Base):
    __tablename__ = "audit_log"

    id = Column(UUID, primary_key=True, default=uuid4)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    action = Column(String, nullable=False)         # "extraction", "classification", "routing"
    input_hash = Column(String, nullable=False)      # Hash of input for dedup
    input_preview = Column(String)                   # First 200 chars of input
    output = Column(JSON, nullable=False)            # Full extraction result
    confidence = Column(Float)                       # Confidence score
    decision = Column(String)                        # "auto_approved", "sent_to_review", "rejected"
    prompt_version = Column(String)                  # Which prompt version produced this
    model = Column(String)                           # Which AI model
    tokens_used = Column(Integer)
    cost_usd = Column(Float)
    latency_ms = Column(Float)
    reviewed_by = Column(String, nullable=True)      # Human reviewer (if applicable)
    review_action = Column(String, nullable=True)    # "approved", "edited", "rejected"
    review_timestamp = Column(DateTime, nullable=True)
```

---

# SECTION 9: DEPLOYMENT & INFRASTRUCTURE

## 9.1 Dockerfile (Required)

```dockerfile
# Multi-stage build for smaller production image
FROM python:3.12-slim as builder

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12-slim

WORKDIR /app
COPY --from=builder /install /usr/local
COPY . .

# Non-root user (security)
RUN useradd -m appuser
USER appuser

EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/health')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

## 9.2 docker-compose.yml (Required)

```yaml
version: "3.8"

services:
  app:
    build: .
    ports:
      - "8000:8000"
    env_file: .env
    depends_on:
      db:
        condition: service_healthy
    volumes:
      - ./app:/app/app  # Hot reload in dev

  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: user
      POSTGRES_PASSWORD: password
      POSTGRES_DB: app_db
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U user -d app_db"]
      interval: 5s
      timeout: 5s
      retries: 5

volumes:
  pgdata:
```

## 9.3 CI Pipeline (Required)

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16-alpine
        env:
          POSTGRES_USER: test
          POSTGRES_PASSWORD: test
          POSTGRES_DB: test_db
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 5s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r requirements-dev.txt

      - name: Lint
        run: |
          ruff check .
          ruff format --check .

      - name: Type check
        run: mypy app/ --ignore-missing-imports

      - name: Test
        env:
          DATABASE_URL: postgresql://test:test@localhost:5432/test_db
          AI_PROVIDER: mock
        run: pytest tests/ -v --tb=short
```

---

# SECTION 10: SECURITY STANDARDS

## 10.1 Checklist (Every Project)

```
□ Secrets in environment variables, never in code
□ .env in .gitignore (verified)
□ .env.example exists with descriptions (no real values)
□ Input validation on all API endpoints (Pydantic)
□ SQL injection prevention (ORM or parameterised queries)
□ Rate limiting on public endpoints
□ CORS configured (restrictive in production)
□ Non-root Docker user
□ Dependencies pinned to specific versions
□ No debug mode in production config
□ Prompt injection mitigation (input sanitisation for AI inputs)
□ PII handling documented (what data is sent to AI providers)
□ API keys have minimum required permissions
```

## 10.2 Prompt Injection Mitigation

```python
"""
Input sanitisation for AI prompts.

Mitigate prompt injection by:
1. Separating user content from instructions (system vs user prompt)
2. Validating input length and format
3. Detecting injection patterns
4. Using structured output (JSON schema) to constrain responses
"""

import re

INJECTION_PATTERNS = [
    r"ignore\s+(previous|above|all)\s+(instructions|prompts)",
    r"you\s+are\s+now",
    r"system\s*:\s*",
    r"<\|.*\|>",
    r"```\s*(system|admin|root)",
]


def sanitise_input(text: str, max_length: int = 10000) -> str:
    """
    Sanitise user input before including in AI prompt.

    Args:
        text: Raw user input.
        max_length: Maximum allowed length.

    Returns:
        Sanitised text.

    Raises:
        ValidationError: If input contains injection patterns.
    """
    if len(text) > max_length:
        text = text[:max_length]

    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            logger.warning("Potential prompt injection detected", extra={"pattern": pattern})
            raise ValidationError(f"Input contains prohibited pattern")

    return text.strip()
```

---

# SECTION 11: README STANDARD (Case Study Format)

Every README must follow this structure. This is the FIRST thing a client or senior engineer reads.

```markdown
# [Project Name]
## [Problem → Outcome in one line with metric]

> **Architecture:** Python, FastAPI, Claude API, PostgreSQL, Docker
> **Status:** Production-ready | [Live Demo](link) | [API Docs](link)

### The Problem

[2-3 sentences. Business language. Who has this pain and how bad it is.
Include a specific number: "X hours/week", "Y% error rate", "$Z cost".]

### The Solution

[What the system does at a high level. 3-4 sentences. Focus on the
approach (AI + automation + human oversight), not implementation details.]

### Architecture

```
[ASCII or Mermaid diagram showing the full system flow.
Include: inputs, processing steps, decision points, outputs, storage.]
```

### Key Features

| Feature | Why It Matters |
|---------|---------------|
| Confidence scoring | System knows when it's uncertain — routes to human review |
| Retry with backoff | Handles API failures gracefully without data loss |
| Full audit trail | Every decision logged for compliance and debugging |
| Cost tracking | Token usage and cost per operation monitored |
| Human review queue | Safety net for edge cases — AI doesn't go rogue |
| Schema validation | Extracted data validated before downstream use |

### Technical Highlights

- Async processing with configurable concurrency
- Structured prompts with versioning for reproducibility
- Evaluation pipeline with XX-case test set (Y% accuracy)
- Docker deployment with health checks
- CI pipeline with automated testing on every push

### Results

| Metric | Before | After |
|--------|--------|-------|
| Processing time per item | 15 minutes | <30 seconds |
| Error rate | ~15% | <5% |
| Audit coverage | None | 100% |
| Cost per item | - | ~$0.03 |

### Project Structure

```
[Abbreviated tree showing key directories]
```

### How to Run

```bash
# Clone and start
git clone https://github.com/afras23/[project].git
cd [project]
cp .env.example .env  # Add your API keys
docker-compose up -d

# Run tests
docker-compose exec app pytest tests/ -v

# Run evaluation
docker-compose exec app python scripts/evaluate.py
```

### Evaluation Results

```
Overall accuracy: 94.2%
Pass rate: 88.0%
Field accuracy:
  vendor_name: 97.0%
  amount: 95.0%
  date: 92.0%
  line_items: 85.0%
```

### Architecture Decisions

| Decision | Rationale |
|----------|-----------|
| Claude over GPT-4 for extraction | Better structured output compliance at lower cost |
| PostgreSQL over MongoDB | Relational model suits audit trail queries |
| Async processing | Handles concurrent requests without blocking |
| Human-in-the-loop at <0.85 confidence | Balances automation speed with accuracy requirements |
```

---

# SECTION 12: GIT PRACTICES

## 12.1 Commit Messages

```
# Format: <type>: <description>
# Types: feat, fix, refactor, test, docs, chore, perf

# GOOD:
feat: add confidence scoring to extraction pipeline
fix: handle null date fields in invoice extraction
test: add edge case tests for malformed email input
docs: add architecture diagram and decision records
refactor: extract AI client into reusable wrapper
perf: add connection pooling for database queries
chore: add Docker healthcheck and CI pipeline

# BAD:
update code
fix bug
WIP
initial commit
asdf
```

## 12.2 Minimum Commits Per Project

A credible project should have **20-30+ commits** showing iterative development:

```
Example commit history (reading bottom to top):
- docs: add evaluation results to README
- test: add integration tests for full pipeline
- feat: add /metrics endpoint with processing stats
- feat: add cost tracking to AI client
- chore: add Docker deployment with health checks
- chore: add GitHub Actions CI pipeline
- feat: add human review queue endpoints
- feat: add confidence scoring
- refactor: extract prompt templates with versioning
- feat: add retry logic with exponential backoff
- fix: handle malformed email attachments
- test: add unit tests for extraction and validation
- feat: add audit trail logging
- feat: add schema validation for extracted data
- feat: implement core extraction pipeline
- feat: add FastAPI app with health check
- chore: initial project structure and configuration
```

---

# SECTION 13: EVALUATION CHECKLIST

**NOTE:** This checklist defines the BASELINE senior-level standard. For projects targeting 10/10, use the EXTENDED checklist in PORTFOLIO-10-OUT-OF-10-ADDENDUM.md (Part 6) which adds: circuit breakers, idempotency, correlation IDs, Alembic migrations, Makefile, pre-commit hooks, ADRs, runbook, parameterised tests, concurrency tests, security tests, batch processing, pagination, graceful shutdown, and more.

**Use this checklist during development.** Use the Addendum's checklist as the final quality gate.

Use this checklist to evaluate every project before considering it complete:

## Code Quality
- [ ] Type hints on ALL function signatures
- [ ] Docstrings on ALL public functions and classes
- [ ] No print statements (use logger)
- [ ] No bare except clauses
- [ ] No hardcoded config values
- [ ] No TODO/FIXME comments in committed code
- [ ] Consistent naming conventions throughout
- [ ] Clean imports (organized, no wildcards)

## Architecture
- [ ] Clear separation: routes / services / models / repositories
- [ ] Dependency injection (not global imports of stateful objects)
- [ ] Configuration via environment variables with validation
- [ ] Custom exception hierarchy (not generic Exception)
- [ ] Retry logic for external service calls
- [ ] Async where appropriate (API calls, DB queries)

## AI / LLM Specific
- [ ] AI client wrapper with cost tracking
- [ ] Prompt templates versioned and separated from code
- [ ] Confidence scoring on AI outputs
- [ ] Human review pathway for low-confidence results
- [ ] Schema validation on structured AI outputs (Pydantic)
- [ ] Input sanitisation (prompt injection mitigation)
- [ ] Evaluation script with test set
- [ ] Cost controls (daily limit, per-request limit)

## Testing
- [ ] Unit tests for core business logic
- [ ] Integration tests for API endpoints
- [ ] Edge case tests (empty input, malformed input, API failure)
- [ ] Test fixtures with realistic data
- [ ] Mocked external services (no real API calls in tests)
- [ ] pytest configuration (pytest.ini or pyproject.toml)
- [ ] Tests pass in CI

## Infrastructure
- [ ] Dockerfile (multi-stage, non-root user, health check)
- [ ] docker-compose.yml (app + database + any dependencies)
- [ ] .github/workflows/ci.yml (lint + type check + test)
- [ ] .env.example with all required variables documented
- [ ] .gitignore comprehensive (no venv, no .env, no __pycache__)
- [ ] requirements.txt with pinned versions
- [ ] requirements-dev.txt for test/lint dependencies

## Observability
- [ ] Health check endpoint (/health)
- [ ] Readiness check endpoint (/health/ready)
- [ ] Metrics endpoint (/metrics)
- [ ] Structured logging (JSON format)
- [ ] Audit trail for AI decisions
- [ ] Error logging with context

## Documentation
- [ ] README follows case study format (Section 11)
- [ ] Architecture diagram (ASCII, Mermaid, or image)
- [ ] How to Run section (Docker commands)
- [ ] Evaluation results included
- [ ] Architecture decisions documented
- [ ] API auto-documented (FastAPI /docs)

## Git
- [ ] 20+ meaningful commits with descriptive messages
- [ ] No venv/, .env, __pycache__ in history
- [ ] No duplicate repos
- [ ] No TODO.md or Jupyter notebooks as primary files
- [ ] Commit history tells a story of iterative development

## Security
- [ ] Secrets in env vars only
- [ ] Input validation on all endpoints
- [ ] Rate limiting on public endpoints
- [ ] Non-root Docker user
- [ ] Dependencies pinned
- [ ] Prompt injection mitigation

---

**When every checkbox above is checked, the project meets senior-level production standard.**

**If feeding this to Cursor:** Tell it "Build this project following the engineering standard in this document. Check every item in Section 13 before considering any file complete."
