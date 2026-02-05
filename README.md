# Ops Workflow Automation (Email → Extraction → Sheet/CRM → Summary)

A **ops intake automation** that ingests inbox-style messages, extracts structured fields, routes low-confidence cases to a **human review queue**, writes approved items to mock destinations (Sheets/CRM), and records an **audit trail** for traceability.

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
  A["Inbox webhook JSON"] --> B["POST /ingest"]
  B --> C["Extractor + validation"]
  C --> D{"Confidence meets threshold?"}

  D -- "No" --> E["Pending review queue"]
  E --> F["POST /items/<item_id>/review"]

  D -- "Yes" --> G["Auto-approved"]

  F --> H["Write to destinations"]
  G --> H

  H --> I["Slack summary (PII redacted)"]

  C --> J["SQLite items + audit log"]
  F --> J
  G --> J
  H --> J
  I --> J
  ```
