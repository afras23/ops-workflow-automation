import hashlib
import re
from datetime import datetime, timezone

EMAIL_RE = re.compile(r"([A-Za-z0-9._%+-]+)@([A-Za-z0-9.-]+\.[A-Za-z]{2,})")
PHONE_RE = re.compile(r"\b(\+?\d[\d\s\-()]{7,}\d)\b")

def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def stable_id(*parts: str) -> str:
    raw = "|".join(parts).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]

def redact_pii(text: str) -> str:
    # Basic guardrail: redact emails and phone-like strings in logs/Slack summaries
    text = EMAIL_RE.sub("[REDACTED_EMAIL]", text)
    text = PHONE_RE.sub("[REDACTED_PHONE]", text)
    return text

def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()
