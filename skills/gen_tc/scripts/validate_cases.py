#!/usr/bin/env python3
"""Validate gen_tc JSON test cases against team writing rules."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

Severity = Literal["error", "warning"]

STEP_SPLIT_RE = re.compile(r"^\s*\d+[）)、.．]\s*")
BAD_STEP_PREFIX_RE = re.compile(r"^\s*\d+、\s*")

VAGUE_EXPECT_PATTERNS = [
    re.compile(r"文案正确"),
    re.compile(r"显示正确"),
    re.compile(r"页面显示正确"),
    re.compile(r"功能正常"),
    re.compile(r"数据正确"),
    re.compile(r"操作成功(?!.*提示|.*状态|.*订单)"),
    re.compile(r"页面正常(?!加载)"),
]

MULTI_POINT_TITLE_PATTERNS = [
    re.compile(r"验证.+(与|及|以及|并).+"),
    re.compile(r"(购买|取消|编辑|删除|开通|关闭).+(与|及).+(购买|取消|编辑|删除|开通|关闭)"),
    re.compile(r"全流程"),
]

STEP_SPLIT_WARN = 7
STEP_SPLIT_ERROR = 10
P1_PER_MODULE_WARN = 5


@dataclass
class Issue:
    severity: Severity
    case_id: str
    field: str
    message: str


@dataclass
class ValidationReport:
    issues: list[Issue] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        return sum(1 for item in self.issues if item.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for item in self.issues if item.severity == "warning")

    def add(self, severity: Severity, case_id: str, field_name: str, message: str) -> None:
        self.issues.append(Issue(severity, case_id, field_name, message))


def _case_id(case: dict[str, Any], index: int) -> str:
    return str(case.get("id") or f"case-{index}")


def _as_lines(items: Any) -> list[str]:
    if isinstance(items, str):
        return [line for line in items.splitlines() if line.strip()]
    if isinstance(items, list):
        return [str(item).strip() for item in items if str(item).strip()]
    return []


def _strip_step_prefix(line: str) -> str:
    return STEP_SPLIT_RE.sub("", line.strip())


def validate_case(case: dict[str, Any], index: int, report: ValidationReport) -> None:
    case_id = _case_id(case, index)

    for field_name in ("title", "precondition", "priority"):
        if not str(case.get(field_name) or "").strip():
            report.add("error", case_id, field_name, f"missing required field '{field_name}'")

    steps = _as_lines(case.get("steps"))
    expects = _as_lines(case.get("expects"))

    if not steps or not expects:
        report.add("error", case_id, "steps/expects", "steps and expects are required")
        return

    if len(steps) != len(expects):
        report.add(
            "error",
            case_id,
            "steps/expects",
            f"steps count ({len(steps)}) != expects count ({len(expects)})",
        )

    step_severity: Severity = "warning" if len(steps) > STEP_SPLIT_WARN else "error"
    if len(steps) > STEP_SPLIT_ERROR:
        step_severity = "error"
        report.add(
            step_severity,
            case_id,
            "steps",
            f"step count {len(steps)} exceeds hard limit {STEP_SPLIT_ERROR}; split the case",
        )
    elif len(steps) > STEP_SPLIT_WARN:
        report.add(
            step_severity,
            case_id,
            "steps",
            f"step count {len(steps)} exceeds recommended split threshold {STEP_SPLIT_WARN}",
        )

    title = str(case.get("title") or "")
    for pattern in MULTI_POINT_TITLE_PATTERNS:
        if pattern.search(title):
            report.add(
                "warning",
                case_id,
                "title",
                "title may contain multiple test points; split into separate cases",
            )
            break

    for step in steps:
        if BAD_STEP_PREFIX_RE.match(step):
            report.add(
                "error",
                case_id,
                "steps",
                f"forbidden step numbering '1、' detected: {step[:60]}",
            )

    for expect in expects:
        body = _strip_step_prefix(expect)
        for pattern in VAGUE_EXPECT_PATTERNS:
            if pattern.search(body):
                report.add(
                    "warning",
                    case_id,
                    "expects",
                    f"vague expectation; add concrete keywords or rules: {body[:80]}",
                )
                break


def validate_cases(cases: list[dict[str, Any]]) -> ValidationReport:
    report = ValidationReport()
    p1_by_module: dict[str, int] = {}

    for index, case in enumerate(cases, start=1):
        validate_case(case, index, report)
        priority = str(case.get("priority") or "").strip().upper()
        module = str(case.get("module") or "未分类").strip()
        if priority == "P1":
            p1_by_module[module] = p1_by_module.get(module, 0) + 1

    for module, count in sorted(p1_by_module.items()):
        if count > P1_PER_MODULE_WARN:
            report.add(
                "warning",
                "module-summary",
                "priority",
                f"module '{module}' has {count} P1 cases (recommended max {P1_PER_MODULE_WARN})",
            )

    return report


def load_cases(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(data, list):
        return data
    cases = data.get("cases") or []
    if not isinstance(cases, list) or not cases:
        raise ValueError("JSON must contain non-empty 'cases' array")
    return cases


def format_report(report: ValidationReport) -> str:
    if not report.issues:
        return "Validation passed with no issues."

    lines = [
        f"Validation: {report.error_count} error(s), {report.warning_count} warning(s)",
        "",
    ]
    for issue in report.issues:
        lines.append(f"[{issue.severity.upper()}] {issue.case_id} :: {issue.field} :: {issue.message}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate gen_tc JSON test cases")
    parser.add_argument("--input", "-i", required=True, help="Input JSON file path")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as errors (exit code 1)",
    )
    args = parser.parse_args()

    input_path = Path(args.input).expanduser().resolve()
    if not input_path.is_file():
        print(f"Input not found: {input_path}", file=sys.stderr)
        return 1

    try:
        cases = load_cases(input_path)
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"Invalid input: {exc}", file=sys.stderr)
        return 1

    report = validate_cases(cases)
    print(format_report(report))

    if report.error_count:
        return 1
    if args.strict and report.warning_count:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
