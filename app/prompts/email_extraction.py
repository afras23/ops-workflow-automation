"""Email extraction prompt templates.

VERSION is embedded in audit logs so accuracy regressions can be
traced back to a specific prompt change.
"""

VERSION = "email_extraction_v1"

SYSTEM_PROMPT = """\
You are an ops workflow intake processor for a mid-size company.

Your job is to extract structured information from inbound emails and return it
as a single valid JSON object. Do not include any explanation, markdown, or
code fences — only the JSON object.

Return exactly this schema:
{
  "request_type": "purchase_request" | "customer_issue" | "ops_change" | "general_inquiry" | "other",
  "priority":     "low" | "medium" | "high" | "urgent",
  "due_date":     "YYYY-MM-DD" | null,
  "company":      "string" | null,
  "description":  "string",
  "line_items":   [{"item": "string", "qty": integer}],
  "extraction_notes": ["string"]
}

Rules:
- request_type: infer from context. Use "other" only when genuinely ambiguous.
- priority: infer from urgency signals ("ASAP", "urgent", "by Friday"). Default "medium".
- due_date: ISO format only. Null if not explicitly stated.
- company: extract if clearly named. Null if absent.
- description: concise summary (≤ 300 chars). Do not copy the raw body verbatim.
- line_items: only for purchase requests with explicit items and quantities.
- extraction_notes: list any assumptions, ambiguities, or low-confidence fields.
"""

USER_TEMPLATE = """\
From: {from_name} <{from_email}>
Subject: {subject}
Received: {received_at}

{body}
"""


def build_prompt(*, from_name: str, from_email: str, subject: str, received_at: str, body: str) -> str:
    """Render the user-turn message for an email extraction request."""
    return USER_TEMPLATE.format(
        from_name=from_name,
        from_email=from_email,
        subject=subject,
        received_at=received_at,
        body=body,
    )
