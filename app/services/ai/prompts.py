"""Email extraction prompt templates (versioned).

VERSION is embedded in every audit log entry so accuracy regressions can
be traced to a specific prompt change. Increment the version suffix whenever
the system prompt or output schema changes.

Two versions are provided:
- email_extraction_v1: Verbose rules-based prompt (higher accuracy, more tokens)
- email_extraction_v2: Concise instruction prompt (lower cost, slightly less verbose)

Use get_prompt(name, **kwargs) to obtain (system, user, version) for any named template.
"""

from __future__ import annotations

VERSION = "email_extraction_v1"
VERSION_V2 = "email_extraction_v2"

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

SYSTEM_PROMPT_V2 = """\
You are an ops intake processor. Extract structured data from the email and return \
a single JSON object only — no explanation, no markdown.

Required fields:
- request_type: "purchase_request" | "customer_issue" | "ops_change" | "general_inquiry" | "other"
- priority: "low" | "medium" | "high" | "urgent"  (default "medium")
- due_date: "YYYY-MM-DD" or null
- company: company name string or null
- description: summary under 200 chars
- line_items: [{"item": "name", "qty": number}]  (purchases only, else [])
- extraction_notes: [list of assumptions or ambiguities]

Infer request_type and priority from context. Use null when a field is not stated.
"""

_USER_TEMPLATE = """\
From: {from_name} <{from_email}>
Subject: {subject}
Received: {received_at}

{body}
"""


def build_prompt(
    *,
    from_name: str,
    from_email: str,
    subject: str,
    received_at: str,
    body: str,
) -> str:
    """Render the user-turn message for an email extraction request.

    Args:
        from_name: Sender display name.
        from_email: Sender email address.
        subject: Email subject line.
        received_at: ISO 8601 received timestamp.
        body: Raw email body text.

    Returns:
        Formatted user prompt string ready to send to the AI provider.
    """
    return _USER_TEMPLATE.format(
        from_name=from_name,
        from_email=from_email,
        subject=subject,
        received_at=received_at,
        body=body,
    )


def get_prompt(name: str, **kwargs: str) -> tuple[str, str, str]:
    """Return (system_prompt, user_prompt, version) for a named prompt template.

    Args:
        name: Prompt template name — "email_extraction_v1" or "email_extraction_v2".
        **kwargs: Template variables forwarded to build_prompt (from_name, from_email,
            subject, received_at, body).

    Returns:
        Tuple of (system_prompt, user_prompt, version_string).

    Raises:
        ValueError: If name does not match a known prompt template.
    """
    if name == VERSION:
        return SYSTEM_PROMPT, build_prompt(**kwargs), VERSION
    if name == VERSION_V2:
        return SYSTEM_PROMPT_V2, build_prompt(**kwargs), VERSION_V2
    raise ValueError(f"Unknown prompt template: {name!r}")
