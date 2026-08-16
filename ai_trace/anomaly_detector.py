# -*- coding: utf-8 -*-
"""日志异常检测：TF-IDF + Isolation Forest，并辅以规则检测。"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Set

from sklearn.ensemble import IsolationForest
from sklearn.feature_extraction.text import TfidfVectorizer

from .config import TraceConfig, get_trace_config
from .models import AnomalyResult, LogEvent

_RULE_LEVELS = {"ERROR", "FATAL"}
_RULE_KEYWORDS = re.compile(
    r"(exception|traceback|timeout|timed\s*out|fatal|panic|outofmemory|"
    r"connection\s*refused|connection\s*reset|failed|failure)",
    re.I,
)


class AnomalyDetector:
    """初始化 TF-IDF 与 Isolation Forest，训练并检测异常日志。"""

    def __init__(self, config: Optional[TraceConfig] = None):
        self.config = config or get_trace_config()
        self.vectorizer = TfidfVectorizer(
            max_features=self.config.tfidf_max_features,
            ngram_range=(1, 2),
            token_pattern=r"(?u)\b\w+\b",
        )
        self.model = IsolationForest(
            contamination=self.config.contamination,
            random_state=42,
            n_estimators=100,
        )
        self._fitted = False

    def _corpus(self, events: List[LogEvent]) -> List[str]:
        return [event.text_for_vector() or event.raw or " " for event in events]

    def fit(self, events: List[LogEvent]) -> "AnomalyDetector":
        """用结构化日志训练向量化器与异常检测模型。"""
        if len(events) < self.config.min_events_for_model:
            self._fitted = False
            return self
        corpus = self._corpus(events)
        matrix = self.vectorizer.fit_transform(corpus)
        self.model.fit(matrix)
        self._fitted = True
        return self

    def _rule_hit(self, event: LogEvent) -> bool:
        if event.level in _RULE_LEVELS:
            return True
        text = " ".join([event.message or "", event.raw or ""])
        return bool(_RULE_KEYWORDS.search(text))

    def detect(self, events: List[LogEvent]) -> List[AnomalyResult]:
        """检测异常；样本过少时仅走规则。"""
        if not events:
            return []

        model_scores: Dict[int, float] = {}
        model_flags: Set[int] = set()

        if self._fitted and len(events) >= self.config.min_events_for_model:
            matrix = self.vectorizer.transform(self._corpus(events))
            preds = self.model.predict(matrix)
            decisions = self.model.decision_function(matrix)
            for event, pred, decision in zip(events, preds, decisions):
                # Isolation Forest: -1 异常；decision 越小越异常
                score = float(-decision)
                model_scores[event.index] = score
                if int(pred) == -1:
                    model_flags.add(event.index)

        results: List[AnomalyResult] = []
        for event in events:
            rule = self._rule_hit(event)
            model = event.index in model_flags
            if not rule and not model:
                continue
            if rule and model:
                source = "both"
            elif model:
                source = "model"
            else:
                source = "rule"
            score = model_scores.get(event.index)
            if score is None:
                score = 1.0 if event.level in _RULE_LEVELS else 0.7
            results.append(AnomalyResult(event=event, score=score, source=source))

        results.sort(key=lambda item: (-item.score, item.event.index))
        return results

    def fit_detect(self, events: List[LogEvent]) -> List[AnomalyResult]:
        """当次训练并检测（无监督批次分析）。"""
        self.fit(events)
        return self.detect(events)
