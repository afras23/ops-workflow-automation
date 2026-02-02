# Failure Modes

## 1. Low-signal emails
Symptoms:
- Missing request type, priority, due date, company, line items
Mitigation:
- Confidence scoring
- Route to human review with reasons

## 2. Schema drift
Symptoms:
- Extraction keys missing/extra, wrong types
Mitigation:
- JSON Schema validation (Draft 2020-12)
- Pydantic model validation
- Fail fast -> status=failed with audit event

## 3. Duplicate deliveries (retries from webhook)
Symptoms:
- Same message_id ingested multiple times
Mitigation:
- Idempotency by unique index on message_id
- Return existing item state

## 4. Integration outage (Slack / Sheets / CRM)
Symptoms:
- Webhook fails or file write errors
Mitigation:
- Store the item first; then attempt integrations
- Audit log events for each destination write
- If needed: add retry queue (future enhancement)

## 5. Unsafe data in logs
Symptoms:
- PII leaks to Slack/logs
Mitigation:
- Redaction in Slack summaries (emails/phones)
- Keep raw extraction in DB; avoid dumping bodies to Slack
