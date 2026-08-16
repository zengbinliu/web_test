# -*- coding: utf-8 -*-
"""日志结构化：原始文本 → LogEvent 列表。"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple, Union

from .models import LogEvent

_LEVEL_ALIASES = {
    "DEBUG": "DEBUG",
    "INFO": "INFO",
    "INFORMATION": "INFO",
    "WARN": "WARN",
    "WARNING": "WARN",
    "ERROR": "ERROR",
    "ERR": "ERROR",
    "FATAL": "FATAL",
    "CRITICAL": "FATAL",
    "CRIT": "FATAL",
}

_TRACE_PATTERNS = [
    re.compile(r"\b(?:trace[_-]?id|request[_-]?id|session[_-]?id)\s*[:=]\s*([A-Za-z0-9\-_]+)", re.I),
    re.compile(r"\b(?:tid|rid)\s*[:=]\s*([A-Za-z0-9\-_]+)", re.I),
]

# 2026-08-16 17:49:00,123 [ERROR] order.pay: message
_TEXT_LINE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d{1,6})?)\s*"
    r"(?:\[(?P<level1>[A-Za-z]+)\]|\b(?P<level2>[A-Za-z]+)\b)\s*"
    r"(?:(?P<logger>[\w./:-]+)\s*:\s*)?(?P<msg>.*)$"
)

_STACK_CONTINUATION = re.compile(
    r"^(?:\s+)?(?:at\s+|File\s+\"|Traceback\b|Caused by:|---|\.\.\.|"
    r"\w*(?:Error|Exception)\b)",
    re.I,
)


def normalize_level(raw: Optional[str]) -> str:
    """归一化日志级别。"""
    if not raw:
        return "INFO"
    key = str(raw).strip().upper()
    return _LEVEL_ALIASES.get(key, key if key in _LEVEL_ALIASES.values() else "INFO")


def extract_trace_id(text: str) -> Optional[str]:
    """从文本中抽取 trace_id / request_id / session_id。"""
    if not text:
        return None
    for pattern in _TRACE_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(1)
    return None


def _parse_timestamp(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    text = str(value).strip().replace("T", " ").replace(",", ".")
    for fmt in (
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
    ):
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        except ValueError:
            continue
    return text


def _try_parse_json_line(line: str) -> Optional[Tuple[Optional[str], str, str, str, Optional[str], dict]]:
    stripped = line.strip()
    if not stripped.startswith("{"):
        return None
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None

    ts = (
        payload.get("ts")
        or payload.get("timestamp")
        or payload.get("time")
        or payload.get("@timestamp")
    )
    level = normalize_level(payload.get("level") or payload.get("severity") or payload.get("severityname"))
    logger = str(
        payload.get("logger")
        or payload.get("logger_name")
        or payload.get("name")
        or payload.get("service")
        or ""
    )
    msg = str(
        payload.get("msg")
        or payload.get("message")
        or payload.get("log")
        or payload.get("text")
        or ""
    )
    trace_id = (
        payload.get("trace_id")
        or payload.get("traceId")
        or payload.get("request_id")
        or payload.get("requestId")
        or payload.get("session_id")
        or extract_trace_id(msg)
    )
    if trace_id is not None:
        trace_id = str(trace_id)
    extra = {
        key: value
        for key, value in payload.items()
        if key
        not in {
            "ts",
            "timestamp",
            "time",
            "@timestamp",
            "level",
            "severity",
            "severityname",
            "logger",
            "logger_name",
            "name",
            "service",
            "msg",
            "message",
            "log",
            "text",
            "trace_id",
            "traceId",
            "request_id",
            "requestId",
            "session_id",
        }
    }
    return _parse_timestamp(str(ts) if ts else None), level, logger, msg, trace_id, extra


def _parse_text_line(line: str) -> Tuple[Optional[str], str, str, str, Optional[str]]:
    match = _TEXT_LINE.match(line.strip())
    if not match:
        return None, "INFO", "", line.strip(), extract_trace_id(line)

    level = normalize_level(match.group("level1") or match.group("level2"))
    logger = (match.group("logger") or "").strip()
    msg = (match.group("msg") or "").strip()
    if not logger and ":" in msg:
        # 兼容 "order.pay: timeout" 已被整体吃进 msg 的情况已由正则处理
        pass
    return (
        _parse_timestamp(match.group("ts")),
        level,
        logger,
        msg,
        extract_trace_id(line),
    )


def _is_continuation(line: str) -> bool:
    if not line.strip():
        return True
    if line.startswith(" ") or line.startswith("\t"):
        return True
    return bool(_STACK_CONTINUATION.match(line))


def parse_log_text(text: str) -> List[LogEvent]:
    """将原始日志文本解析为结构化事件列表。"""
    if text is None:
        return []
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    events: List[LogEvent] = []
    pending_raw: List[str] = []
    pending_meta: Optional[Tuple] = None
    last_ts: Optional[str] = None

    def flush() -> None:
        nonlocal pending_raw, pending_meta, last_ts
        if not pending_raw or pending_meta is None:
            pending_raw = []
            pending_meta = None
            return
        ts, level, logger, msg, trace_id, extra = pending_meta
        if ts is None:
            ts = last_ts
        else:
            last_ts = ts
        raw = "\n".join(pending_raw)
        if len(pending_raw) > 1:
            # 堆栈续行追加进 message
            continuation = "\n".join(pending_raw[1:])
            if continuation and continuation not in msg:
                msg = (msg + "\n" + continuation).strip()
        if not trace_id:
            trace_id = extract_trace_id(raw)
        events.append(
            LogEvent(
                index=len(events),
                timestamp=ts,
                level=level,
                logger=logger,
                message=msg,
                raw=raw,
                trace_id=trace_id,
                extra=extra or {},
            )
        )
        pending_raw = []
        pending_meta = None

    for line in lines:
        if not line and not pending_raw:
            continue
        if pending_raw and _is_continuation(line) and not line.strip().startswith("{"):
            # 无时间戳且像堆栈的续行并入上一条
            if not _TEXT_LINE.match(line.strip()) and not (line.strip().startswith("{") and line.strip().endswith("}")):
                pending_raw.append(line)
                continue

        json_parsed = _try_parse_json_line(line)
        if json_parsed is not None:
            flush()
            ts, level, logger, msg, trace_id, extra = json_parsed
            pending_meta = (ts, level, logger, msg, trace_id, extra)
            pending_raw = [line]
            continue

        if _TEXT_LINE.match(line.strip()):
            flush()
            ts, level, logger, msg, trace_id = _parse_text_line(line)
            pending_meta = (ts, level, logger, msg, trace_id, {})
            pending_raw = [line]
            continue

        if pending_raw:
            pending_raw.append(line)
            continue

        # 独立无时间戳行
        pending_meta = (last_ts, "INFO", "", line.strip(), extract_trace_id(line), {})
        pending_raw = [line]

    flush()
    return events


def parse_log_file(path: Union[str, Path]) -> List[LogEvent]:
    """从本地文件读取并解析日志。"""
    file_path = Path(path)
    text = file_path.read_text(encoding="utf-8", errors="replace")
    return parse_log_text(text)
