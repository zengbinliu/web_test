import json
import os
import tempfile
import unittest
from unittest import mock

from app import (
    MCP_PROTOCOL_VERSION,
    SERVER_NAME,
    SUPPORTED_PROTOCOL_VERSIONS,
    SESSIONS,
    TOOLS,
    app,
)


class FlaskMcpServerTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.client = app.test_client()
        SESSIONS.clear()

    def post_json(self, payload, headers=None):
        return self.client.post("/mcp", json=payload, headers=headers or {})

    def session_headers(self, session_id, protocol_version=MCP_PROTOCOL_VERSION):
        return {
            "MCP-Session-Id": session_id,
            "MCP-Protocol-Version": protocol_version,
        }

    def initialize_session(self, protocol_version=MCP_PROTOCOL_VERSION):
        response = self.post_json(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": protocol_version,
                    "capabilities": {},
                    "clientInfo": {"name": "unit-test", "version": "1.0"},
                },
            }
        )
        self.assertEqual(response.status_code, 200)
        session_id = response.headers.get("MCP-Session-Id")
        self.assertTrue(session_id)
        return response, session_id

    def test_initialize_returns_server_info_and_session(self):
        response, session_id = self.initialize_session()
        payload = response.get_json()

        self.assertEqual(payload["result"]["protocolVersion"], MCP_PROTOCOL_VERSION)
        self.assertEqual(payload["result"]["serverInfo"]["name"], SERVER_NAME)
        self.assertIn("tools", payload["result"]["capabilities"])
        self.assertEqual(response.headers["MCP-Session-Id"], session_id)

    def test_initialize_supports_legacy_protocol_version(self):
        legacy_version = SUPPORTED_PROTOCOL_VERSIONS[-1]
        response, _session_id = self.initialize_session(legacy_version)
        payload = response.get_json()

        self.assertEqual(payload["result"]["protocolVersion"], legacy_version)
        self.assertEqual(response.headers["MCP-Protocol-Version"], legacy_version)

    def test_tools_list_requires_session_header(self):
        response = self.post_json(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list",
                "params": {},
            }
        )

        self.assertEqual(response.status_code, 400)
        payload = response.get_json()
        self.assertIn("MCP-Session-Id", payload["error"]["message"])

    def test_tools_list_contains_builtin_tools(self):
        _response, session_id = self.initialize_session()
        response = self.post_json(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list",
                "params": {},
            },
            headers=self.session_headers(session_id),
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        tool_names = [tool["name"] for tool in payload["result"]["tools"]]
        self.assertEqual(
            tool_names,
            ["askreolink", "askcamovue", "update_reolink_kb"],
        )

    @mock.patch("app.subprocess.run")
    def test_askreolink_tool_invokes_kb_script(self, run_mock):
        fake = mock.Mock()
        fake.returncode = 0
        fake.stdout = "kb-output"
        fake.stderr = ""
        run_mock.return_value = fake

        result = TOOLS["askreolink"].handler({"query": "切换套餐"})
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(result["stdout"], "kb-output")
        run_mock.assert_called_once()
        cmd = run_mock.call_args[0][0]
        self.assertTrue(cmd[1].endswith("ask_reolink_testcase_kb.py"))
        self.assertEqual(cmd[2], "切换套餐")
        self.assertEqual(cmd[3:5], ["--top", "5"])

    @mock.patch("app.subprocess.run")
    def test_askcamovue_tool_invokes_kb_script(self, run_mock):
        fake = mock.Mock()
        fake.returncode = 0
        fake.stdout = "camovue-output"
        fake.stderr = ""
        run_mock.return_value = fake

        result = TOOLS["askcamovue"].handler({"query": "年套餐可以提现吗"})
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(result["stdout"], "camovue-output")
        run_mock.assert_called_once()
        cmd = run_mock.call_args[0][0]
        self.assertTrue(cmd[1].endswith("ask_camovue_kb.py"))
        self.assertEqual(cmd[2], "年套餐可以提现吗")
        self.assertEqual(cmd[3:5], ["--top", "3"])

    @mock.patch("app.subprocess.run")
    @mock.patch("app.os.path.isfile", return_value=True)
    @mock.patch("app.update_reolink_script_path", return_value=r"C:\fake\update_reolink_testcase_kb.py")
    @mock.patch("app.reolink_kb_root_dir", return_value=r"C:\fake\kb")
    def test_update_reolink_kb_tool_invokes_script(
        self, _root_mock, _script_mock, _isfile_mock, run_mock
    ):
        fake = mock.Mock()
        fake.returncode = 0
        fake.stdout = "updated"
        fake.stderr = ""
        run_mock.return_value = fake

        result = TOOLS["update_reolink_kb"].handler(
            {
                "summary": "修正套餐切换文案",
                "correction": "切换后应展示新套餐名称。",
                "module_hint": "套餐",
                "author": "tester",
            }
        )
        self.assertEqual(result["mode"], "script")
        self.assertEqual(result["exit_code"], 0)
        run_mock.assert_called_once()
        stdin = run_mock.call_args.kwargs["input"]
        payload = json.loads(stdin)
        self.assertEqual(payload["summary"], "修正套餐切换文案")
        self.assertEqual(payload["correction"], "切换后应展示新套餐名称。")
        self.assertEqual(payload["module_hint"], "套餐")
        self.assertEqual(payload["author"], "tester")
        self.assertEqual(payload["topic_key"], "套餐")
        self.assertIn("submitted_at", payload)

    def test_update_reolink_kb_rejects_batch_renewal_without_country_group_rule(self):
        with self.assertRaises(ValueError) as ctx:
            TOOLS["update_reolink_kb"].handler(
                {
                    "summary": "批量续费说明",
                    "correction": "支持勾选多条记录操作。",
                }
            )
        self.assertIn("批量续费", str(ctx.exception))
        self.assertIn("国家组", str(ctx.exception))

    def test_update_reolink_kb_accepts_batch_renewal_with_country_group_rule(self):
        with tempfile.TemporaryDirectory() as tmp:
            patches = os.path.join(tmp, "p.jsonl")
            env = {
                "REOLINK_KB_ROOT": tmp,
                "REOLINK_KB_PATCHES_PATH": patches,
            }
            with mock.patch.dict(os.environ, env, clear=False):
                result = TOOLS["update_reolink_kb"].handler(
                    {
                        "summary": "批量续费",
                        "correction": (
                            "批量续费仅允许同一国家组：所选记录须国家组一致；跨国家组不可批量续费。"
                        ),
                    }
                )
            self.assertEqual(result["mode"], "patch_file")

    def test_update_reolink_kb_tool_appends_patch_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            patches = os.path.join(tmp, "custom_patches.jsonl")
            env = {
                "REOLINK_KB_ROOT": tmp,
                "REOLINK_KB_PATCHES_PATH": patches,
            }
            with mock.patch.dict(os.environ, env, clear=False):
                result = TOOLS["update_reolink_kb"].handler(
                    {
                        "summary": "s1",
                        "correction": "detail line",
                    }
                )
            self.assertEqual(result["mode"], "patch_file")
            self.assertEqual(result["patches_path"], patches)
            with open(patches, "r", encoding="utf-8") as handle:
                line = handle.readline().strip()
            stored = json.loads(line)
            self.assertEqual(stored["summary"], "s1")
            self.assertEqual(stored["correction"], "detail line")
            self.assertEqual(stored["topic_key"], "s1")

    def test_update_reolink_kb_tool_replaces_same_topic_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            patches = os.path.join(tmp, "custom_patches.jsonl")
            with open(patches, "w", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(
                        {
                            "summary": "old-a",
                            "correction": "rule a",
                            "module_hint": "云服务/套餐",
                            "topic_key": "云服务|套餐",
                            "author": "",
                            "submitted_at": "2026-01-01T00:00:00+00:00",
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                handle.write(
                    json.dumps(
                        {
                            "summary": "old-b",
                            "correction": "rule b",
                            "module_hint": "云服务/套餐",
                            "author": "",
                            "submitted_at": "2026-01-02T00:00:00+00:00",
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )

            env = {"REOLINK_KB_PATCHES_PATH": patches}
            with mock.patch.dict(os.environ, env, clear=False):
                result = TOOLS["update_reolink_kb"].handler(
                    {
                        "summary": "new-title",
                        "correction": "replacement rule",
                        "module_hint": "云服务/套餐",
                    }
                )

            self.assertEqual(result["mode"], "patch_file")
            self.assertEqual(result["topic_key"], "云服务|套餐")
            self.assertEqual(result["removed_conflicting_rows"], 2)

            lines = []
            with open(patches, "r", encoding="utf-8") as handle:
                lines = [ln.strip() for ln in handle if ln.strip()]
            self.assertEqual(len(lines), 1)
            payload = json.loads(lines[0])
            self.assertEqual(payload["correction"], "replacement rule")

    def test_update_reolink_kb_removes_exact_duplicate_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            patches = os.path.join(tmp, "p.jsonl")
            dup_line = json.dumps(
                {
                    "summary": "dup-title",
                    "correction": "same body",
                    "module_hint": "mod-a",
                    "topic_key": "mod|a",
                    "author": "",
                    "submitted_at": "2026-01-01T00:00:00+00:00",
                },
                ensure_ascii=False,
            )
            with open(patches, "w", encoding="utf-8") as handle:
                handle.write(dup_line + "\n")
                handle.write(
                    json.dumps(
                        {
                            "summary": "other",
                            "correction": "x",
                            "module_hint": "other-mod",
                            "submitted_at": "2026-01-02T00:00:00+00:00",
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )

            env = {"REOLINK_KB_PATCHES_PATH": patches}
            with mock.patch.dict(os.environ, env, clear=False):
                result = TOOLS["update_reolink_kb"].handler(
                    {
                        "summary": "dup-title",
                        "correction": "same body",
                        "module_hint": "mod-a",
                    }
                )

            self.assertEqual(result["removed_conflicting_rows"], 1)
            lines = []
            with open(patches, "r", encoding="utf-8") as handle:
                lines = [ln.strip() for ln in handle if ln.strip()]
            self.assertEqual(len(lines), 2)
            bodies = {json.loads(ln)["summary"] for ln in lines}
            self.assertEqual(bodies, {"dup-title", "other"})

    def test_update_reolink_kb_removes_same_title_same_module(self):
        with tempfile.TemporaryDirectory() as tmp:
            patches = os.path.join(tmp, "p.jsonl")
            with open(patches, "w", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(
                        {
                            "summary": "同一标题吗？",
                            "correction": "旧逻辑",
                            "module_hint": "云服务/套餐",
                            "submitted_at": "2026-01-01T00:00:00+00:00",
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )

            env = {"REOLINK_KB_PATCHES_PATH": patches}
            with mock.patch.dict(os.environ, env, clear=False):
                TOOLS["update_reolink_kb"].handler(
                    {
                        "summary": "同一标题",
                        "correction": "新逻辑",
                        "module_hint": "云服务/套餐",
                    }
                )

            with open(patches, "r", encoding="utf-8") as handle:
                lines = [ln.strip() for ln in handle if ln.strip()]
            self.assertEqual(len(lines), 1)
            row = json.loads(lines[0])
            self.assertEqual(row["correction"], "新逻辑")

    def test_initialized_notification_returns_accepted(self):
        _response, session_id = self.initialize_session()
        response = self.post_json(
            {
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
                "params": {},
            },
            headers=self.session_headers(session_id),
        )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.get_data(as_text=True), "")

    def test_unknown_tool_returns_error_result(self):
        _response, session_id = self.initialize_session()
        response = self.post_json(
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "missing_tool",
                    "arguments": {},
                },
            },
            headers=self.session_headers(session_id),
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["result"]["isError"])
        self.assertIn("not found", payload["result"]["content"][0]["text"])

    def test_delete_invalidates_session(self):
        _response, session_id = self.initialize_session()
        delete_response = self.client.delete(
            "/mcp",
            headers=self.session_headers(session_id),
        )
        self.assertEqual(delete_response.status_code, 204)

        response = self.post_json(
            {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/list",
                "params": {},
            },
            headers=self.session_headers(session_id),
        )

        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
