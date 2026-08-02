import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import networkx as nx
from sqlalchemy import create_engine, text


APP_ROOT = Path(__file__).resolve().parents[1]
DEMO_ROOT = APP_ROOT.parent
for import_path in (APP_ROOT, DEMO_ROOT):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from backend.new_sql_agent import (  # noqa: E402
    AgentError,
    NewSQLAgent,
    SQLValidationError,
    _llm_request,
    analyze_user_request,
    execute_sql_safe,
    parse_and_validate_sql,
    statement_type,
)


def node_link_data(graph):
    try:
        return nx.node_link_data(graph, edges="links")
    except TypeError:
        return nx.node_link_data(graph, link="links")


def add_table(graph, table_name, columns, primary_key="id"):
    graph.add_node(
        table_name,
        columns=[
            {
                "name": column_name,
                "type": "INTEGER" if column_name.endswith("id") else "VARCHAR(100)",
                "nullable": column_name != primary_key,
                "default": None,
                "primary_key": column_name == primary_key,
                "comment": None,
            }
            for column_name in columns
        ],
        primary_keys=[primary_key],
        primary_key=primary_key,
        object_type="table",
        comment=None,
    )


def create_test_graph(path):
    graph = nx.MultiDiGraph(
        graph_version=3,
        dialect="sqlite",
        sqlglot_dialect="sqlite",
        dialect_label="SQLite",
        schema="main",
    )
    add_table(
        graph,
        "accounts",
        ["id", "name", "contact_email", "password_hash"],
    )
    add_table(graph, "records", ["id", "account_id", "status"])
    add_table(graph, "record_items", ["id", "record_id", "product_id"])
    add_table(graph, "products", ["id", "name"])
    for table_name, required_columns in {
        "accounts": {"name"},
        "records": {"account_id"},
        "record_items": {"record_id", "product_id"},
        "products": {"name"},
    }.items():
        for column in graph.nodes[table_name]["columns"]:
            if column["name"] in required_columns:
                column["nullable"] = False
    graph.add_edge(
        "records", "accounts", src_col="account_id", dst_col="id",
        type="explicit_fk", confidence=1.0,
    )
    graph.add_edge(
        "record_items", "records", src_col="record_id", dst_col="id",
        type="explicit_fk", confidence=1.0,
    )
    graph.add_edge(
        "record_items", "products", src_col="product_id", dst_col="id",
        type="inferred_hint", confidence=0.95,
    )
    path.write_text(json.dumps(node_link_data(graph), ensure_ascii=False), encoding="utf-8")
    return graph


class DynamicGraphTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.graph_path = Path(self.temp_directory.name) / "table_graph.json"
        self.graph = create_test_graph(self.graph_path)

    def tearDown(self):
        self.temp_directory.cleanup()

    def test_prompt_uses_dynamic_schema_and_bridge_tables(self):
        agent = NewSQLAgent(self.graph_path)
        prompt = agent.build_prompt(
            "查询账户关联的产品",
            task_type="select",
            selected_tables={"accounts", "products"},
        )
        self.assertIn("accounts（table）", prompt)
        self.assertIn("records（table）", prompt)
        self.assertIn("record_items（table）", prompt)
        self.assertIn("products（table）", prompt)
        self.assertIn("record_items.product_id = products.id", prompt)
        self.assertIn("SQLite", prompt)

    def test_insert_prompt_includes_explicit_parent_dependencies(self):
        agent = NewSQLAgent(self.graph_path)
        prompt = agent.build_prompt(
            "创建一条记录",
            task_type="insert",
            selected_tables={"records"},
        )
        self.assertIn("records（table）", prompt)
        self.assertIn("accounts（table）", prompt)
        self.assertIn("records.account_id = accounts.id", prompt)

    @patch(
        "backend.new_sql_agent._llm_request",
        return_value='{"task_type":"select","tables":["accounts","products"]}',
    )
    def test_request_analysis_only_accepts_graph_tables(self, _request):
        analysis = analyze_user_request("查询账户关联的产品", self.graph)
        self.assertEqual(analysis["task_type"], "select")
        self.assertEqual(analysis["tables"], {"accounts", "products"})

    @patch(
        "backend.new_sql_agent._llm_request",
        return_value='{"task_type":"select","tables":["unknown_table"]}',
    )
    def test_request_analysis_rejects_unknown_tables(self, _request):
        with self.assertRaisesRegex(AgentError, "图谱之外"):
            analyze_user_request("查询不存在的表", self.graph)

    def test_agent_reloads_graph_after_file_changes(self):
        agent = NewSQLAgent(self.graph_path)
        self.assertNotIn("audit_log", agent.graph)
        add_table(self.graph, "audit_log", ["id", "message"])
        self.graph_path.write_text(
            json.dumps(node_link_data(self.graph), ensure_ascii=False),
            encoding="utf-8",
        )
        self.assertIn("audit_log", agent.graph)


class LLMRequestTests(unittest.TestCase):
    @patch("backend.new_sql_agent.requests.post")
    def test_gpt_56_uses_custom_chat_completions_endpoint(self, post):
        post.return_value.status_code = 200
        post.return_value.json.return_value = {
            "choices": [{"message": {"content": "SELECT 1;"}}]
        }
        settings = {
            "LLM_API_KEY": "test-key",
            "LLM_API_URL": "https://gateway.example/v1/chat/completions",
            "LLM_MODEL": "gpt-5.6",
            "LLM_REASONING_EFFORT": "none",
            "LLM_TIMEOUT_SECONDS": "23",
            "LLM_MAX_RETRIES": "2",
            "DEEP_API_KEY": "ignored-legacy-key",
            "DEEPSEEK_API_URL": "https://ignored.example/chat/completions",
            "DEEPSEEK_MODEL": "ignored-legacy-model",
        }

        with patch.dict(os.environ, settings, clear=True):
            result = _llm_request("生成 SQL")

        self.assertEqual(result, "SELECT 1;")
        post.assert_called_once()
        call = post.call_args
        self.assertEqual(call.args[0], settings["LLM_API_URL"])
        self.assertEqual(call.kwargs["headers"]["Authorization"], "Bearer test-key")
        self.assertEqual(call.kwargs["timeout"], 23)
        self.assertEqual(call.kwargs["json"]["model"], "gpt-5.6")
        self.assertEqual(call.kwargs["json"]["reasoning_effort"], "none")
        self.assertNotIn("temperature", call.kwargs["json"])

    @patch("backend.new_sql_agent.requests.post")
    def test_api_base_url_appends_chat_completions_path(self, post):
        post.return_value.status_code = 200
        post.return_value.json.return_value = {
            "choices": [{"message": {"content": "SELECT 1;"}}]
        }
        settings = {
            "LLM_API_KEY": "test-key",
            "LLM_API_URL": "https://gateway.example/v1/",
            "LLM_MODEL": "gpt-5.6",
        }

        with patch.dict(os.environ, settings, clear=True):
            result = _llm_request("test")

        self.assertEqual(result, "SELECT 1;")
        self.assertEqual(
            post.call_args.args[0],
            "https://gateway.example/v1/chat/completions",
        )

    @patch("backend.new_sql_agent.requests.post")
    def test_non_json_response_has_actionable_error(self, post):
        post.return_value.status_code = 200
        post.return_value.headers = {"Content-Type": "text/html; charset=utf-8"}
        post.return_value.text = "<html>route not found</html>"
        post.return_value.json.side_effect = ValueError("not JSON")
        settings = {
            "LLM_API_KEY": "test-key",
            "LLM_API_URL": "https://gateway.example/v1",
            "LLM_MODEL": "gpt-5.6",
            "LLM_MAX_RETRIES": "1",
        }

        with patch.dict(os.environ, settings, clear=True):
            with self.assertRaisesRegex(
                AgentError,
                "非 JSON 响应.*疑似 HTML.*v1/chat/completions",
            ):
                _llm_request("test")

    @patch("backend.new_sql_agent.requests.post")
    def test_legacy_deepseek_environment_variables_remain_supported(self, post):
        post.return_value.status_code = 200
        post.return_value.json.return_value = {
            "choices": [{"message": {"content": "legacy response"}}]
        }
        settings = {
            "DEEP_API_KEY": "legacy-key",
            "DEEPSEEK_API_URL": "https://legacy.example/chat/completions",
            "DEEPSEEK_MODEL": "legacy-model",
        }

        with patch.dict(os.environ, settings, clear=True):
            result = _llm_request("test")

        self.assertEqual(result, "legacy response")
        call = post.call_args
        self.assertEqual(call.args[0], settings["DEEPSEEK_API_URL"])
        self.assertEqual(call.kwargs["json"]["model"], "legacy-model")
        self.assertEqual(call.kwargs["headers"]["Authorization"], "Bearer legacy-key")


class SQLExecutionTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        root = Path(self.temp_directory.name)
        self.graph_path = root / "table_graph.json"
        self.graph = create_test_graph(self.graph_path)
        self.database_url = f"sqlite:///{(root / 'test.db').as_posix()}"
        engine = create_engine(self.database_url)
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE accounts (id INTEGER PRIMARY KEY, "
                "name VARCHAR(100) NOT NULL UNIQUE, "
                "contact_email VARCHAR(100), password_hash VARCHAR(100))"
            )
            connection.exec_driver_sql(
                "CREATE TABLE records (id INTEGER PRIMARY KEY, account_id INTEGER, status VARCHAR(100))"
            )
            connection.exec_driver_sql(
                "CREATE TABLE record_items (id INTEGER PRIMARY KEY, record_id INTEGER, product_id INTEGER)"
            )
            connection.exec_driver_sql(
                "CREATE TABLE products (id INTEGER PRIMARY KEY, name VARCHAR(100) NOT NULL)"
            )
        engine.dispose()

    def tearDown(self):
        self.temp_directory.cleanup()

    def engine_factory(self):
        return create_engine(self.database_url)

    def test_mixed_batch_detects_write_statement(self):
        statements = parse_and_validate_sql(
            "SELECT * FROM accounts; DELETE FROM accounts WHERE id = 9;",
            {"accounts"},
            "sqlite",
        )
        self.assertEqual([statement_type(item) for item in statements], ["select", "delete"])

    def test_update_and_delete_without_where_are_rejected(self):
        for sql in ("UPDATE accounts SET name = 'x'", "DELETE FROM accounts"):
            with self.subTest(sql=sql), self.assertRaisesRegex(SQLValidationError, "WHERE"):
                parse_and_validate_sql(sql, {"accounts"}, "sqlite")

    def test_ddl_and_unknown_tables_are_rejected(self):
        with self.assertRaisesRegex(SQLValidationError, "不支持"):
            parse_and_validate_sql("DROP TABLE accounts", {"accounts"}, "sqlite")
        with self.assertRaisesRegex(SQLValidationError, "图谱之外"):
            parse_and_validate_sql("SELECT * FROM secrets", {"accounts"}, "sqlite")
        with self.assertRaisesRegex(SQLValidationError, "图谱之外"):
            parse_and_validate_sql(
                "SELECT * FROM other.accounts",
                {"accounts"},
                "sqlite",
                allowed_schema="main",
            )

    def test_insert_preview_does_not_open_database(self):
        result = execute_sql_safe(
            "INSERT INTO accounts (id, name) VALUES (1, 'a'), (2, 'b')",
            preview_only=True,
            graph_path=self.graph_path,
            engine_factory=lambda: self.fail("insert preview should not connect"),
        )
        self.assertEqual(result["type"], "insert_preview")
        self.assertEqual(result["affected_rows"], 2)
        self.assertEqual(result["inferred_values_added"], 4)
        self.assertIn("contact_email", result["planned_sql"])
        self.assertIn("password_hash", result["planned_sql"])
        self.assertIn("@example.test", result["planned_sql"])
        self.assertTrue(result["requires_confirmation"])

        execution = execute_sql_safe(
            result["planned_sql"],
            preview_only=False,
            graph_path=self.graph_path,
            engine_factory=self.engine_factory,
        )
        self.assertEqual(execution["type"], "write_executed")
        engine = self.engine_factory()
        with engine.connect() as connection:
            accounts = connection.execute(
                text(
                    "SELECT contact_email, password_hash "
                    "FROM accounts ORDER BY id"
                )
            ).mappings().all()
        engine.dispose()
        self.assertEqual(len(accounts), 2)
        self.assertTrue(
            all(row["contact_email"].endswith("@example.test") for row in accounts)
        )
        self.assertTrue(all(len(row["password_hash"]) == 64 for row in accounts))

    def test_explicit_semantic_values_are_not_overwritten(self):
        result = execute_sql_safe(
            "INSERT INTO accounts "
            "(id, name, contact_email, password_hash) VALUES "
            "(1, 'a', 'explicit@example.org', 'explicit-hash')",
            preview_only=True,
            graph_path=self.graph_path,
            engine_factory=lambda: self.fail("preview should not connect"),
        )

        self.assertNotIn("inferred_values_added", result)
        self.assertNotIn("planned_sql", result)
        self.assertIn("explicit@example.org", result["sql"])
        self.assertIn("explicit-hash", result["sql"])

    def test_missing_parent_is_added_to_preview_and_executed_first(self):
        preview = execute_sql_safe(
            "INSERT INTO records (id, account_id, status) VALUES (10, 77, 'new')",
            preview_only=True,
            graph_path=self.graph_path,
            engine_factory=self.engine_factory,
        )
        self.assertEqual(preview["type"], "batch_preview")
        self.assertEqual(preview["dependency_rows_added"], 1)
        self.assertTrue(preview["results"][0]["auto_created_dependency"])
        planned_sql = preview["planned_sql"]
        self.assertLess(planned_sql.index("accounts"), planned_sql.index("records"))

        execution = execute_sql_safe(
            planned_sql,
            preview_only=False,
            graph_path=self.graph_path,
            engine_factory=self.engine_factory,
        )
        self.assertEqual(execution["type"], "batch_execution")
        engine = self.engine_factory()
        with engine.connect() as connection:
            account = connection.execute(
                text(
                    "SELECT id, name, contact_email, password_hash "
                    "FROM accounts WHERE id = 77"
                )
            ).mappings().one()
            record = connection.execute(
                text("SELECT id, account_id FROM records WHERE id = 10")
            ).mappings().one()
        engine.dispose()
        self.assertTrue(account["name"].startswith("test_"))
        self.assertTrue(account["contact_email"].endswith("@example.test"))
        self.assertEqual(len(account["password_hash"]), 64)
        self.assertEqual(record["account_id"], 77)

    def test_existing_parent_is_reused_without_extra_insert(self):
        engine = self.engine_factory()
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO accounts (id, name) VALUES (77, 'existing')"))
        engine.dispose()

        preview = execute_sql_safe(
            "INSERT INTO records (id, account_id, status) VALUES (10, 77, 'new')",
            preview_only=True,
            graph_path=self.graph_path,
            engine_factory=self.engine_factory,
        )
        self.assertEqual(preview["type"], "insert_preview")
        self.assertNotIn("dependency_rows_added", preview)
        self.assertFalse(preview["auto_created_dependency"])

    def test_existing_batch_parent_is_reordered_before_child(self):
        preview = execute_sql_safe(
            "INSERT INTO records (id, account_id) VALUES (10, 77);"
            "INSERT INTO accounts (id, name) VALUES (77, 'batch-parent');",
            preview_only=True,
            graph_path=self.graph_path,
            engine_factory=self.engine_factory,
        )
        planned_sql = preview["planned_sql"]
        self.assertLess(planned_sql.index("accounts"), planned_sql.index("records"))
        self.assertNotIn("dependency_rows_added", preview)

    def test_missing_required_foreign_key_reuses_existing_parent(self):
        engine = self.engine_factory()
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO accounts (id, name) VALUES (5, 'existing')"))
        engine.dispose()

        preview = execute_sql_safe(
            "INSERT INTO records (id, status) VALUES (10, 'new')",
            preview_only=True,
            graph_path=self.graph_path,
            engine_factory=self.engine_factory,
        )
        self.assertIn("account_id", preview["planned_sql"])
        self.assertIn("5", preview["planned_sql"])
        self.assertNotIn("dependency_rows_added", preview)

    def test_dependency_change_after_preview_requires_new_preview(self):
        engine = self.engine_factory()
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO accounts (id, name) VALUES (5, 'existing')"))
        engine.dispose()
        preview = execute_sql_safe(
            "INSERT INTO records (id, status) VALUES (10, 'new')",
            preview_only=True,
            graph_path=self.graph_path,
            engine_factory=self.engine_factory,
        )

        engine = self.engine_factory()
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM accounts WHERE id = 5"))
        engine.dispose()
        execution = execute_sql_safe(
            preview["planned_sql"],
            preview_only=False,
            graph_path=self.graph_path,
            engine_factory=self.engine_factory,
        )
        self.assertEqual(execution["type"], "error")
        self.assertIn("重新预览", execution["message"])

        engine = self.engine_factory()
        with engine.connect() as connection:
            count = connection.execute(text("SELECT COUNT(*) FROM records")).scalar_one()
        engine.dispose()
        self.assertEqual(count, 0)

    def test_dependencies_are_filled_recursively(self):
        preview = execute_sql_safe(
            "INSERT INTO record_items (id, record_id, product_id) VALUES (1, 10, 20)",
            preview_only=True,
            graph_path=self.graph_path,
            engine_factory=self.engine_factory,
        )
        self.assertEqual(preview["dependency_rows_added"], 2)
        planned_sql = preview["planned_sql"]
        self.assertLess(planned_sql.index("accounts"), planned_sql.index("records"))
        self.assertLess(planned_sql.index("records"), planned_sql.index("record_items"))
        self.assertNotIn("INSERT INTO products", planned_sql)

    def test_identity_parent_key_fails_closed(self):
        for column in self.graph.nodes["accounts"]["columns"]:
            if column["name"] == "id":
                column["identity"] = {"always": True}
                column["generated"] = True
        self.graph_path.write_text(
            json.dumps(node_link_data(self.graph), ensure_ascii=False),
            encoding="utf-8",
        )
        result = execute_sql_safe(
            "INSERT INTO records (id, account_id) VALUES (10, 99)",
            preview_only=True,
            graph_path=self.graph_path,
            engine_factory=self.engine_factory,
        )
        self.assertEqual(result["type"], "error")
        self.assertIn("强制生成", result["message"])

    def test_update_preview_uses_target_dialect(self):
        engine = self.engine_factory()
        with engine.begin() as connection:
            connection.exec_driver_sql("INSERT INTO accounts (id, name) VALUES (1, 'a')")
        engine.dispose()

        result = execute_sql_safe(
            "UPDATE accounts SET name = 'updated' WHERE id = 1",
            preview_only=True,
            graph_path=self.graph_path,
            engine_factory=self.engine_factory,
        )
        self.assertEqual(result["type"], "write_preview")
        self.assertEqual(result["affected_rows"], 1)
        self.assertEqual(result["preview_rows"][0]["name"], "a")

    def test_batch_write_rolls_back_as_one_transaction(self):
        sql = (
            "INSERT INTO accounts (id, name) VALUES (1, 'a');"
            "INSERT INTO accounts (id, name) VALUES (1, 'duplicate');"
        )
        result = execute_sql_safe(
            sql,
            preview_only=False,
            graph_path=self.graph_path,
            engine_factory=self.engine_factory,
        )
        self.assertEqual(result["type"], "error")

        engine = self.engine_factory()
        with engine.connect() as connection:
            count = connection.execute(text("SELECT COUNT(*) FROM accounts")).scalar_one()
        engine.dispose()
        self.assertEqual(count, 0)

    def test_select_is_limited_by_server(self):
        engine = self.engine_factory()
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "INSERT INTO accounts (id, name) VALUES "
                + ",".join(f"({index}, 'name-{index}')" for index in range(1, 121))
            )
        engine.dispose()
        result = execute_sql_safe(
            "SELECT id, name FROM accounts ORDER BY id",
            graph_path=self.graph_path,
            engine_factory=self.engine_factory,
        )
        self.assertEqual(result["type"], "select")
        self.assertEqual(len(result["rows"]), 100)


if __name__ == "__main__":
    unittest.main()
