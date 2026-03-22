#!/usr/bin/env python3
"""Evaluation pipeline for the ops workflow extraction system.

Loads test cases from eval/test_set.jsonl, runs each through the
ExtractionService, compares results to expected values, and writes a
structured JSON report to eval/results/eval_YYYY-MM-DD.json.

Usage:
    python eval/evaluate.py
    AI_PROVIDER=anthropic ANTHROPIC_API_KEY=sk-... python eval/evaluate.py
    python eval/evaluate.py --test-set eval/test_set.jsonl
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Project root on path so app modules import correctly.
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import get_settings  # noqa: E402
from app.core.exceptions import BaseAppError  # noqa: E402
from app.models.email import Extraction, InboxMessage  # noqa: E402
from app.services.ai.client import DailyCostTracker, get_ai_client  # noqa: E402
from app.services.ai.prompts import VERSION as PROMPT_VERSION  # noqa: E402
from app.services.extraction_service import ExtractionService  # noqa: E402

EVAL_DIR = Path(__file__).parent
RESULTS_DIR = EVAL_DIR / "results"
DEFAULT_TEST_SET = EVAL_DIR / "test_set.jsonl"

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def _load_test_cases(path: Path) -> list[dict[str, Any]]:
    """Load test cases from a JSONL file.

    Args:
        path: Path to the .jsonl file.

    Returns:
        List of test case dicts.

    Raises:
        SystemExit: If the file does not exist or contains invalid JSON.
    """
    if not path.exists():
        sys.exit(f"Test set not found: {path}")
    cases = []
    for line_number, raw_line in enumerate(path.read_text().splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            cases.append(json.loads(line))
        except json.JSONDecodeError as exc:
            sys.exit(f"Invalid JSON on line {line_number} of {path}: {exc}")
    return cases


def _build_message(case_id: str, case_input: dict[str, Any], received_at: datetime) -> InboxMessage:
    """Construct an InboxMessage from a test case input dict.

    Args:
        case_id: Test case identifier (used as message_id).
        case_input: Dict with from_name, from_email, subject, body keys.
        received_at: Timestamp to assign to the message.

    Returns:
        Validated InboxMessage.
    """
    return InboxMessage(
        message_id=f"eval_{case_id}",
        **{
            "from": {
                "name": case_input.get("from_name", "Eval User"),
                "email": case_input.get("from_email", "eval@example.com"),
            }
        },
        subject=case_input.get("subject", ""),
        received_at=received_at,
        body=case_input.get("body", ""),
    )


# ---------------------------------------------------------------------------
# Field comparison
# ---------------------------------------------------------------------------


def _compare_fields(extraction: Extraction, expected: dict[str, Any]) -> dict[str, bool | None]:
    """Compare extracted fields against expected values.

    Returns a dict mapping field name to True/False/None where None means
    the expected value was not specified for that field.

    Args:
        extraction: Completed Extraction from the pipeline.
        expected: Expected values dict from the test case.

    Returns:
        Per-field match results.
    """
    results: dict[str, bool | None] = {
        "request_type": extraction.request_type == expected.get("request_type"),
        "priority": extraction.priority == expected.get("priority")
        if "priority" in expected
        else None,
        "company_present": None,
        "has_line_items": None,
    }
    if "company_present" in expected:
        results["company_present"] = bool(extraction.company) == expected["company_present"]
    if "has_line_items" in expected:
        results["has_line_items"] = bool(extraction.line_items) == expected["has_line_items"]
    return results


# ---------------------------------------------------------------------------
# Single-case runner
# ---------------------------------------------------------------------------


async def _run_case(
    svc: ExtractionService,
    cost_tracker: DailyCostTracker,
    case: dict[str, Any],
    received_at: datetime,
) -> dict[str, Any]:
    """Run a single test case and return a structured result dict.

    Args:
        svc: ExtractionService configured with the target AI provider.
        cost_tracker: Shared cost accumulator (read after each call).
        case: Test case dict with id, input, and expected keys.
        received_at: Timestamp to embed in the InboxMessage.

    Returns:
        Result dict with passed, field_matches, extracted values, and metrics.
    """
    expected = case["expected"]
    cost_before = cost_tracker.total_today()
    t_start = time.monotonic()

    try:
        message = _build_message(case["id"], case["input"], received_at)
        extraction = await svc.extract(message)
        latency_ms = (time.monotonic() - t_start) * 1000
        cost_usd = cost_tracker.total_today() - cost_before
        field_matches = _compare_fields(extraction, expected)
        return {
            "case_id": case["id"],
            "category": case.get("category", "unknown"),
            "passed": field_matches.get("request_type") is True,
            "field_matches": {k: v for k, v in field_matches.items() if v is not None},
            "extracted": {
                "request_type": extraction.request_type,
                "priority": extraction.priority,
                "company": extraction.company,
                "has_line_items": bool(extraction.line_items),
                "confidence": extraction.confidence,
            },
            "expected": expected,
            "confidence": extraction.confidence,
            "latency_ms": round(latency_ms, 1),
            "cost_usd": round(cost_usd, 6),
            "error": None,
        }
    except (BaseAppError, Exception) as exc:
        latency_ms = (time.monotonic() - t_start) * 1000
        logger.warning("Case %s failed: %s", case["id"], exc)
        return {
            "case_id": case["id"],
            "category": case.get("category", "unknown"),
            "passed": False,
            "field_matches": {},
            "extracted": None,
            "expected": expected,
            "confidence": 0.0,
            "latency_ms": round(latency_ms, 1),
            "cost_usd": 0.0,
            "error": str(exc),
        }


# ---------------------------------------------------------------------------
# Metrics aggregation
# ---------------------------------------------------------------------------


def _compute_field_accuracy(results: list[dict[str, Any]]) -> dict[str, float]:
    """Compute per-field accuracy across all results.

    Only counts cases where the field was specified in expected.

    Args:
        results: List of case result dicts.

    Returns:
        Dict of field_name → accuracy fraction in [0.0, 1.0].
    """
    totals: dict[str, int] = {}
    matches: dict[str, int] = {}
    for result in results:
        for field, matched in result.get("field_matches", {}).items():
            totals[field] = totals.get(field, 0) + 1
            if matched:
                matches[field] = matches.get(field, 0) + 1
    return {
        field: round(matches.get(field, 0) / total, 4)
        for field, total in totals.items()
        if total > 0
    }


def _build_report(
    results: list[dict[str, Any]],
    model: str,
    prompt_version: str,
) -> dict[str, Any]:
    """Aggregate case results into the final evaluation report.

    Args:
        results: List of case result dicts from _run_case.
        model: AI model identifier used during the run.
        prompt_version: Prompt template version used.

    Returns:
        Structured report dict matching the documented report schema.
    """
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    confidences = [r["confidence"] for r in results]
    latencies = [r["latency_ms"] for r in results]
    costs = [r["cost_usd"] for r in results]
    field_accuracy = _compute_field_accuracy(results)
    overall_accuracy = (
        round(sum(field_accuracy.values()) / len(field_accuracy), 4) if field_accuracy else 0.0
    )
    return {
        "timestamp": datetime.now(UTC).isoformat(),
        "model": model,
        "prompt_version": prompt_version,
        "test_cases": total,
        "overall_accuracy": overall_accuracy,
        "pass_rate": round(passed / total, 4) if total else 0.0,
        "field_accuracy": field_accuracy,
        "avg_confidence": round(sum(confidences) / total, 4) if total else 0.0,
        "avg_latency_ms": round(sum(latencies) / total, 1) if total else 0.0,
        "avg_cost_per_item_usd": round(sum(costs) / total, 6) if total else 0.0,
        "total_cost_usd": round(sum(costs), 6),
        "passes": passed,
        "failures": total - passed,
        "by_category": _summarise_by_category(results),
        "cases": results,
    }


def _summarise_by_category(results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Compute pass rate and count per category.

    Args:
        results: List of case result dicts.

    Returns:
        Dict of category → {total, passed, pass_rate}.
    """
    categories: dict[str, list[bool]] = {}
    for result in results:
        cat = result["category"]
        categories.setdefault(cat, []).append(result["passed"])
    return {
        cat: {
            "total": len(passed_list),
            "passed": sum(passed_list),
            "pass_rate": round(sum(passed_list) / len(passed_list), 4),
        }
        for cat, passed_list in sorted(categories.items())
    }


def _write_report(report: dict[str, Any]) -> Path:
    """Write the report JSON to eval/results/eval_YYYY-MM-DD.json.

    Args:
        report: Completed report dict.

    Returns:
        Path to the written file.
    """
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    date_tag = datetime.now(UTC).strftime("%Y-%m-%d")
    output_path = RESULTS_DIR / f"eval_{date_tag}.json"
    output_path.write_text(json.dumps(report, indent=2))
    return output_path


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def run_eval(test_set_path: Path) -> dict[str, Any]:
    """Load test cases, run the extraction pipeline, and return the report.

    Args:
        test_set_path: Path to the JSONL test set file.

    Returns:
        Completed evaluation report dict.
    """
    settings = get_settings()
    cost_tracker = DailyCostTracker()
    ai_client = get_ai_client(settings, cost_tracker=cost_tracker)
    model = settings.ai_model if settings.ai_provider == "anthropic" else "mock"
    svc = ExtractionService(ai_client=ai_client)

    test_cases = _load_test_cases(test_set_path)
    received_at = datetime.now(UTC)

    print(
        f"Running {len(test_cases)} test cases with provider={settings.ai_provider!r} model={model!r}"
    )

    tasks = [_run_case(svc, cost_tracker, case, received_at) for case in test_cases]
    results = await asyncio.gather(*tasks)

    return _build_report(list(results), model=model, prompt_version=PROMPT_VERSION)


def main() -> None:
    """CLI entry point — parse args, run evaluation, print summary."""
    parser = argparse.ArgumentParser(description="Run the extraction evaluation pipeline")
    parser.add_argument(
        "--test-set",
        type=Path,
        default=DEFAULT_TEST_SET,
        help="Path to test_set.jsonl (default: eval/test_set.jsonl)",
    )
    args = parser.parse_args()

    report = asyncio.run(run_eval(args.test_set))
    output_path = _write_report(report)

    print(f"\n{'=' * 60}")
    print(f"  Evaluation complete — {report['test_cases']} cases")
    print(f"{'=' * 60}")
    print(
        f"  Pass rate        : {report['pass_rate']:.1%}  ({report['passes']}/{report['test_cases']})"
    )
    print(f"  Overall accuracy : {report['overall_accuracy']:.1%}")
    print(f"  Avg confidence   : {report['avg_confidence']:.3f}")
    print(f"  Avg latency      : {report['avg_latency_ms']:.0f} ms")
    print(f"  Total cost       : ${report['total_cost_usd']:.4f}")
    print("\n  Field accuracy:")
    for field, acc in report["field_accuracy"].items():
        print(f"    {field:<20} {acc:.1%}")
    print("\n  By category:")
    for cat, summary in report["by_category"].items():
        print(f"    {cat:<22} {summary['passed']}/{summary['total']} ({summary['pass_rate']:.0%})")
    print(f"\n  Report written to: {output_path}")


if __name__ == "__main__":
    main()
