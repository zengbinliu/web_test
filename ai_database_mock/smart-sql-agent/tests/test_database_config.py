import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


APP_ROOT = Path(__file__).resolve().parents[1]
DEMO_ROOT = APP_ROOT.parent
if str(DEMO_ROOT) not in sys.path:
    sys.path.insert(0, str(DEMO_ROOT))

from database_config import (  # noqa: E402
    get_database_url,
    get_sqlglot_dialect,
)
from backend.new_sql_agent import parse_and_validate_sql, render_sql  # noqa: E402


class DatabaseConfigTests(unittest.TestCase):
    def test_database_url_takes_precedence(self):
        with patch.dict(
            os.environ,
            {"DATABASE_URL": "postgresql+psycopg://user:password@db.example/app"},
            clear=False,
        ):
            url = get_database_url()
        self.assertEqual(url.get_backend_name(), "postgresql")
        self.assertEqual(url.database, "app")
        self.assertEqual(get_sqlglot_dialect(url.get_backend_name()), "postgres")

    def test_legacy_mysql_settings_remain_supported(self):
        environment = {
            "DATABASE_URL": "",
            "DB_DIALECT": "mysql+mysqlconnector",
            "DB_HOST": "db.example",
            "DB_PORT": "3307",
            "DB_USER": "tester",
            "DB_PASSWORD": "secret",
            "DB_NAME": "sample",
        }
        with patch.dict(os.environ, environment, clear=False):
            url = get_database_url()
        self.assertEqual(url.get_backend_name(), "mysql")
        self.assertEqual(url.host, "db.example")
        self.assertEqual(url.port, 3307)
        self.assertEqual(url.database, "sample")

    def test_relative_sqlite_path_is_resolved_from_demo_root(self):
        with patch.dict(
            os.environ,
            {"DATABASE_URL": "", "DB_DIALECT": "sqlite", "DB_NAME": "data/test.db"},
            clear=False,
        ):
            url = get_database_url()
        self.assertEqual(Path(url.database), DEMO_ROOT / "data" / "test.db")

    def test_common_read_dialects_are_parsed(self):
        cases = {
            "mysql": "SELECT id FROM example LIMIT 10",
            "postgres": "SELECT id FROM example LIMIT 10",
            "tsql": "SELECT TOP 10 id FROM example",
            "oracle": "SELECT id FROM example FETCH FIRST 10 ROWS ONLY",
        }
        for dialect, sql in cases.items():
            with self.subTest(dialect=dialect):
                statement = parse_and_validate_sql(sql, {"example"}, dialect)[0]
                rendered = render_sql(statement, dialect)
                self.assertIn("example", rendered.lower())


if __name__ == "__main__":
    unittest.main()
