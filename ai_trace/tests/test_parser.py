# -*- coding: utf-8 -*-
"""parser 单元测试。"""

from __future__ import annotations

import unittest
from pathlib import Path

from ai_trace.parser import extract_trace_id, normalize_level, parse_log_file, parse_log_text

SAMPLES = Path(__file__).resolve().parents[1] / "samples" / "sample.log"


class ParserTests(unittest.TestCase):
    def test_normalize_level(self):
        self.assertEqual(normalize_level("warning"), "WARN")
        self.assertEqual(normalize_level("CRITICAL"), "FATAL")
        self.assertEqual(normalize_level(None), "INFO")

    def test_extract_trace_id(self):
        self.assertEqual(extract_trace_id("timeout request_id=req-1001"), "req-1001")
        self.assertEqual(extract_trace_id("trace_id: abc-9"), "abc-9")

    def test_parse_text_and_stack(self):
        text = (
            "2026-08-16 17:49:01,310 [ERROR] payment.client: timeout request_id=req-1\n"
            "Traceback (most recent call last):\n"
            '  File "payment/client.py", line 88, in charge\n'
            "TimeoutError: gateway timeout\n"
            "2026-08-16 17:49:01,320 [INFO] gateway.http: done\n"
        )
        events = parse_log_text(text)
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0].level, "ERROR")
        self.assertEqual(events[0].trace_id, "req-1")
        self.assertIn("Traceback", events[0].message)
        self.assertEqual(events[1].level, "INFO")

    def test_parse_json_lines(self):
        text = (
            '{"ts":"2026-08-16 17:51:00.100","level":"ERROR","logger":"job",'
            '"msg":"boom","trace_id":"job-77"}\n'
        )
        events = parse_log_text(text)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].level, "ERROR")
        self.assertEqual(events[0].trace_id, "job-77")
        self.assertEqual(events[0].logger, "job")

    def test_sample_file(self):
        events = parse_log_file(SAMPLES)
        self.assertGreaterEqual(len(events), 10)
        traced = [e for e in events if e.trace_id == "req-1001"]
        self.assertGreaterEqual(len(traced), 5)


if __name__ == "__main__":
    unittest.main()
