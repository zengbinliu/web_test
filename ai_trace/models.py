# -*- coding: utf-8 -*-
"""日志根因分析的数据结构。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class LogEvent:
    """一条结构化日志事件。"""

    index: int
    timestamp: Optional[str]
    level: str
    logger: str
    message: str
    raw: str
    trace_id: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def text_for_vector(self) -> str:
        """供 TF-IDF 使用的文本表示。"""
        parts = [self.level or "", self.logger or "", self.message or ""]
        return " ".join(p for p in parts if p).strip()

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AnomalyResult:
    """异常检测结果。"""

    event: LogEvent
    score: float
    source: str  # model | rule | both

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event": self.event.to_dict(),
            "score": self.score,
            "source": self.source,
        }


@dataclass
class RcaReport:
    """根因分析报告。"""

    event_path: List[str]
    root_cause: str
    confidence: float
    suggestions: List[str]
    evidence: List[str]
    fallback: bool = False
    anomaly_count: int = 0
    event_count: int = 0
    anomalies: List[AnomalyResult] = field(default_factory=list)
    chain_events: List[LogEvent] = field(default_factory=list)
    raw_llm_response: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_path": self.event_path,
            "root_cause": self.root_cause,
            "confidence": self.confidence,
            "suggestions": self.suggestions,
            "evidence": self.evidence,
            "fallback": self.fallback,
            "anomaly_count": self.anomaly_count,
            "event_count": self.event_count,
            "anomalies": [item.to_dict() for item in self.anomalies],
            "chain_events": [item.to_dict() for item in self.chain_events],
            "raw_llm_response": self.raw_llm_response,
        }
