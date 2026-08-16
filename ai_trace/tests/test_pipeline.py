# -*- coding: utf-8 -*-
"""端到端 pipeline 测试（假 LLM）。"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from ai_trace.pipeline import analyze_log_file, analyze_logs

SAMPLES = Path(__file__).resolve().parents[1] / "samples" / "sample.log"


class PipelineTests(unittest.TestCase):
    def test_analyze_logs_with_fake_llm(self):
        text = SAMPLES.read_text(encoding="utf-8")

        def fake_chat(_messages):
            return json.dumps(
                {
                    "event_path": ["INFO 下单", "ERROR 支付超时"],
                    "root_cause": "支付网关超时导致订单未确认",
                    "confidence": 0.8,
                    "suggestions": ["检查支付超时配置", "补重试与幂等"],
                    "evidence": ["timeout after 30s", "request_id=req-1001"],
                },
                ensure_ascii=False,
            )

        report = analyze_logs(text, chat_fn=fake_chat)
        self.assertGreater(report.anomaly_count, 0)
        self.assertGreater(report.event_count, 0)
        self.assertFalse(report.fallback)
        payload = report.to_dict()
        self.assertIn("root_cause", payload)
        self.assertIn("event_path", payload)

    def test_analyze_file_fallback_without_llm(self):
        report = analyze_log_file(SAMPLES, chat_fn=None)
        # 无可用 LLM 且未注入 chat_fn 时走兜底
        # 若环境碰巧配置了 LLM，这里强制用坏 chat 测 fallback 更稳
        def boom(_messages):
            raise RuntimeError("llm down")

        report = analyze_log_file(SAMPLES, chat_fn=boom)
        self.assertTrue(report.fallback)
        self.assertTrue(report.root_cause)
        self.assertGreater(report.anomaly_count, 0)


if __name__ == "__main__":
    unittest.main()
