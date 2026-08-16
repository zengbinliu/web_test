# -*- coding: utf-8 -*-
"""本地文件入口：python -m ai_trace.cli --file samples/sample.log"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .pipeline import analyze_log_file, analyze_logs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AI 日志根因分析")
    parser.add_argument(
        "--file",
        "-f",
        type=str,
        help="本地日志文件路径",
    )
    parser.add_argument(
        "--text",
        "-t",
        type=str,
        help="直接传入日志文本（与 --file 二选一）",
    )
    parser.add_argument(
        "--out",
        "-o",
        type=str,
        help="将结果 JSON 写入文件；默认打印到 stdout",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="输出紧凑 JSON（不含 chain_events / anomalies 明细可仍保留完整 to_dict）",
    )
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if bool(args.file) == bool(args.text):
        print("请使用 --file 或 --text 之一传入日志。", file=sys.stderr)
        return 2

    if args.file:
        path = Path(args.file)
        if not path.exists():
            print("文件不存在: %s" % path, file=sys.stderr)
            return 1
        report = analyze_log_file(path)
    else:
        report = analyze_logs(args.text)

    indent = None if args.compact else 2
    payload = json.dumps(report.to_dict(), ensure_ascii=False, indent=indent)
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(payload + "\n", encoding="utf-8")
        print("已写入: %s" % out_path)
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
