# Problem Definition

## Business Context

Operations teams in small-to-medium organisations receive a continuous stream of unstructured email requests: procurement approvals, system change requests, customer issue reports, and general inquiries. These emails arrive in a shared inbox, are read by an analyst or coordinator, manually categorised, and routed to the appropriate team or system.

The manual process has predictable failure modes that worsen as the volume grows:

**Classification inconsistency.** Different team members apply different criteria for what counts as "urgent" or what constitutes a "purchase request" versus a "general inquiry." The same email sent by two different senders may be routed differently depending on who reads it and when.

**No structured audit trail.** Approval decisions live in email threads or in the memory of the person who processed the request. When a purchase order or system change is later questioned, there is no reliable record of who approved it, what information they had at the time, or what the original request said.

**Human bottleneck on high-confidence cases.** A substantial fraction of incoming requests are straightforward — a well-formed purchase order with a company name, itemised list, and due date, or a clearly-described production incident. These cases do not need human review, but they go through the same manual queue as ambiguous cases.

**Latency on urgent issues.** A P1 incident report buried in an inbox may sit unprocessed for minutes or hours. The manual process has no mechanism to prioritise routing based on content.

---

## The Specific Problem This System Solves

This system addresses the structured intake problem: getting an unstructured email into a structured, actionable record with a routing decision and audit trail, as fast as possible.

It does not replace human judgement for ambiguous cases — it explicitly preserves human review for low-confidence extractions. The goal is to eliminate human effort on the high-confidence cases (estimated at 40–60% of volume in a typical ops inbox) and give reviewers better tooling for the rest.

**Scope:** Ingestion, extraction, confidence-scored routing, and audit logging. Out of scope: downstream integrations (actual ticketing system writes, Slack notifications to channels, email replies). The system produces structured records and a review queue; what happens after approval is a separate concern.

---

## Success Criteria

1. **Throughput:** Process 100+ emails per minute without degradation (the batch endpoint enables this at the infrastructure level).
2. **Classification accuracy:** ≥ 85% request\_type accuracy on a representative test set with a production LLM.
3. **Cost control:** Total AI cost per item ≤ $0.002 (approximately one half-page email processed via Claude Haiku).
4. **Latency:** P95 extraction latency ≤ 3 seconds for single-item ingestion.
5. **Audit completeness:** Every state change (ingestion, routing, approval, rejection) recorded with actor, timestamp, and reason.
6. **Safety:** Prompt injection attempts classified as `other` with low confidence, not executed as instructions.

---

## What This Is Not

- A general-purpose email automation platform. The extraction schema is specific to this ops intake use case.
- A replacement for a proper ticketing system. The review queue is a lightweight holding area; production usage would integrate with Jira, Linear, or similar.
- A zero-human system. The confidence routing is designed to surface ambiguous cases to humans, not eliminate human oversight entirely.
