# -*- coding: utf-8 -*-
"""根因分析单元测试（不调用真实 LLM）。"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from ai_trace.anomaly_detector import AnomalyDetector
from ai_trace.parser import parse_log_file
from ai_trace.root_cause import (
    build_event_chains,
    extract_json_from_llm_response,
    format_chain_for_llm,
    generate_root_cause,
    heuristic_fallback,
)

SAMPLES = Path(__file__).resolve().parents[1] / "samples" / "sample.log"


class RootCauseTests(unittest.TestCase):
    def test_extract_json_plain_and_fenced(self):
        payload = {
            "event_path": ["a", "b"],
            "root_cause": "timeout",
            "confidence": 0.9,
            "suggestions": ["retry"],
            "evidence": ["timeout after 30s"],
        }
        plain = json.dumps(payload, ensure_ascii=False)
        self.assertEqual(extract_json_from_llm_response(plain)["root_cause"], "timeout")

        fenced = "```json\n%s\n```" % plain
        self.assertEqual(
            extract_json_from_llm_response(fenced)["confidence"],
            0.9,
        )

        noisy = "分析如下：\n%s\n结束" % plain
        self.assertEqual(extract_json_from_llm_response(noisy)["root_cause"], "timeout")

    def test_build_chain_by_trace_id(self):
        events = parse_log_file(SAMPLES)
        anomalies = AnomalyDetector().fit_detect(events)
        chain = build_event_chains(events, anomalies)
        self.assertTrue(chain)
        # sample 主链路应聚到 req-1001
        self.assertTrue(any(e.trace_id == "req-1001" for e in chain))
        text = format_chain_for_llm(chain, anomalies)
        self.assertIn("[ANOMALY]", text)

    def test_fallback_without_llm(self):
        events = parse_log_file(SAMPLES)
        anomalies = AnomalyDetector().fit_detect(events)
        data = heuristic_fallback(build_event_chains(events, anomalies), anomalies)
        self.assertTrue(data["fallback"])
        self.assertTrue(data["root_cause"])
        self.assertTrue(data["event_path"])

    def test_generate_with_fake_llm(self):
        events = parse_log_file(SAMPLES)
        anomalies = AnomalyDetector().fit_detect(events)

        def fake_chat(_messages):
            return json.dumps(
                {
                    "event_path": ["下单", "支付超时"],
                    "root_cause": "支付网关超时导致订单未确认",
                    "confidence": 0.82,
                    "suggestions": ["检查支付超时配置"],
                    "evidence": ["timeout after 30s"],
                },
                ensure_ascii=False,
            )

        report = generate_root_cause(events, anomalies, chat_fn=fake_chat)
        self.assertFalse(report.fallback)
        self.assertIn("支付", report.root_cause)
        self.assertEqual(report.confidence, 0.82)

    def test_generate_falls_back_on_bad_json(self):
        events = parse_log_file(SAMPLES)
        anomalies = AnomalyDetector().fit_detect(events)

        def bad_chat(_messages):
            return "这不是 JSON"

        report = generate_root_cause(events, anomalies, chat_fn=bad_chat)
        self.assertTrue(report.fallback)
        self.assertTrue(report.root_cause)


if __name__ == "__main__":
    unittest.main()
