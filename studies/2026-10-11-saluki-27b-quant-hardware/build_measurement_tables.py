"""Export closed Saluki measurements as CSV and Markdown tables."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics
from pathlib import Path
from typing import Any


STUDY = Path(__file__).resolve().parent
H_DIR = STUDY.parents[3] / "infra/saluki-eval-20261011"
VARIANTS = ["saluki-iq2", "gsq-iq2", "qwen-q4", "qwen-q5"]
VARIANT_LABELS = {"saluki-iq2": "Saluki IQ2-mix", "gsq-iq2": "GSQ IQ2_XS", "qwen-q4": "Q4", "qwen-q5": "Q5"}
HOSTS = [("rtx3090", "RTX3090"), ("ai-max395", "AI Max+395")]
TASKS = ["D01", "C01", "W01", "C02", "A01", "W02", "C03", "A02", "E01", "W03", "R01", "R02"]
REPEATED = {"C03": 3, "A02": 3, "E01": 3}
CSV_FIELDS = [
    "profile", "collection", "folder", "case", "round", "thinking", "accepted", "hard_pass", "editor_score",
    "elapsed_s", "native_prefill_s", "native_decode_s", "prompt_tokens", "completion_tokens", "total_tokens",
    "usage_complete", "native_timings_complete", "first_content_delta_s", "native_cached_tokens", "reasoning_chars_sum", "body_chars", "outcome",
    "error_or_rule_detail", "source", "compatible_accepted", "compatible_hard_pass", "compatible_outcome",
]


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def profile_name(host: str, variant: str) -> str:
    return f"{host}-{variant}"


def state(info: dict[str, Any] | None) -> str:
    if info and info.get("status") == "skipped_resource_limit":
        return "超限未测"
    if info and info.get("status") == "complete":
        return "complete"
    return "待完成"


def fmt(value: Any, suffix: str = "") -> str:
    if isinstance(value, (int, float)):
        return f"{value:.2f}{suffix}" if isinstance(value, float) else f"{value}{suffix}"
    return "未知"


def shown(value: Any) -> str:
    if value is None:
        return "未知/不完整"
    if isinstance(value, bool):
        return "通过" if value else "未通过"
    return str(value)


def shown_seconds(value: Any) -> str:
    return f"{value:.2f}s" if isinstance(value, (int, float)) else "未知/不完整"


def rows_for(summary: dict[str, Any], profile: str, collection: str | None = None, case: str | None = None) -> list[dict[str, Any]]:
    rows = [row for row in summary.get("record_rows", []) if row.get("profile") == profile]
    if collection is not None:
        rows = [row for row in rows if row.get("collection") == collection]
    if case is not None:
        rows = [row for row in rows if row.get("case") == case]
    return rows


def closed_summary(summary: dict[str, Any]) -> bool:
    if summary.get("status") != "complete" or summary.get("in_progress_files"):
        return False
    if not all(info.get("status") in {"complete", "skipped_resource_limit"} for info in summary.get("profiles", {}).values()):
        return False
    return all(
        row.get("editor_review_pending") is not True
        and isinstance(row.get("elapsed_s"), (int, float))
        and bool(row.get("source"))
        for row in summary.get("record_rows", [])
    )


def compatible_closed(compatibility: dict[str, Any] | None) -> bool:
    if not compatibility:
        return True
    if compatibility.get("status") != "complete":
        return False
    profiles = compatibility.get("secondary_profiles", {})
    return all(info.get("status") in {"complete", "skipped_resource_limit"} for info in profiles.values())


def markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    return "\n".join([
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
        *["| " + " | ".join(str(cell).replace("|", "\\|").replace("\n", "<br>") for cell in row) + " |" for row in rows],
    ])


def main_cell(summary: dict[str, Any], profile: str, case: str) -> str:
    info = summary.get("profiles", {}).get(profile)
    if state(info) != "complete":
        return state(info)
    rows = rows_for(summary, profile, "main", case)
    expected = REPEATED.get(case, 1)
    if len(rows) != expected:
        return "待完成"
    accepted = sum(row.get("accepted") is True for row in rows)
    waits = [row.get("elapsed_s") for row in rows]
    median_wait = statistics.median(waits) if all(isinstance(v, (int, float)) for v in waits) else None
    return f"原始通过 {accepted}/{expected}；等待中位 {fmt(median_wait, 's')}"


def metric_cell(summary: dict[str, Any], profile: str, case: str) -> str:
    info = summary.get("profiles", {}).get(profile)
    if state(info) != "complete":
        return state(info)
    rows = rows_for(summary, profile, "main", case)
    expected = REPEATED.get(case, 1)
    if len(rows) != expected:
        return "待完成"
    native_ok = all(row.get("native_timings_complete") is True for row in rows)
    usage_ok = all(row.get("usage_complete") is True for row in rows)
    native_values = [row.get(field) for row in rows for field in ("native_prefill_s", "native_decode_s")]
    token_values = [row.get(field) for row in rows for field in ("prompt_tokens", "completion_tokens", "total_tokens")]
    if not native_ok or not usage_ok or not all(isinstance(x, (int, float)) for x in native_values + token_values):
        return "未知/不完整"
    prefill = statistics.median([row["native_prefill_s"] for row in rows])
    decode = statistics.median([row["native_decode_s"] for row in rows])
    tokens = [statistics.median([row[field] for row in rows]) for field in ("prompt_tokens", "completion_tokens", "total_tokens")]
    return f"预/解 {prefill:.2f}/{decode:.2f}s\n入/出/总 {'/'.join(str(int(x)) for x in tokens)}tok"


def build_csv(summary: dict[str, Any], compatibility: dict[str, Any] | None) -> list[dict[str, Any]]:
    secondary = {}
    if compatibility:
        secondary = {row.get("source"): row for row in compatibility.get("secondary_record_rows", [])}
    output = []
    for row in summary.get("record_rows", []):
        record = {field: row.get(field) for field in CSV_FIELDS}
        alternate = secondary.get(row.get("source")) if row.get("case") == "W02" else None
        if alternate:
            record.update(
                compatible_accepted=alternate.get("accepted"),
                compatible_hard_pass=alternate.get("hard_pass"),
                compatible_outcome=alternate.get("outcome"),
            )
        output.append(record)
    return output


def diagnostic_markdown(summary: dict[str, Any]) -> list[str]:
    profiles = summary.get("profiles", {})
    sections = ["## Profile 总览", markdown_table(
        ["profile", "状态", "主测记录", "接受会话", "completion_rate", "known_main_total_tokens", "资源采样"],
        [[p, state(info), shown(info.get("main_recorded")), shown(info.get("accepted_sessions")), shown(info.get("completion_rate")), shown(info.get("known_main_total_tokens")), shown(info.get("resource_samples"))] for p, info in profiles.items()],
    )]
    sections += ["## 固定512三次探针", markdown_table(
        ["profile", "状态", "decode中位 token/s", "完整等待中位", "采样峰值 bytes"],
        [[p, state(info), shown(info.get("fixed512_decode_median_tokens_per_s")), shown(info.get("fixed512_full_wait_median_s")), shown(info.get("peak_runtime_gpu_allocation_bytes"))] for p, info in profiles.items()],
    )]
    timing_rows = []
    for p in profiles:
        for row in rows_for(summary, p, "timing"):
            repeat = next((label for label in ["new-prefix", "exact-repeat"] if row.get("folder", "").endswith(label)), "未知")
            timing_rows.append([p, row.get("case"), repeat, shown(row.get("first_content_delta_s")), shown(row.get("elapsed_s")), shown(row.get("completion_tokens")), shown(row.get("accepted")), shown(row.get("native_predicted_per_second"))])
    sections += ["## 流式 timing 逐记录诊断", markdown_table(["profile", "档位", "重复", "首正文s", "完整等待s", "生成token", "验收", "原生token/s"], timing_rows)]
    for case in ("O01", "O02", "O03"):
        thinking_rows = []
        for p in profiles:
            cells = [p, state(profiles[p])]
            for mode in (True, False):
                rs = [r for r in rows_for(summary, p, "thinking", case) if r.get("thinking") is mode]
                if state(profiles[p]) != "complete":
                    cells.append(state(profiles[p])); continue
                if len(rs) != 2:
                    cells.append("未知/不完整"); continue
                waits = [r.get("elapsed_s") for r in rs]
                usage_ok = all(r.get("usage_complete") is True for r in rs)
                inputs = [r.get("prompt_tokens") for r in rs]
                outputs = [r.get("completion_tokens") for r in rs]
                wait_median = statistics.median(waits) if all(isinstance(x, (int, float)) for x in waits) else None
                input_median = statistics.median(inputs) if usage_ok and all(isinstance(x, (int, float)) for x in inputs) else None
                output_median = statistics.median(outputs) if usage_ok and all(isinstance(x, (int, float)) for x in outputs) else None
                accepted = sum(r.get("accepted") is True for r in rs)
                cells.append(f"{accepted}/2通过；等待中位 {shown_seconds(wait_median)}；入 {shown(input_median)}；出 {shown(output_median)}")
            thinking_rows.append(cells)
        sections += [f"## {case} 简单题 thinking 开关（各两轮中位）", markdown_table(["profile", "状态", "on", "off"], thinking_rows)]
    complex_rows = []
    for p in profiles:
        for collection in ("thinking-complex", "native-sampling"):
            for row in rows_for(summary, p, collection):
                complex_rows.append([p, collection, row.get("case"), shown(row.get("accepted")), shown(row.get("elapsed_s")), shown(row.get("prompt_tokens")), shown(row.get("completion_tokens")), shown(row.get("native_prefill_s")), shown(row.get("native_decode_s")), shown(row.get("outcome"))])
    sections += ["## 复杂 off / native 逐记录诊断", markdown_table(["profile", "collection", "题目", "验收", "等待s", "输入tok", "生成tok", "prefill s", "decode s", "outcome"], complex_rows)]
    return sections


def build_markdown(summary: dict[str, Any], compatibility: dict[str, Any] | None) -> str:
    lines = [
        "# Saluki 测量表",
        "",
        "数据导出；不替换原始记录。等待为完整会话；重复题等待取各轮中位；通过轮数按 accepted=True；token 仅在 usage_complete 全部为 True 时汇总，未知不补零。",
        "",
    ]
    secondary = {}
    if compatibility:
        secondary = {row.get("source"): row for row in compatibility.get("secondary_record_rows", [])}
    for case in TASKS:
        table_rows = []
        for variant in VARIANTS:
            cells = [VARIANT_LABELS[variant]]
            for host, _ in HOSTS:
                cells.append(main_cell(summary, profile_name(host, variant), case))
            table_rows.append(cells)
        lines += [f"## {case} 主测", markdown_table(["量化", "RTX3090", "AI Max+395"], table_rows), ""]
        metric_rows = []
        for variant in VARIANTS:
            metric_rows.append([VARIANT_LABELS[variant]] + [metric_cell(summary, profile_name(host, variant), case) for host, _ in HOSTS])
        lines += [f"### {case} 实际指标（native 与 usage 均完整才显示）", markdown_table(["量化", "RTX3090", "AI Max+395"], metric_rows), ""]
        if case == "W02" and secondary:
            compat_rows = []
            for variant in VARIANTS:
                cells = [VARIANT_LABELS[variant]]
                for host, _ in HOSTS:
                    profile = profile_name(host, variant)
                    originals = rows_for(summary, profile, "main", "W02")
                    alternate = next((secondary.get(row.get("source")) for row in originals if secondary.get(row.get("source"))), None)
                    if alternate is None:
                        cells.append(state(summary.get("profiles", {}).get(profile)))
                    else:
                        cells.append(f"原始 {'通过' if alternate.get('original_accepted', alternate.get('accepted')) is True else '未通过'}；补算 {'通过' if alternate.get('accepted') is True else '未通过'}")
                compat_rows.append(cells)
            lines += ["### W02 换行兼容补算（旁列）", markdown_table(["量化", "RTX3090", "AI Max+395"], compat_rows), ""]
    lines += diagnostic_markdown(summary)
    return "\n".join(lines) + "\n"


def main(summary_path: Path, compatibility_path: Path | None, output_dir: Path, allow_partial: bool) -> None:
    try:
        if allow_partial:
            output_dir.resolve().relative_to(H_DIR.resolve())
        summary = load(summary_path)
        compatibility = load(compatibility_path) if compatibility_path else None
        if compatibility:
            if compatibility.get("source_summary_sha256") != hashlib.sha256(summary_path.read_bytes()).hexdigest():
                raise ValueError("secondary compatibility summary does not match the supplied primary summary")
        if not allow_partial and (not closed_summary(summary) or not compatible_closed(compatibility)):
            raise ValueError("formal export requires complete summary, complete compatibility, and closed records")
    except ValueError:
        raise
    output_dir.mkdir(parents=True, exist_ok=True)
    records = build_csv(summary, compatibility)
    with (output_dir / "measurement-records.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(records)
    (output_dir / "measurement-tables.md").write_text(build_markdown(summary, compatibility), encoding="utf-8")
    print(json.dumps({"output_dir": str(output_dir), "records": len(records), "formal": not allow_partial}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--compatibility", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--allow-partial", action="store_true")
    args = parser.parse_args()
    main(args.summary.resolve(), args.compatibility.resolve() if args.compatibility else None, args.output_dir.resolve(), args.allow_partial)
