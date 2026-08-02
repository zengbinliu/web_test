import sys
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine


APP_ROOT = Path(__file__).resolve().parents[1]
DEMO_ROOT = APP_ROOT.parent
if str(DEMO_ROOT) not in sys.path:
    sys.path.insert(0, str(DEMO_ROOT))

from build_table_graph import (  # noqa: E402
    build_table_relationship_graph,
    write_graph_json,
)
from backend.new_sql_agent import load_table_graph  # noqa: E402


class BuildTableGraphTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        database_path = Path(self.temp_directory.name) / "schema.db"
        self.engine = create_engine(f"sqlite:///{database_path.as_posix()}")
        with self.engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE parents (id INTEGER PRIMARY KEY, name VARCHAR(50) NOT NULL)"
            )
            connection.exec_driver_sql(
                "CREATE TABLE children ("
                "id INTEGER PRIMARY KEY, parent_id INTEGER NOT NULL, "
                "FOREIGN KEY(parent_id) REFERENCES parents(id))"
            )
            connection.exec_driver_sql(
                "CREATE TABLE audit_logs (id INTEGER PRIMARY KEY, parent_id INTEGER)"
            )

    def tearDown(self):
        self.engine.dispose()
        self.temp_directory.cleanup()

    def test_builds_typed_nodes_explicit_fk_and_inferred_relation(self):
        graph = build_table_relationship_graph(engine=self.engine)
        self.assertEqual(graph.graph["dialect"], "sqlite")
        self.assertEqual(graph.graph["sqlglot_dialect"], "sqlite")
        self.assertEqual(set(graph.nodes), {"parents", "children", "audit_logs"})
        self.assertIsInstance(graph.nodes["parents"]["columns"][0], dict)
        self.assertIn("generated", graph.nodes["parents"]["columns"][0])
        self.assertIn("unique_constraints", graph.nodes["parents"])

        relations = {
            (source, target, data["src_col"], data["dst_col"], data["type"])
            for source, target, data in graph.edges(data=True)
        }
        self.assertIn(
            ("children", "parents", "parent_id", "id", "explicit_fk"),
            relations,
        )
        self.assertIn(
            ("audit_logs", "parents", "parent_id", "id", "inferred_naming"),
            relations,
        )
        explicit_relation = next(
            data
            for source, target, data in graph.edges(data=True)
            if source == "children" and target == "parents"
        )
        self.assertEqual(explicit_relation["constrained_columns"], ["parent_id"])
        self.assertEqual(explicit_relation["referred_columns"], ["id"])

    def test_generated_json_is_consumable_by_agent(self):
        graph = build_table_relationship_graph(engine=self.engine)
        graph_path = Path(self.temp_directory.name) / "table_graph.json"
        write_graph_json(graph, graph_path)
        loaded_graph = load_table_graph(graph_path)
        self.assertEqual(set(loaded_graph.nodes), set(graph.nodes))
        self.assertEqual(loaded_graph.graph["graph_version"], 3)


if __name__ == "__main__":
    unittest.main()
