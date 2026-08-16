# -*- coding: utf-8 -*-
"""异常检测单元测试。"""

from __future__ import annotations

import unittest
from pathlib import Path

from ai_trace.anomaly_detector import AnomalyDetector
from ai_trace.parser import parse_log_file, parse_log_text

SAMPLES = Path(__file__).resolve().parents[1] / "samples" / "sample.log"


class AnomalyDetectorTests(unittest.TestCase):
    def test_rule_detects_error_and_timeout(self):
        text = (
            "2026-08-16 17:48:01,001 [INFO] a: ok\n"
            "2026-08-16 17:48:02,001 [INFO] a: still ok\n"
            "2026-08-16 17:48:03,001 [ERROR] b: timeout after 30s\n"
        )
        events = parse_log_text(text)
        detector = AnomalyDetector()
        # 样本不足，仅规则
        results = detector.fit_detect(events)
        self.assertTrue(results)
        messages = " ".join(item.event.message for item in results)
        self.assertIn("timeout", messages.lower())
        self.assertTrue(any(item.source in {"rule", "both"} for item in results))

    def test_sample_log_finds_payment_errors(self):
        events = parse_log_file(SAMPLES)
        results = AnomalyDetector().fit_detect(events)
        self.assertTrue(results)
        self.assertTrue(
            any(
                "timeout" in (item.event.message or "").lower()
                or item.event.level == "ERROR"
                for item in results
            )
        )


if __name__ == "__main__":
    unittest.main()
