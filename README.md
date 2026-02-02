# Ops Workflow Automation (Email → Extraction → Sheet/CRM → Summary)

Demonstrates an automation pipeline for repetitive ops intake with guardrails:
- Sanitised “inbox” inputs (JSON)
- Structured extraction using a JSON schema
- Human-in-loop review step
- Audit logging for traceability
- Mock integrations (Sheets/Airtable + Slack)

## Before / After

**Before**
- Ops team reads emails manually
- Copies details into a sheet/CRM
- Posts updates in Slack
- No consistent schema, no audit trail, high rework

**After**
- Webhook ingests inbox messages
- Extracts structured fields + confidence score
- Routes low-confidence cases to human review
- Writes approved items to destinations
- Posts a redacted summary to Slack
- Audit log records every step

## Architecture

```mermaid
flowchart LR
  A[Inbox Webhook JSON] --> B[/POST /ingest/]
  B --> C[Extractor + JSON Schema Validation]
  C --> D{Confidence >= Threshold?}
  D -- No --> E[Pending Review Queue]
  E --> F[/POST /items/:id/review/]
  D -- Yes --> G[Auto-Approved]
  F --> H[Write to Sheet/CRM Mocks]
  G --> H
  H --> I[Slack Summary (PII Redacted)]
  C --> J[(SQLite Items + Audit Log)]
  F --> J
  G --> J
  H --> J
  I --> J
