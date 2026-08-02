import unittest
from unittest.mock import PropertyMock, patch

from backend.main import (
    app,
    issue_confirmation_token,
    validate_confirmation_token,
)
from backend.models import RequestValidationError


class FlaskAPITests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()

    def test_frontend_is_served_by_flask(self):
        response = self.client.get("/")
        try:
            self.assertEqual(response.status_code, 200)
            self.assertIn("智能 SQL 助手", response.get_data(as_text=True))
        finally:
            response.close()

    def test_generate_validates_request(self):
        response = self.client.post("/generate", json={"natural_language": ""})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.get_json()["success"])

    @patch("backend.main.agent.generate_sql", return_value="SELECT id FROM any_table LIMIT 5;")
    def test_generate_returns_sql(self, generate_sql):
        response = self.client.post("/generate", json={"natural_language": "查询数据"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["data"]["sql"], "SELECT id FROM any_table LIMIT 5;")
        self.assertEqual(response.get_json()["data"]["artifact_type"], "sql")
        generate_sql.assert_called_once_with("查询数据")

    @patch(
        "backend.main.agent.generate_sql",
        return_value='{"kind":"hierarchical_insert","version":1,"entities":[]}',
    )
    @patch("backend.main.parse_hierarchical_plan", return_value=object())
    @patch("backend.main.render_hierarchical_sql", return_value="START TRANSACTION;\nCOMMIT;")
    @patch("backend.main.agent.__class__.graph", new_callable=PropertyMock)
    def test_generate_identifies_hierarchical_data_plan(
        self,
        graph_property,
        _render_sql,
        _parse_plan,
        _generate,
    ):
        graph_property.return_value = object()
        response = self.client.post(
            "/generate",
            json={"natural_language": "创建父记录和子记录"},
        )
        payload = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["data"]["artifact_type"], "data_plan")
        self.assertIn("START TRANSACTION", payload["data"]["sql_preview"])
        self.assertIn("分层数据计划", payload["message"])

    @patch(
        "backend.main.execute_sql_safe",
        return_value={"type": "error", "message": "UPDATE 必须包含 WHERE 条件"},
    )
    def test_execute_returns_validation_error(self, _execute):
        response = self.client.post(
            "/execute",
            json={"sql": "UPDATE any_table SET value = 1", "confirm": False},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("WHERE", response.get_json()["message"])

    def test_write_cannot_skip_preview(self):
        response = self.client.post(
            "/execute",
            json={"sql": "INSERT INTO any_table (id) VALUES (1)", "confirm": True},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("先预览", response.get_json()["message"])

    def test_confirmation_token_is_bound_to_sql(self):
        token = issue_confirmation_token("INSERT INTO any_table (id) VALUES (1)")
        response = self.client.post(
            "/execute",
            json={
                "sql": "INSERT INTO any_table (id) VALUES (2)",
                "confirm": True,
                "confirmation_token": token,
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("发生变化", response.get_json()["message"])

    @patch(
        "backend.main.execute_sql_safe",
        return_value={
            "type": "insert_preview",
            "operation": "INSERT",
            "affected_rows": 1,
            "sql": "INSERT INTO any_table (id) VALUES (1)",
            "requires_confirmation": True,
        },
    )
    def test_preview_returns_confirmation_token(self, _execute):
        response = self.client.post(
            "/execute",
            json={"sql": "INSERT INTO any_table (id) VALUES (1)", "confirm": False},
        )
        payload = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["requires_confirmation"])
        self.assertTrue(payload["data"]["confirmation_token"])

    @patch(
        "backend.main.execute_sql_safe",
        return_value={
            "type": "batch_preview",
            "statements_count": 2,
            "results": [],
            "planned_sql": (
                "INSERT INTO parents (id, name) VALUES (7, 'auto_dep_test');\n"
                "INSERT INTO children (id, parent_id) VALUES (1, 7);"
            ),
            "dependency_rows_added": 1,
            "requires_confirmation": True,
        },
    )
    def test_dependency_preview_token_is_bound_to_planned_sql(self, _execute):
        original_sql = "INSERT INTO children (id, parent_id) VALUES (1, 7)"
        response = self.client.post(
            "/execute",
            json={"sql": original_sql, "confirm": False},
        )
        payload = response.get_json()
        planned_sql = payload["data"]["planned_sql"]
        token = payload["data"]["confirmation_token"]
        validate_confirmation_token(planned_sql, token)
        with self.assertRaises(RequestValidationError):
            validate_confirmation_token(original_sql, token)
        self.assertIn("自动补齐 1 条", payload["message"])

    @patch(
        "backend.main.execute_sql_safe",
        return_value={
            "type": "insert_preview",
            "operation": "INSERT",
            "affected_rows": 1,
            "sql": "INSERT INTO samples (id, email) VALUES (1, 'test@example.test')",
            "planned_sql": (
                "INSERT INTO samples (id, email) "
                "VALUES (1, 'test@example.test');"
            ),
            "inferred_values_added": 1,
            "requires_confirmation": True,
        },
    )
    def test_inferred_value_preview_token_is_bound_to_planned_sql(self, _execute):
        original_sql = "INSERT INTO samples (id) VALUES (1)"
        response = self.client.post(
            "/execute",
            json={"sql": original_sql, "confirm": False},
        )

        payload = response.get_json()
        planned_sql = payload["data"]["planned_sql"]
        validate_confirmation_token(
            planned_sql,
            payload["data"]["confirmation_token"],
        )
        self.assertIn("生成 1 个缺省值", payload["message"])

    @patch(
        "backend.main.execute_sql_safe",
        return_value={
            "type": "data_plan_preview",
            "entity_count": 3,
            "total_rows": 310,
            "statements_count": 310,
            "entities": [],
            "planned_artifact": '{"kind":"hierarchical_insert","version":1}',
            "requires_confirmation": True,
        },
    )
    def test_data_plan_confirmation_is_bound_to_canonical_artifact(self, _execute):
        original = '{ "kind": "hierarchical_insert", "version": 1 }'
        response = self.client.post(
            "/execute",
            json={"sql": original, "confirm": False},
        )
        payload = response.get_json()
        canonical = payload["data"]["planned_artifact"]
        token = payload["data"]["confirmation_token"]
        validate_confirmation_token(canonical, token)
        with self.assertRaises(RequestValidationError):
            validate_confirmation_token(original, token)
        self.assertIn("310 行", payload["message"])


if __name__ == "__main__":
    unittest.main()
