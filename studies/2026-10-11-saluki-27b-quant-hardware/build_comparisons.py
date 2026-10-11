"""Build pairwise, measurement-only comparisons from a build_summary artifact.

The script does not run models or assign scores.  Formal pairwise gate results
require a complete summary; ``--allow-partial`` is intended for a private
working directory while collection is in progress.
"""

from __future__ import annotations

import argparse
import itertools
import json
import statistics
from pathlib import Path
from typing import Any


STUDY = Path(__file__).resolve().parent
MAIN_ORDER = [
    ("D01", 1), ("C01", 1), ("W01", 1), ("C02", 1), ("A01", 1),
    ("W02", 1), ("C03", 1), ("C03", 2), ("C03", 3),
    ("A02", 1), ("A02", 2), ("A02", 3),
    ("E01", 1), ("E01", 2), ("E01", 3), ("W03", 1),
    ("R01", 1), ("R02", 1),
]
ROW_FIELDS = [
    "profile", "collection", "case", "round", "thinking", "accepted",
    "full_wait_s", "native_prefill_s", "native_decode_s",
    "prompt_tokens", "completion_tokens", "total_tokens", "editor_score",
    "body_chars", "outcome", "usage_complete", "hard_pass",
    "error_or_rule_detail", "source",
]


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def compact_row(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    result = {field: row.get(field) for field in ROW_FIELDS}
    result["full_wait_s"] = row.get("elapsed_s")
    return result


def profile_pairs(profiles: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    pairs: list[dict[str, Any]] = []
    for axis, key in (("same_hardware", "host"), ("same_quantization", "variant")):
        groups: dict[str, list[str]] = {}
        for profile, info in profiles.items():
            groups.setdefault(info[key], []).append(profile)
        for group, members in groups.items():
            for left, right in itertools.combinations(sorted(members), 2):
                pairs.append({"axis": axis, "group": group, "left": left, "right": right})
    return pairs


def gate_for_pair(
    left: str,
    right: str,
    profiles: dict[str, dict[str, Any]],
    aligned: list[dict[str, Any]],
    gate: dict[str, Any],
) -> dict[str, Any]:
    left_info, right_info = profiles[left], profiles[right]
    complete_statuses = {"complete"}
    available = left_info.get("status") in complete_statuses and right_info.get("status") in complete_statuses
    ratios = [row["full_wait_ratio_larger_over_smaller"] for row in aligned if row["full_wait_ratio_larger_over_smaller"] is not None]
    if available:
        assert len(aligned) == len(ratios) == 18, "complete profiles require all 18 timing pairs"
        assert all(row['left'] is not None and row['right'] is not None for row in aligned)
    median_ratio = statistics.median(ratios) if ratios else None
    completion_ok = (
        left_info.get("completion_rate") is not None
        and right_info.get("completion_rate") is not None
        and left_info["completion_rate"] >= gate["minimum_completion_rate_each"]
        and right_info["completion_rate"] >= gate["minimum_completion_rate_each"]
    )
    basic_ok = left_info.get("basic_all_pass") is True and right_info.get("basic_all_pass") is True
    ratio_ok = median_ratio is not None and median_ratio <= gate["maximum_median_paired_wall_ratio"]
    if not available:
        decision = "unavailable"
    else:
        decision = "pass" if completion_ok and basic_ok and ratio_ok else "fail"
    return {
        "decision": decision,
        "availability": "available" if available else "unavailable",
        "completion_rate_gate": completion_ok if available else None,
        "basic_tasks_gate": basic_ok if available else None,
        "median_full_wait_ratio_gate": ratio_ok if available else None,
        "left_completion_rate": left_info.get("completion_rate") if available else None,
        "right_completion_rate": right_info.get("completion_rate") if available else None,
        "left_basic_all_pass": left_info.get("basic_all_pass") if available else None,
        "right_basic_all_pass": right_info.get("basic_all_pass") if available else None,
        "median_full_wait_ratio": median_ratio if available else None,
        "ratio_count": len(ratios) if available else None,
        "thresholds": {
            "minimum_completion_rate_each": gate["minimum_completion_rate_each"],
            "maximum_median_paired_wall_ratio": gate["maximum_median_paired_wall_ratio"],
            "basic_tasks_all_required": gate["basic_tasks_all_required"],
        },
    }


def diagnostics(rows: list[dict[str, Any]], profile: str) -> dict[str, list[dict[str, Any]]]:
    selected = [row for row in rows if row.get("profile") == profile]
    return {
        "simple_thinking_on_off": [
            compact_row(row) for row in selected
            if row.get("collection") == "thinking" and row.get("case") in {"O01", "O02", "O03"}
        ],
        "writing_off": [
            compact_row(row) for row in selected
            if row.get("collection") == "thinking-complex" and row.get("case") in {"W01", "W02", "W03"}
        ],
        "complex_off": [
            compact_row(row) for row in selected
            if row.get("collection") == "thinking-complex" and row.get("case") in {"C01", "C03"}
        ],
        "native_sampling": [
            compact_row(row) for row in selected if row.get("collection") == "native-sampling"
        ],
    }


def build(summary: dict[str, Any], gate: dict[str, Any], allow_partial: bool) -> dict[str, Any]:
    if summary.get("status") != "complete" and not allow_partial:
        raise ValueError(
            "formal comparisons require summary.status=complete; use --allow-partial only for a private output"
        )
    profiles = summary.get("profiles")
    rows = summary.get("record_rows")
    if not isinstance(profiles, dict) or not isinstance(rows, list):
        raise ValueError("summary schema must contain profiles and record_rows")
    if summary.get('status')=='complete':
        assert all(x['status'] in ['complete','skipped_resource_limit'] for x in profiles.values())

    row_map: dict[tuple[str, str, int], dict[str, Any]] = {}
    for row in rows:
        if row.get("collection") != "main":
            continue
        key = (row.get("profile"), row.get("case"), row.get("round"))
        if key in row_map:
            raise ValueError(f"duplicate main identity in summary: {key}")
        row_map[key] = row

    comparisons = []
    for pair in profile_pairs(profiles):
        aligned = []
        for case, round_ in MAIN_ORDER:
            left = compact_row(row_map.get((pair["left"], case, round_)))
            right = compact_row(row_map.get((pair["right"], case, round_)))
            left_wait = left.get("full_wait_s") if left else None
            right_wait = right.get("full_wait_s") if right else None
            ratio = None
            larger = smaller = None
            if isinstance(left_wait, (int, float)) and isinstance(right_wait, (int, float)) and min(left_wait, right_wait) > 0:
                larger, smaller = max(left_wait, right_wait), min(left_wait, right_wait)
                ratio = larger / smaller
            aligned.append({
                "case": case,
                "round": round_,
                "left": left,
                "right": right,
                "full_wait_larger_s": larger,
                "full_wait_smaller_s": smaller,
                "full_wait_ratio_larger_over_smaller": ratio,
            })
        comparisons.append({
            **pair,
            "main_alignment_count": len(aligned),
            "gate": gate_for_pair(pair["left"], pair["right"], profiles, aligned, gate),
            "main_task_rows": aligned,
        })

    return {
        "study": summary.get("frozen_study"),
        "source_summary_status": summary.get("status"),
        "formal_comparisons": summary.get("status") == "complete",
        "allow_partial": allow_partial,
        "gate_source": "acceptance-gate.json",
        "gate": gate,
        "comparisons": comparisons,
        "profile_diagnostics": {
            profile: diagnostics(rows, profile) for profile in profiles
        },
        "profile_status": {
            profile: {
                "host": info.get("host"),
                "variant": info.get("variant"),
                "status": info.get("status"),
            }
            for profile, info in profiles.items()
        },
        "no_overall_score_or_recommendation": True,
    }


def main(summary_path: Path, output_path: Path, allow_partial: bool) -> None:
    summary = load(summary_path)
    gate = load(STUDY / "acceptance-gate.json")
    document = build(summary, gate, allow_partial)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(output_path),
        "formal_comparisons": document["formal_comparisons"],
        "comparison_count": len(document["comparisons"]),
    }, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-partial", action="store_true")
    args = parser.parse_args()
    main(args.summary.resolve(), args.output.resolve(), args.allow_partial)
