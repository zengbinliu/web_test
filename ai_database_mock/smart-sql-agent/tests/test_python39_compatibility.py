import ast
import unittest
from pathlib import Path


DEMO_ROOT = Path(__file__).resolve().parents[2]
EXCLUDED_DIRECTORIES = {".venv", "venv", "__pycache__"}


class Python39CompatibilityTests(unittest.TestCase):
    def test_all_project_sources_parse_as_python_39(self):
        python_files = [
            path
            for path in DEMO_ROOT.rglob("*.py")
            if not EXCLUDED_DIRECTORIES.intersection(path.parts)
        ]
        self.assertTrue(python_files)
        for source_path in python_files:
            with self.subTest(source=str(source_path.relative_to(DEMO_ROOT))):
                source = source_path.read_text(encoding="utf-8")
                ast.parse(
                    source,
                    filename=str(source_path),
                    feature_version=(3, 9),
                )


if __name__ == "__main__":
    unittest.main()
