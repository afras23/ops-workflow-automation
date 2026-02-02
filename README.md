# Ops Workflow Automation (Email → Extraction → Sheet/CRM → Summary)

A small but realistic **ops intake automation** that ingests inbox-style messages, extracts structured fields, routes low-confidence cases to a **human review queue**, writes approved items to mock destinations (Sheets/CRM), and records an **audit trail** for traceability.

Built as a demo package for “automation with guardrails” rather than a toy script.

---

## What this demonstrates

- **Event-driven intake** via `/ingest` (webhook-style)
- **Structured extraction** (Pydantic models + JSON Schema validation)
- **Confidence scoring** + **review reasons** (human-in-the-loop routing)
- **Idempotency protection** keyed by `message_id` (safe retries)
- **PII redaction** in Slack summaries (emails/phone-like strings)
- **Audit logging** for every state change + integration write
- **Tests** covering extraction + workflow behavior

---

## Before / After

**Before**
- Someone reads emails manually
- Copies fields into a Sheet/CRM
- Posts updates in Slack
- Inconsistent structure, no audit trail, high rework

**After**
- Webhook ingests messages
- Extracts fields → validates schema → scores confidence
- Low-confidence routed to human review with reasons
- Approved items written to destinations + Slack summary
- Audit log captures who did what, when, and why

---

## Architecture

```mermaid
flowchart LR
  A[Inbox Webhook JSON] --> B[/POST /ingest/]
  B --> C[Extractor + Validation<br/>Pydantic + JSON Schema]
  C --> D{Confidence >= Threshold?}
  D -- No --> E[Pending Review Queue]
  E --> F[/POST /items/:id/review/]
  D -- Yes --> G[Auto-Approved]
  F --> H[Write to Destinations<br/>CSV + JSONL mocks]
  G --> H
  H --> I[Slack Summary<br/>(PII Redacted)]
  C --> J[(SQLite Items + Audit Log)]
  F --> J
  G --> J
  H --> J
  I --> J
