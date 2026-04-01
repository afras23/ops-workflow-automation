"""Reusable evaluation metric helpers for the extraction pipeline."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any


def exact_match_accuracy(matches: Iterable[bool]) -> float:
    """Compute exact-match accuracy for a sequence of boolean outcomes.

    Args:
        matches: Iterable of booleans where True indicates a correct prediction.

    Returns:
        Accuracy as a fraction in \[0.0, 1.0]. Returns 0.0 if the iterable
        is empty.
    """
    match_list = [matched for matched in matches]
    if not match_list:
        return 0.0
    correct_count = sum(1 for matched in match_list if matched)
    return round(correct_count / len(match_list), 4)


def partial_match_score(expected: str, predicted: str) -> float:
    """Score similarity between two short texts using token overlap.

    The score is a symmetric overlap ratio based on unique, lowercased
    whitespace-delimited tokens:

    score = |intersection(expected_tokens, predicted_tokens)|
            / |union(expected_tokens, predicted_tokens)|

    Args:
        expected: Ground-truth string.
        predicted: Model-predicted string.

    Returns:
        Similarity score in \[0.0, 1.0]. Returns 1.0 if both strings are empty.
    """
    expected_tokens = {token for token in expected.lower().split() if token}
    predicted_tokens = {token for token in predicted.lower().split() if token}
    if not expected_tokens and not predicted_tokens:
        return 1.0
    if not expected_tokens or not predicted_tokens:
        return 0.0
    intersection_size = len(expected_tokens & predicted_tokens)
    union_size = len(expected_tokens | predicted_tokens)
    return round(intersection_size / union_size, 4)


def field_level_accuracy(results: list[dict[str, Any]]) -> dict[str, float]:
    """Compute per-field exact-match accuracy across evaluation results.

    This function expects each result dict to contain a ``field_matches``
    mapping of ``field_name -> bool`` for any field where an explicit
    expected value was provided in the test set.

    Args:
        results: List of per-case result dictionaries emitted by the
            evaluation runner.

    Returns:
        Mapping of field name to accuracy fraction in \[0.0, 1.0].
    """
    totals: dict[str, int] = {}
    matches: dict[str, int] = {}

    for case_result in results:
        for field_name, matched in case_result.get("field_matches", {}).items():
            totals[field_name] = totals.get(field_name, 0) + 1
            if matched:
                matches[field_name] = matches.get(field_name, 0) + 1

    return {
        field_name: round(matches.get(field_name, 0) / total_count, 4)
        for field_name, total_count in totals.items()
        if total_count > 0
    }

