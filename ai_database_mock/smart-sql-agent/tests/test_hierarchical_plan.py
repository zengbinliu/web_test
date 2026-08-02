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

from backend.hierarchical_plan import (  # noqa: E402
    DataPlanError,
    canonical_hierarchical_plan,
    parse_hierarchical_plan,
    render_hierarchical_sql,
    validate_plan_values,
)
from backend.new_sql_agent import NewSQLAgent, execute_sql_safe  # noqa: E402


def node_link_data(graph):
    try:
        return nx.node_link_data(graph, edges="links")
    except TypeError:
        return nx.node_link_data(graph, link="links")


def column(
    name,
    type_name,
    nullable=False,
    default=None,
    primary_key=False,
    generated=False,
    autoincrement=False,
):
    return {
        "name": name,
        "type": type_name,
        "nullable": nullable,
        "default": default,
        "primary_key": primary_key,
        "comment": None,
        "generated": generated,
        "autoincrement": autoincrement,
        "identity": None,
        "computed": None,
    }


def create_hierarchy_graph(path):
    graph = nx.MultiDiGraph(
        graph_version=3,
        dialect="sqlite",
        sqlglot_dialect="sqlite",
        dialect_label="SQLite",
        schema="main",
    )
    graph.add_node(
        "root_records",
        columns=[
            column("id", "INTEGER", primary_key=True, generated=True, autoincrement=True),
            column("root_code", "VARCHAR(64)"),
            column("contact_email", "VARCHAR(80)", nullable=True),
            column("password_hash", "VARCHAR(64)", nullable=True),
        ],
        primary_keys=["id"],
        primary_key="id",
        object_type="table",
        unique_constraints=[{"name": "uq_root_records_root_code", "columns": ["root_code"]}],
    )
    graph.add_node(
        "child_records",
        columns=[
            column("id", "INTEGER", primary_key=True, generated=True, autoincrement=True),
            column("root_id", "INTEGER"),
            column("child_code", "VARCHAR(48)"),
            column("required_text", "VARCHAR(128)"),
            column("unit_price", "DECIMAL(10,2)", nullable=True, default="0.00"),
        ],
        primary_keys=["id"],
        primary_key="id",
        object_type="table",
        unique_constraints=[{"name": "uq_child_records_child_code", "columns": ["child_code"]}],
    )
    graph.add_node(
        "leaf_records",
        columns=[
            column("id", "INTEGER", primary_key=True, generated=True, autoincrement=True),
            column("child_id", "INTEGER"),
            column("position_index", "INTEGER"),
            column("line_no", "INTEGER", default="0"),
            column("payload_value", "VARCHAR(128)"),
            column("quantity", "INTEGER", default="1"),
            column("details", "JSON", nullable=True),
            column("material_list", "JSON", nullable=True),
            column("snapshot_label", "VARCHAR(128)", nullable=True),
        ],
        primary_keys=["id"],
        primary_key="id",
        object_type="table",
        unique_constraints=[],
    )
    graph.add_edge(
        "child_records",
        "root_records",
        src_col="root_id",
        dst_col="id",
        constrained_columns=["root_id"],
        referred_columns=["id"],
        constraint_name="fk_child_root",
        type="explicit_fk",
        confidence=1.0,
    )
    graph.add_edge(
        "leaf_records",
        "child_records",
        src_col="child_id",
        dst_col="id",
        constrained_columns=["child_id"],
        referred_columns=["id"],
        constraint_name="fk_leaf_child",
        type="explicit_fk",
        confidence=1.0,
    )
    path.write_text(json.dumps(node_link_data(graph), ensure_ascii=False), encoding="utf-8")
    return graph


def plan_payload(item_values=None):
    return {
        "kind": "hierarchical_insert",
        "version": 1,
        "entities": [
            {
                "id": "root_records",
                "table": "root_records",
                "count": 2,
                "count_mode": "exactly",
                "values": {},
            },
            {
                "id": "child_records",
                "table": "child_records",
                "parent": "root_records",
                "count_per_parent": 3,
                "count_mode": "exactly",
                "relationship": "fk_child_root",
                "values": {"required_text": "child-value"},
            },
            {
                "id": "items",
                "table": "leaf_records",
                "parent": "child_records",
                "count_per_parent": 4,
                "count_mode": "at_least",
                "relationship": "fk_leaf_child",
                "values": item_values or {"payload_value": "测试明细"},
                "generators": {
                    "position_index": {
                        "strategy": "sequence",
                        "start": 1,
                        "step": 1,
                        "scope": "parent",
                    }
                },
            },
        ],
    }


class HierarchicalPlanTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        root = Path(self.temp_directory.name)
        self.graph_path = root / "table_graph.json"
        self.graph = create_hierarchy_graph(self.graph_path)
        self.database_url = f"sqlite:///{(root / 'hierarchy.db').as_posix()}"
        engine = create_engine(self.database_url)
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE root_records (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "root_code VARCHAR(64) NOT NULL UNIQUE, "
                "contact_email VARCHAR(80), password_hash VARCHAR(64))"
            )
            connection.exec_driver_sql(
                "CREATE TABLE child_records (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "root_id INTEGER NOT NULL REFERENCES root_records(id), "
                "child_code VARCHAR(48) NOT NULL UNIQUE, "
                "required_text VARCHAR(128) NOT NULL, "
                "unit_price DECIMAL(10,2) DEFAULT 0.00)"
            )
            connection.exec_driver_sql(
                "CREATE TABLE leaf_records (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "child_id INTEGER NOT NULL REFERENCES child_records(id), "
                "position_index INTEGER NOT NULL, "
                "line_no INTEGER NOT NULL DEFAULT 0, "
                "payload_value VARCHAR(128) NOT NULL, "
                "quantity INTEGER NOT NULL DEFAULT 1 CHECK(quantity > 0), "
                "details JSON, material_list JSON, snapshot_label VARCHAR(128))"
            )
        engine.dispose()

    def tearDown(self):
        self.temp_directory.cleanup()

    def engine_factory(self):
        engine = create_engine(self.database_url)
        with engine.connect() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys = ON")
        return engine

    def canonical_plan(self, item_values=None):
        plan = parse_hierarchical_plan(
            json.dumps(plan_payload(item_values)),
            self.graph,
            require_plan=True,
        )
        return canonical_hierarchical_plan(plan)

    def test_preview_calculates_all_hierarchy_counts_without_database(self):
        result = execute_sql_safe(
            self.canonical_plan(),
            preview_only=True,
            graph_path=self.graph_path,
            engine_factory=lambda: self.fail("preview must not connect to database"),
        )
        self.assertEqual(result["type"], "data_plan_preview")
        self.assertEqual(result["total_rows"], 32)
        self.assertEqual([item["rows"] for item in result["entities"]], [2, 6, 24])
        self.assertIn("INSERT INTO", result["sql_preview"])
        self.assertTrue(result["requires_confirmation"])

    def test_execution_captures_generated_keys_and_preserves_cardinality(self):
        result = execute_sql_safe(
            self.canonical_plan(),
            preview_only=False,
            graph_path=self.graph_path,
            engine_factory=self.engine_factory,
        )
        self.assertEqual(result["type"], "data_plan_execution")
        self.assertEqual(result["total_rows"], 32)

        engine = self.engine_factory()
        with engine.connect() as connection:
            self.assertEqual(connection.execute(text("SELECT COUNT(*) FROM root_records")).scalar_one(), 2)
            child_counts = connection.execute(
                text("SELECT root_id, COUNT(*) count FROM child_records GROUP BY root_id")
            ).all()
            item_counts = connection.execute(
                text("SELECT child_id, COUNT(*) count FROM leaf_records GROUP BY child_id")
            ).all()
            positions = connection.execute(
                text(
                    "SELECT child_id, GROUP_CONCAT(position_index) positions "
                    "FROM leaf_records GROUP BY child_id"
                )
            ).all()
            root_values = connection.execute(
                text("SELECT contact_email, password_hash FROM root_records")
            ).all()
            prices = connection.execute(
                text("SELECT unit_price FROM child_records")
            ).scalars().all()
            inferred_leaf_values = connection.execute(
                text(
                    "SELECT line_no, quantity, material_list, snapshot_label "
                    "FROM leaf_records"
                )
            ).all()
            self.assertEqual([row.count for row in child_counts], [3, 3])
            self.assertEqual([row.count for row in item_counts], [4] * 6)
            self.assertEqual([row.positions for row in positions], ["1,2,3,4"] * 6)
            self.assertTrue(
                all("@example.test" in row.contact_email for row in root_values)
            )
            self.assertTrue(all(len(row.password_hash) == 64 for row in root_values))
            self.assertTrue(all(value > 0 for value in prices))
            self.assertEqual(
                [row.line_no for row in inferred_leaf_values],
                [1, 2, 3, 4] * 6,
            )
            self.assertTrue(all(row.quantity > 0 for row in inferred_leaf_values))
            self.assertTrue(
                all(row.material_list not in (None, "", "{}", "[]") for row in inferred_leaf_values)
            )
            self.assertTrue(
                all(row.snapshot_label.startswith("snapshot_") for row in inferred_leaf_values)
            )
        engine.dispose()

    def test_explicit_values_override_semantic_inference(self):
        payload = plan_payload()
        payload["entities"][0]["values"] = {
            "contact_email": "explicit@example.org",
            "password_hash": "explicit_hash",
        }
        payload["entities"][1]["values"]["unit_price"] = 0
        payload["entities"][2]["values"].update(
            {"line_no": 99, "material_list": [], "snapshot_label": "explicit"}
        )
        plan = parse_hierarchical_plan(
            json.dumps(payload),
            self.graph,
            require_plan=True,
        )

        sql = render_hierarchical_sql(plan, self.graph)

        self.assertIn("'explicit@example.org'", sql)
        self.assertIn("'explicit_hash'", sql)
        self.assertIn("'explicit'", sql)
        self.assertIn("99", sql)

    def test_constraint_failure_rolls_back_every_level(self):
        result = execute_sql_safe(
            self.canonical_plan({"payload_value": "测试明细", "quantity": -1}),
            preview_only=False,
            graph_path=self.graph_path,
            engine_factory=self.engine_factory,
        )
        self.assertEqual(result["type"], "error")
        engine = self.engine_factory()
        with engine.connect() as connection:
            self.assertEqual(connection.execute(text("SELECT COUNT(*) FROM root_records")).scalar_one(), 0)
            self.assertEqual(connection.execute(text("SELECT COUNT(*) FROM child_records")).scalar_one(), 0)
            self.assertEqual(connection.execute(text("SELECT COUNT(*) FROM leaf_records")).scalar_one(), 0)
        engine.dispose()

    def test_generated_columns_and_unknown_relationships_are_rejected(self):
        payload = plan_payload()
        payload["entities"][0]["values"] = {"id": 99}
        with self.assertRaisesRegex(DataPlanError, "数据库生成字段"):
            parse_hierarchical_plan(json.dumps(payload), self.graph, require_plan=True)

        payload = plan_payload()
        payload["entities"][1]["relationship"] = "missing_fk"
        with self.assertRaisesRegex(DataPlanError, "不存在.*显式外键"):
            parse_hierarchical_plan(json.dumps(payload), self.graph, require_plan=True)

        payload = plan_payload()
        payload["entities"][2]["values"] = {}
        payload["entities"][2]["generators"] = {
            "payload_value": {"strategy": "sequence"}
        }
        with self.assertRaisesRegex(DataPlanError, "只支持数值字段"):
            parse_hierarchical_plan(json.dumps(payload), self.graph, require_plan=True)

    def test_relationship_field_expression_resolves_to_explicit_foreign_key(self):
        payload = plan_payload()
        payload["entities"][1]["relationship"] = "child_records.root_id = root_records.id"
        payload["entities"][2]["relationship"] = (
            "child_records.id = leaf_records.child_id"
        )

        plan = parse_hierarchical_plan(
            json.dumps(payload),
            self.graph,
            require_plan=True,
        )

        self.assertEqual(plan.entities[1].relationship.constraint_name, "fk_child_root")
        self.assertEqual(plan.entities[2].relationship.constraint_name, "fk_leaf_child")
        canonical = canonical_hierarchical_plan(plan)
        self.assertIn('"relationship": "fk_child_root"', canonical)
        self.assertIn('"relationship": "fk_leaf_child"', canonical)
        self.assertIn('"strategy": "sequence"', canonical)

    def test_mysql_preview_contains_concrete_hierarchical_sql_and_json_values(self):
        payload = plan_payload(
            {
                "payload_value": "测试标签",
                "quantity": 1,
                "details": {"key": "value"},
            }
        )
        self.graph.graph["dialect"] = "mysql"
        plan = parse_hierarchical_plan(
            json.dumps(payload, ensure_ascii=False),
            self.graph,
            require_plan=True,
        )

        sql = render_hierarchical_sql(plan, self.graph)

        self.assertIn("START TRANSACTION;", sql)
        self.assertIn("SET @plan_root_records_1_id = LAST_INSERT_ID();", sql)
        self.assertIn("@plan_root_records_1_id", sql)
        self.assertIn("@plan_child_records_1_id", sql)
        self.assertIn("'测试标签'", sql)
        self.assertIn('"key":"value"', sql)
        self.assertIn("`position_index`", sql)
        self.assertTrue(sql.rstrip().endswith("COMMIT;"))
        reparsed = parse_hierarchical_plan(
            canonical_hierarchical_plan(plan),
            self.graph,
            require_plan=True,
        )
        self.assertEqual(render_hierarchical_sql(reparsed, self.graph), sql)

    def test_total_row_limit_is_enforced(self):
        settings = {"DATA_PLAN_MAX_ROWS": "31"}
        with patch.dict(os.environ, settings, clear=False):
            with self.assertRaisesRegex(DataPlanError, "总行数 32"):
                parse_hierarchical_plan(
                    json.dumps(plan_payload()),
                    self.graph,
                    require_plan=True,
                )

    def test_required_values_cannot_be_omitted(self):
        payload = plan_payload()
        payload["entities"][1]["values"] = {}
        payload["entities"][2]["values"] = {}
        plan = parse_hierarchical_plan(
            json.dumps(payload),
            self.graph,
            require_plan=True,
        )
        with self.assertRaisesRegex(
            DataPlanError,
            "required_text.*payload_value",
        ):
            validate_plan_values(plan, self.graph)

    def test_required_values_reject_empty_content(self):
        payload = plan_payload()
        payload["entities"][1]["values"]["required_text"] = ""
        payload["entities"][2]["values"]["payload_value"] = " "
        plan = parse_hierarchical_plan(
            json.dumps(payload),
            self.graph,
            require_plan=True,
        )

        with self.assertRaisesRegex(
            DataPlanError,
            "不能使用.*required_text.*payload_value",
        ):
            validate_plan_values(plan, self.graph)

    @patch("backend.new_sql_agent.call_llm")
    @patch("backend.new_sql_agent.analyze_user_request")
    def test_multi_table_insert_generation_returns_validated_plan(self, analyze, call_llm):
        analyze.return_value = {
            "task_type": "insert",
            "tables": {"root_records", "child_records", "leaf_records"},
        }
        call_llm.return_value = json.dumps(plan_payload())
        agent = NewSQLAgent(self.graph_path)

        generated = agent.generate_sql("创建根记录、子记录和叶子记录")

        self.assertIn('"kind": "hierarchical_insert"', generated)
        self.assertIn('"graph_fingerprint"', generated)
        prompt = call_llm.call_args.args[0]
        self.assertIn("分层测试数据规划器", prompt)
        self.assertIn("count_per_parent", prompt)

    @patch("backend.new_sql_agent.call_llm")
    @patch("backend.new_sql_agent.analyze_user_request")
    def test_invalid_required_values_are_regenerated_once(self, analyze, call_llm):
        analyze.return_value = {
            "task_type": "insert",
            "tables": {"root_records", "child_records", "leaf_records"},
        }
        invalid = plan_payload()
        invalid["entities"][1]["values"] = {}
        invalid["entities"][2]["values"] = {}
        call_llm.side_effect = [
            json.dumps(invalid),
            json.dumps(plan_payload()),
        ]
        agent = NewSQLAgent(self.graph_path)

        generated = agent.generate_sql("创建根记录、子记录和叶子记录")

        self.assertIn('"kind": "hierarchical_insert"', generated)
        self.assertEqual(call_llm.call_count, 2)
        self.assertIn("上一次输出未通过系统校验", call_llm.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
