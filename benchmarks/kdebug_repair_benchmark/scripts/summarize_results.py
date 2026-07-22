#!/usr/bin/env python3
"""Create a Chinese Markdown summary from benchmark results.csv."""

import argparse
import csv
import statistics
from collections import defaultdict
from pathlib import Path


MODELS = ["gpt-5.5", "glm-4.7", "qwen3.6-35b"]
GROUPS = ["with_kdebug", "without_kdebug"]
GROUP_LABEL = {
    "with_kdebug": "使用 kdebug",
    "without_kdebug": "不使用 kdebug",
}
STATUS_LABEL = {
    "PASS": "通过",
    "TIMEOUT": "未修通（1 小时超时）",
    "RULE_VIOLATION": "规则违规/无效",
    "TOOL_EVIDENCE_MISSING": "工具证据缺失",
    "TOOL_EVIDENCE_INVALID": "工具证据无效",
    "INFRA_ERROR": "基础设施异常",
    "FAIL": "基础设施异常",
    "RETRY_LATER": "限流/接口异常，待重试",
    "missing": "缺失",
}


def as_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def median(values):
    nums = [as_float(v) for v in values if str(v) != ""]
    return statistics.median(nums) if nums else 0.0


def status_text(value):
    return STATUS_LABEL.get(value, value or "")


def summarize(rows):
    total = len(rows)
    passed = sum(1 for r in rows if r.get("final_status") == "PASS")
    timeout = sum(1 for r in rows if r.get("final_status") == "TIMEOUT")
    missing = sum(1 for r in rows if r.get("final_status") == "TOOL_EVIDENCE_MISSING")
    invalid = sum(1 for r in rows if r.get("final_status") == "TOOL_EVIDENCE_INVALID")
    rule = sum(1 for r in rows if r.get("final_status") == "RULE_VIOLATION")
    retry = sum(1 for r in rows if r.get("final_status") == "RETRY_LATER")
    infra = total - passed - timeout - missing - invalid - rule - retry
    valid_total = passed + timeout
    pass_elapsed = [r.get("elapsed_sec") for r in rows if r.get("final_status") == "PASS"]
    tokens = [r.get("token_total") for r in rows if r.get("token_total")]
    return {
        "total": total,
        "passed": passed,
        "timeout": timeout,
        "missing": missing,
        "invalid": invalid,
        "rule": rule,
        "retry": retry,
        "infra": infra,
        "rate": passed / valid_total * 100.0 if valid_total else 0.0,
        "median_elapsed": median(pass_elapsed),
        "median_tokens": median(tokens),
    }


def add_summary_table(lines, title, rows, key_fields):
    lines.append(f"## {title}")
    lines.append("")
    header = key_fields + [
        "Trial 数",
        "PASS",
        "未修通（TIMEOUT）",
        "证据缺失",
        "证据无效",
        "规则违规",
        "限流待重试",
        "基础设施异常",
        "有效成功率",
        "PASS 中位耗时",
        "Token 中位数",
    ]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("|" + "|".join(["---"] * len(header)) + "|")

    groups = defaultdict(list)
    for row in rows:
        key = tuple(row.get(field, "") for field in key_fields)
        groups[key].append(row)

    for key in sorted(groups):
        stats = summarize(groups[key])
        cells = list(key) + [
            str(stats["total"]),
            str(stats["passed"]),
            str(stats["timeout"]),
            str(stats["missing"]),
            str(stats["invalid"]),
            str(stats["rule"]),
            str(stats["retry"]),
            str(stats["infra"]),
            f"{stats['rate']:.1f}%",
            f"{stats['median_elapsed']:.2f}s" if stats["passed"] else "",
            f"{stats['median_tokens']:.0f}",
        ]
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")


def trial_cell(row):
    if not row:
        return "缺失"
    status = status_text(row.get("final_status", ""))
    elapsed = as_float(row.get("elapsed_sec"))
    return (
        f"{status}, {elapsed:.2f}s, iter={row.get('iterations', '')}, "
        f"token={row.get('token_total', '')}, repair={row.get('repair_class', '')}, "
        f"evidence_present={row.get('tool_evidence_present', '')}, "
        f"evidence_valid={row.get('tool_evidence_valid', '')}"
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("results_csv", type=Path)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    rows = list(csv.DictReader(args.results_csv.open(newline="", encoding="utf-8")))

    lines = [
        "# KDebug XiangShan Benchmark 汇总",
        "",
        (
            "本汇总按模型、工具组、bug 域和 benchmark 层级统计。"
            "`no_patch`、`build_fail`、`run_fail`、`judge_fail` 只作为 repair loop 的中间反馈；"
            "模型可以继续修改并重新 build/run，只有在 3600 秒内仍未让原 fail workload 通过时，"
            "才记为 `TIMEOUT`。API 限流、接口无响应等单次尝试先记为 `RETRY_LATER`；"
            "但同一模型、工具组、case 的多次 `RETRY_LATER` 累计耗时超过 3600 秒后，也按预算耗尽记为 `TIMEOUT`。"
            "runner 崩溃、脚本兼容性等仍属于基础设施问题，不计入有效模型失败率。"
        ),
        "",
    ]

    add_summary_table(lines, "模型与工具组", rows, ["model_id", "group"])
    add_summary_table(lines, "按 bug 域拆分", rows, ["bug_domain", "model_id", "group"])
    add_summary_table(lines, "按 benchmark 层拆分", rows, ["benchmark_layer", "model_id", "group"])

    lines.append("## 逐 Case 结果")
    lines.append("")
    lines.append("| Case | Bug 域 | 层级 | 子系统 | 模型 | 使用 kdebug | 不使用 kdebug |")
    lines.append("|---|---|---|---|---|---|---|")

    case_ids = sorted({r.get("case_id", "") for r in rows if r.get("case_id")})
    for case_id in case_ids:
        for model in MODELS:
            case_rows = [
                r for r in rows
                if r.get("case_id") == case_id and r.get("model_id") == model
            ]
            if not case_rows:
                continue
            first = case_rows[0]
            by_group = {r.get("group"): r for r in case_rows}
            lines.append(
                f"| {case_id} | {first.get('bug_domain','')} | "
                f"{first.get('benchmark_layer','') or first.get('layer','')} | "
                f"{first.get('subsystem','')} | {model} | "
                f"{trial_cell(by_group.get('with_kdebug'))} | "
                f"{trial_cell(by_group.get('without_kdebug'))} |"
            )

    text = "\n".join(lines) + "\n"
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
