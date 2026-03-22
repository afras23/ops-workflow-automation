# ADR 002 — Confidence Scoring Approach

**Status:** Accepted
**Date:** 2026-03-08
**Author:** anesah

---

## Context

The routing pipeline needs a signal to decide whether to auto-approve, send to human review, or auto-reject an extracted item. The naive approach is to use the confidence value returned by the LLM directly. The problem is that raw LLM confidence is unreliable: LLMs are known to be overconfident on uncertain inputs and underconfident on clear ones. A system that auto-approves on high LLM confidence will pass through poorly-extracted items and block good ones.

A second option is to use a fixed rule-based classifier (e.g. "if it has a company and line items, approve it"). This is fast and auditable but brittle — it cannot generalise to new request types without code changes.

The routing decision also needs to be explainable. When an ops reviewer sees an item in the review queue, they need to understand *why* it was sent for review, not just that "confidence was 0.62."

---

## Decision

**Use a composite confidence score computed from three weighted signals: field completeness (40%), type compliance (40%), and raw LLM confidence (20%).**

```python
confidence = (completeness * 0.40) + (type_compliance * 0.40) + (ai_confidence * 0.20)
```

The routing service applies fixed thresholds to this composite score:
- `> 0.85` → auto_approve
- `0.50 – 0.85` → pending_review
- `< 0.50` → auto_reject

Thresholds are configurable via `APPROVAL_THRESHOLD` and `REJECTION_THRESHOLD` in Settings.

---

## Rationale

**Field completeness as a 40% weight.** Completeness is entirely observable — it does not depend on the LLM's self-assessment. A purchase request with no company and no line items is objectively incomplete. Completeness is computed per-type: the expected fields for each request type are defined in the scorer, not in the prompt.

**Type compliance as a 40% weight.** Compliance checks that the extracted fields are internally consistent. A "purchase_request" that has no line items is suspicious. An "ops_change" that has line items is suspicious. These cross-field consistency checks catch cases where the LLM classified the type correctly but extracted fields inconsistently — or vice versa.

**LLM confidence as a 20% weight.** The LLM confidence is still useful as a tiebreaker and for cases the rule-based components cannot assess (e.g. ambiguous language, unusual formatting). Capping its weight at 20% limits the damage from LLM overconfidence.

**Explainability.** Because the completeness and compliance components are rule-based, the review reasons surfaced to the reviewer are human-readable strings: "missing company for purchase_request", "line items present on ops_change type". This is more useful than "confidence = 0.62."

**Separating scoring from the prompt.** The scoring logic lives in `ConfidenceScorer`, not in the prompt. This means threshold tuning and field requirement changes do not require prompt versioning or re-evaluation runs — only unit test updates.

---

## Consequences

- The composite score weights (0.40/0.40/0.20) are constants in `ConfidenceScorer`. If production data shows the weights are miscalibrated, they can be tuned and tested without touching the AI layer.
- Completeness is defined per request type. Adding a new request type requires a corresponding completeness definition in the scorer.
- The 20% weight on LLM confidence means prompt injection attacks that attempt to set `"confidence": 1.0` in the response have limited effect — they can move the composite score by at most 0.20 (and only if completeness and compliance are also high).

---

## Alternatives Rejected

**Raw LLM confidence only.** Rejected because LLM confidence values are not calibrated. A model that returns `"confidence": 0.95` on an empty email body is not reliable for routing.

**Pure rule-based classifier.** Rejected because it cannot handle ambiguous cases or new request types without code changes. The LLM layer handles the generalisation; the rule layer handles the verifiable parts.

**ML-trained classifier on top of LLM output.** Rejected as over-engineering for the current scale. A trained routing model would require labelled data, a training pipeline, and a deployment mechanism — all of which add complexity without a current need. If the review queue grows large enough to generate training data, this could be revisited.
