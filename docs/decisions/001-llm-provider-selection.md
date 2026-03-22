# ADR 001 — LLM Provider Selection

**Status:** Accepted
**Date:** 2026-03-01
**Author:** anesah

---

## Context

The extraction pipeline needs an LLM that can reliably return structured JSON output. The key requirements are:

1. **Schema adherence** — the LLM must return a valid JSON object matching a specific schema on every call, not occasionally produce prose or wrap JSON in markdown fences unpredictably.
2. **Cost predictability** — per-token pricing must be stable and trackable; the system enforces a daily cost ceiling.
3. **Latency** — a synchronous ingest endpoint means extraction latency directly affects API response time. P95 should be under 3 seconds.
4. **Tool / structured output support** — native support for constrained JSON generation is preferable to prompt-engineering a JSON response out of a free-text model.

Alternatives considered: OpenAI GPT-4o, Google Gemini 1.5 Flash, a self-hosted Ollama instance, and Anthropic Claude Haiku.

---

## Decision

**Use Anthropic Claude (claude-3-5-haiku-20241022 as default) via the Anthropic Python SDK.**

The default model is configurable via `AI_MODEL` in Settings. The client is abstracted behind an `AIClient` protocol so the provider can be swapped without changing the extraction or workflow logic.

---

## Rationale

**Schema adherence.** Claude Haiku with a well-structured system prompt and explicit JSON schema in the prompt reliably returns valid JSON in testing. The extraction prompt specifies the exact output schema and includes a format reminder. Validation is done by Pydantic after the call; if Claude produces prose instead of JSON, the system raises `ExtractionError` and returns HTTP 422 to the caller — a deterministic failure mode.

**Cost.** Claude Haiku is among the lowest-cost production-grade models at the time of writing (~$0.00025 per 1K input tokens, ~$0.00125 per 1K output tokens). For the extraction use case (short prompts, short completions), per-request cost is expected to be under $0.001. The daily limit defaults to $10, giving approximately 10,000 extractions per day before the cost cap is hit.

**Latency.** Claude Haiku median latency for short completion tasks is approximately 500–800ms. This is acceptable for a synchronous ingest endpoint where callers expect near-real-time acknowledgement.

**Abstraction.** The `AIClient` protocol means the provider decision is not embedded throughout the codebase. `MockAIClient` is used in all tests and in the evaluation pipeline (offline mode), keeping test cost at $0.

---

## Consequences

- The `ANTHROPIC_API_KEY` environment variable must be set for production use. If absent and `AI_PROVIDER=anthropic`, the system will fail on startup.
- If Anthropic raises prices or degrades quality, switching to a different provider requires only a new `AIClient` implementation and an environment variable change.
- The mock client uses keyword matching, which means evaluation results with `AI_PROVIDER=mock` understate real-LLM accuracy (particularly for priority and nuanced classification). Evaluation should be re-run with a real provider before quoting accuracy figures publicly.

---

## Alternatives Rejected

**OpenAI GPT-4o.** Higher cost for this use case; no strong quality advantage for structured extraction tasks. The OpenAI SDK would require a separate abstraction layer.

**Google Gemini 1.5 Flash.** Similar cost profile to Claude Haiku. Less established SDK at the time of implementation; structured output support was newer and less tested in production.

**Ollama (self-hosted).** Zero per-token cost, but requires significant infrastructure to run reliably (GPU or high-memory CPU instances). Latency is unpredictable without dedicated hardware. Not appropriate for a demo system that must be runnable from `docker-compose up` on a developer laptop.
