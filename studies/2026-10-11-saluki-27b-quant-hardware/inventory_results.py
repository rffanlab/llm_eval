"""Inventory recorded Saluki study results without scoring missing work as zero.

This is deliberately offline: it reads the frozen study metadata and result.json
recordings only.  Use ``--output-dir`` for generated files so an empty inventory
can be checked in a temporary directory without creating public artifacts.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Iterable


LEDGER_FIELDS = [
    "profile",
    "kind",
    "case",
    "round",
    "thinking",
    "elapsed_s",
    "usage_complete",
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "hard_pass",
    "editor_review_pending",
    "reasoning_chars_sum",
    "native_timings_complete",
    "native_prompt_n",
    "native_prompt_ms",
    "native_predicted_n",
    "native_predicted_ms",
    "native_predicted_per_second",
    "first_content_delta_s",
    "error",
]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def number(value: Any) -> int | float | None:
    # bool is not a measurement, even though it is an int subclass.
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def sum_field(items: Iterable[dict[str, Any]], key: str) -> int | float | None:
    values = [number(item.get(key)) for item in items]
    values = [value for value in values if value is not None]
    return sum(values) if values else None


def result_files(study: Path) -> list[Path]:
    """Only accept the frozen runner layout: kind/profile/case/result.json."""
    files = []
    for path in study.rglob("result.json"):
        relative = path.relative_to(study)
        if len(relative.parts) == 4 and relative.parts[-1] == "result.json":
            files.append(path)
    return sorted(files)


def native_measurements(record: dict[str, Any]) -> dict[str, int | float | None]:
    """Aggregate per-turn native timings, preserving unknowns as blank.

    A multi-turn Agent row sums token counts and milliseconds.  Its rate is
    derived once from those sums; per-turn rates are never added together.
    """
    turns = record.get("turns")
    if not isinstance(turns, list):
        turns = []
    required = ("prompt_n", "prompt_ms", "predicted_n", "predicted_ms")
    timings = [turn.get("timings") for turn in turns if isinstance(turn, dict)]
    complete = bool(turns) and all(
        isinstance(timing, dict) and all(number(timing.get(key)) is not None for key in required)
        for timing in timings
    )
    if not complete:
        return {
            "native_timings_complete": None if not turns else False,
            "native_prompt_n": None,
            "native_prompt_ms": None,
            "native_predicted_n": None,
            "native_predicted_ms": None,
            "native_predicted_per_second": None,
        }
    prompt_n = sum_field(timings, "prompt_n")
    prompt_ms = sum_field(timings, "prompt_ms")
    predicted_n = sum_field(timings, "predicted_n")
    predicted_ms = sum_field(timings, "predicted_ms")
    rate = None
    if predicted_n is not None and predicted_ms is not None and predicted_ms > 0:
        rate = predicted_n / predicted_ms * 1000
    return {
        "native_timings_complete": True,
        "native_prompt_n": prompt_n,
        "native_prompt_ms": prompt_ms,
        "native_predicted_n": predicted_n,
        "native_predicted_ms": predicted_ms,
        "native_predicted_per_second": rate,
    }


def ledger_row(path: Path, record: dict[str, Any]) -> dict[str, Any]:
    relative = path.relative_to(path.parents[3]).parts
    # relative is kind/profile/case/result.json; the study root is parents[3].
    kind, profile, folder_case = relative[:3]
    turns = record.get("turns")
    turns = turns if isinstance(turns, list) else []
    usage = record.get("usage")
    # run_case initializes aggregate counters to zero before the first API
    # response.  With no completed turn those zeros mean "unknown", not zero
    # billed/generated tokens.
    if not turns and record.get("usage_complete") is not True:
        usage = {}
    usage = usage if isinstance(usage, dict) else {}
    reasoning_values = [
        number(turn.get("reasoning_chars"))
        for turn in turns
        if isinstance(turn, dict)
    ]
    reasoning_values = [value for value in reasoning_values if value is not None]
    grade = record.get("grade") if isinstance(record.get("grade"), dict) else {}
    hard_pass = grade.get("pass")
    if hard_pass is None and "full_512_output" in grade:
        hard_pass = grade["full_512_output"]
    row = {
        "profile": profile,
        "kind": kind,
        "case": record.get("case") or folder_case,
        "round": record.get("round"),
        "thinking": record.get("thinking"),
        "elapsed_s": record.get("elapsed_s"),
        "usage_complete": record.get("usage_complete"),
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
        "hard_pass": hard_pass,
        "editor_review_pending": grade.get("editor_review_pending", False),
        "reasoning_chars_sum": sum(reasoning_values) if reasoning_values else None,
        "first_content_delta_s": record.get("first_content_delta_s"),
        "error": record.get("error"),
    }
    row.update(native_measurements(record))
    return {field: row.get(field) for field in LEDGER_FIELDS}


def main(study: Path, output_dir: Path) -> None:
    # Reading both frozen files is intentional: profiles and main identities are
    # taken only from freeze.json, while models.json is validated as frozen input.
    frozen = load_json(study / "freeze.json")
    models = load_json(study / "models.json")
    if not isinstance(frozen, dict) or not isinstance(models, list):
        raise ValueError("invalid freeze.json/models.json shape")

    profiles = [
        f"{host}-{model}"
        for host in frozen.get("hosts_order", [])
        for model in frozen.get("profiles_order", [])
    ]
    expected_main = [
        {"case": item[0], "round": item[1]}
        for item in frozen.get("main_order", [])
    ]
    rows = []
    parse_errors = []
    for path in result_files(study):
        try:
            record = load_json(path)
            if not isinstance(record, dict):
                raise ValueError("result is not an object")
            rows.append(ledger_row(path, record))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            parse_errors.append({"file": path.relative_to(study).as_posix(), "error": str(exc)})

    counts: dict[str, dict[str, Any]] = {}
    for profile in profiles:
        profile_rows = [row for row in rows if row["profile"] == profile]
        main_rows = [row for row in profile_rows if row["kind"] == "main"]
        recorded = {(row["case"], row["round"]) for row in main_rows}
        missing = [item for item in expected_main if (item["case"], item["round"]) not in recorded]
        counts[profile] = {
            "records": len(profile_rows),
            "by_kind": {
                kind: sum(row["kind"] == kind for row in profile_rows)
                for kind in sorted({row["kind"] for row in profile_rows})
            },
            "main_recorded": len(main_rows),
            "main_expected": len(expected_main),
            "missing_main": missing,
        }

    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "measurement-ledger.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=LEDGER_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "study": frozen.get("study"),
        "status": "no_results" if not rows and not parse_errors else "inventory_only",
        "profiles": profiles,
        "models_declared": [model.get("id") for model in models if isinstance(model, dict)],
        "record_count": len(rows),
        "parse_errors": parse_errors,
        "counts": counts,
        "main_order_source": "freeze.json:main_order",
        "missing_records_are_unknown": True,
        "editor_review_scores_included": False,
        "native_rate_definition": "derived as summed native_predicted_n / summed native_predicted_ms * 1000; per-turn rates are not added",
    }
    (output_dir / "inventory-results.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    main(args.study.resolve(), args.output_dir.resolve())
