# -*- coding: utf-8 -*-
"""根因分析：事件链构建、LLM 格式化、JSON 提取、路径与建议生成。"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Set

from .config import TraceConfig, get_trace_config, is_llm_available
from .llm_client import ChatFn, chat_completions
from .models import AnomalyResult, LogEvent, RcaReport

_SYSTEM_PROMPT = (
    "你是资深测试开发与日志根因分析专家。"
    "请仅依据提供的日志事件链进行分析，禁止编造日志中未出现的服务、配置或错误。"
    "必须只输出合法 JSON 对象，不要 Markdown，不要额外说明。"
)

_USER_PROMPT_TEMPLATE = """请根据以下日志事件链分析根因。

要求输出 JSON，字段如下：
- event_path: string[]，按时间顺序的关键事件摘要
- root_cause: string，一句话根因
- confidence: number，0~1
- suggestions: string[]，可执行建议
- evidence: string[]，直接来自日志的证据片段

事件链（[ANOMALY] 标记异常点）：
{chain_text}
"""


def _parse_event_time(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    text = str(value).strip().replace("T", " ").replace(",", ".")
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _event_summary(event: LogEvent) -> str:
    msg = (event.message or "").splitlines()[0].strip()
    if len(msg) > 120:
        msg = msg[:117] + "..."
    logger = event.logger or "-"
    return "%s %s: %s" % (event.level, logger, msg)


def build_event_chains(
    events: List[LogEvent],
    anomalies: List[AnomalyResult],
    config: Optional[TraceConfig] = None,
) -> List[LogEvent]:
    """围绕异常点构建并合并事件链，返回按 index 排序的事件列表。"""
    cfg = config or get_trace_config()
    if not anomalies:
        return []
    if not events:
        return []

    by_index = {event.index: event for event in events}
    selected: Set[int] = set()
    neighbor = cfg.chain_neighbor_count
    window_seconds = cfg.chain_window_seconds

    sorted_anomalies = sorted(anomalies, key=lambda item: item.event.index)
    for anomaly in sorted_anomalies:
        center = anomaly.event
        if center.trace_id:
            for event in events:
                if event.trace_id == center.trace_id:
                    selected.add(event.index)
            continue

        # 无关联 ID：时间窗与前后邻居取并集，保证异常点附近上下文完整
        center_time = _parse_event_time(center.timestamp)
        if center_time is not None:
            for event in events:
                event_time = _parse_event_time(event.timestamp)
                if event_time is None:
                    continue
                delta = abs((event_time - center_time).total_seconds())
                if delta <= window_seconds:
                    selected.add(event.index)
        for idx in range(center.index - neighbor, center.index + neighbor + 1):
            if idx in by_index:
                selected.add(idx)

    chain = [by_index[idx] for idx in sorted(selected) if idx in by_index]
    if len(chain) > cfg.max_events_for_llm:
        # 优先保留异常点附近
        anomaly_indexes = {item.event.index for item in anomalies}
        scored = []
        for event in chain:
            dist = min(abs(event.index - aidx) for aidx in anomaly_indexes)
            scored.append((dist, event.index, event))
        scored.sort()
        keep = {item[2].index for item in scored[: cfg.max_events_for_llm]}
        chain = [event for event in chain if event.index in keep]
    return chain


def format_chain_for_llm(
    chain_events: List[LogEvent],
    anomalies: Iterable[AnomalyResult],
) -> str:
    """把事件链格式化为适合 LLM 分析的字符串。"""
    anomaly_indexes = {item.event.index for item in anomalies}
    lines: List[str] = []
    for event in chain_events:
        marker = " [ANOMALY]" if event.index in anomaly_indexes else ""
        ts = event.timestamp or "unknown-time"
        logger = event.logger or "-"
        msg = (event.message or "").replace("\n", "\\n")
        if len(msg) > 500:
            msg = msg[:497] + "..."
        trace = " trace_id=%s" % event.trace_id if event.trace_id else ""
        lines.append(
            "#%d %s [%s] %s: %s%s%s"
            % (event.index, ts, event.level, logger, msg, trace, marker)
        )
    return "\n".join(lines)


def extract_json_from_llm_response(text: str) -> Dict[str, Any]:
    """从 LLM 响应提取 JSON 对象。"""
    if text is None:
        raise ValueError("LLM 响应为空")
    content = str(text).strip()
    if not content:
        raise ValueError("LLM 响应为空")

    fence = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", content, re.I)
    if fence:
        content = fence.group(1).strip()

    try:
        payload = json.loads(content)
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        pass

    start = content.find("{")
    end = content.rfind("}")
    if start >= 0 and end > start:
        snippet = content[start : end + 1]
        payload = json.loads(snippet)
        if isinstance(payload, dict):
            return payload
    raise ValueError("无法从 LLM 响应中提取 JSON")


def _normalize_report_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    event_path = payload.get("event_path") or []
    if not isinstance(event_path, list):
        event_path = [str(event_path)]
    suggestions = payload.get("suggestions") or []
    if not isinstance(suggestions, list):
        suggestions = [str(suggestions)]
    evidence = payload.get("evidence") or []
    if not isinstance(evidence, list):
        evidence = [str(evidence)]
    try:
        confidence = float(payload.get("confidence", 0.5))
    except (TypeError, ValueError):
        confidence = 0.5
    confidence = max(0.0, min(1.0, confidence))
    return {
        "event_path": [str(item) for item in event_path],
        "root_cause": str(payload.get("root_cause") or "").strip() or "未能确定根因",
        "confidence": confidence,
        "suggestions": [str(item) for item in suggestions],
        "evidence": [str(item) for item in evidence],
    }


def heuristic_fallback(
    chain_events: List[LogEvent],
    anomalies: List[AnomalyResult],
) -> Dict[str, Any]:
    """LLM 不可用或解析失败时的启发式兜底。"""
    path = [_event_summary(event) for event in chain_events if event.level != "DEBUG"]
    if not path:
        path = [_event_summary(event) for event in chain_events]

    root_event = None
    for anomaly in sorted(anomalies, key=lambda item: item.event.index):
        if anomaly.event.level in {"ERROR", "FATAL"}:
            root_event = anomaly.event
            break
    if root_event is None and anomalies:
        root_event = anomalies[0].event
    if root_event is None and chain_events:
        root_event = chain_events[-1]

    root_cause = (
        (root_event.message or root_event.raw or "未知异常").splitlines()[0].strip()
        if root_event
        else "未检测到可用异常信号"
    )
    evidence = []
    for anomaly in anomalies[:5]:
        evidence.append(
            (anomaly.event.message or anomaly.event.raw or "").splitlines()[0][:200]
        )
    suggestions = [
        "核对异常点前后同一 trace_id / request_id 的调用链",
        "检查超时、依赖服务可用性与重试策略",
    ]
    return {
        "event_path": path[:20],
        "root_cause": root_cause,
        "confidence": 0.35,
        "suggestions": suggestions,
        "evidence": [item for item in evidence if item],
        "fallback": True,
    }


def generate_root_cause(
    events: List[LogEvent],
    anomalies: List[AnomalyResult],
    *,
    config: Optional[TraceConfig] = None,
    chat_fn: Optional[ChatFn] = None,
) -> RcaReport:
    """生成事件路径与根因建议。"""
    cfg = config or get_trace_config()
    chain = build_event_chains(events, anomalies, cfg)
    if not anomalies:
        return RcaReport(
            event_path=[],
            root_cause="未检测到异常日志",
            confidence=0.0,
            suggestions=["确认日志是否包含错误级别或超时等信息"],
            evidence=[],
            fallback=True,
            anomaly_count=0,
            event_count=len(events),
            anomalies=[],
            chain_events=[],
        )

    chain_text = format_chain_for_llm(chain, anomalies)
    raw_response: Optional[str] = None
    use_chat = chat_fn or chat_completions

    if chat_fn is not None or is_llm_available():
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": _USER_PROMPT_TEMPLATE.format(chain_text=chain_text),
            },
        ]
        try:
            raw_response = use_chat(messages)
            payload = _normalize_report_payload(
                extract_json_from_llm_response(raw_response)
            )
            return RcaReport(
                event_path=payload["event_path"],
                root_cause=payload["root_cause"],
                confidence=payload["confidence"],
                suggestions=payload["suggestions"],
                evidence=payload["evidence"],
                fallback=False,
                anomaly_count=len(anomalies),
                event_count=len(events),
                anomalies=anomalies,
                chain_events=chain,
                raw_llm_response=raw_response,
            )
        except Exception:
            pass

    fallback = heuristic_fallback(chain, anomalies)
    return RcaReport(
        event_path=fallback["event_path"],
        root_cause=fallback["root_cause"],
        confidence=fallback["confidence"],
        suggestions=fallback["suggestions"],
        evidence=fallback["evidence"],
        fallback=True,
        anomaly_count=len(anomalies),
        event_count=len(events),
        anomalies=anomalies,
        chain_events=chain,
        raw_llm_response=raw_response,
    )
