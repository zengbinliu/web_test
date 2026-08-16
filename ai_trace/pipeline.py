# -*- coding: utf-8 -*-
"""三步编排：结构化 → 异常检测 → 根因分析。"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

from .anomaly_detector import AnomalyDetector
from .config import TraceConfig, get_trace_config
from .llm_client import ChatFn
from .models import RcaReport
from .parser import parse_log_file, parse_log_text
from .root_cause import generate_root_cause


def analyze_logs(
    text: str,
    *,
    config: Optional[TraceConfig] = None,
    chat_fn: Optional[ChatFn] = None,
) -> RcaReport:
    """分析原始日志文本，返回根因报告。"""
    cfg = config or get_trace_config()
    events = parse_log_text(text or "")
    detector = AnomalyDetector(cfg)
    anomalies = detector.fit_detect(events)
    return generate_root_cause(
        events,
        anomalies,
        config=cfg,
        chat_fn=chat_fn,
    )


def analyze_log_file(
    path: Union[str, Path],
    *,
    config: Optional[TraceConfig] = None,
    chat_fn: Optional[ChatFn] = None,
) -> RcaReport:
    """分析本地日志文件。"""
    events = parse_log_file(path)
    # 走文本路径会再 parse 一次；这里直接编排以保留文件解析结果
    cfg = config or get_trace_config()
    detector = AnomalyDetector(cfg)
    anomalies = detector.fit_detect(events)
    return generate_root_cause(
        events,
        anomalies,
        config=cfg,
        chat_fn=chat_fn,
    )
