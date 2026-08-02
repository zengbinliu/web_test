import sys
import unittest
from decimal import Decimal
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from backend.field_semantics import (  # noqa: E402
    generate_field_value,
    infer_field_semantic,
)


def column(name, type_name="VARCHAR(128)", **attributes):
    result = {
        "name": name,
        "type": type_name,
        "length": attributes.pop("length", None),
        "precision": attributes.pop("precision", None),
        "scale": attributes.pop("scale", None),
        "enum_values": attributes.pop("enum_values", []),
    }
    result.update(attributes)
    return result


class FieldSemanticsTests(unittest.TestCase):
    def test_common_field_names_are_classified(self):
        cases = {
            "contact_email": "email",
            "user_mail": "email",
            "passwordHash": "password_hash",
            "login_pwd": "password",
            "password_salt": "salt",
            "total_amount": "money",
            "unit_price": "money",
            "ingredient_cost": "money",
            "item_count": "quantity",
            "material_list": "material",
            "snapshot_name": "snapshot",
            "line_no": "sequence",
            "sortOrder": "sequence",
            "mobile_phone": "phone",
            "callback_url": "url",
            "reference_code": "code",
            "联系邮箱": "email",
            "密码哈希": "password_hash",
            "密码盐值": "salt",
            "成交金额": "money",
            "材料清单": "material",
            "数据快照": "snapshot",
            "明细行号": "sequence",
        }
        for name, expected in cases.items():
            with self.subTest(name=name):
                self.assertEqual(infer_field_semantic(column(name)), expected)

    def test_semantic_values_are_deterministic_and_type_appropriate(self):
        token = "0123456789abcdef"
        email_column = column("contact_email", length=80)
        hash_column = column("password_hash", length=64)
        money_column = column(
            "unit_price",
            "DECIMAL(12,2)",
            precision=12,
            scale=2,
        )
        material_column = column("material_list", "JSON")
        snapshot_column = column("snapshot_name", length=64)
        snapshot_version_column = column("snapshot_version", "INTEGER")
        sequence_column = column("line_no", "INTEGER")

        email = generate_field_value(email_column, token)
        password_hash = generate_field_value(hash_column, token)
        amount = generate_field_value(money_column, token)
        materials = generate_field_value(material_column, token)
        snapshot = generate_field_value(snapshot_column, token)
        snapshot_version = generate_field_value(snapshot_version_column, token)
        sequence = generate_field_value(sequence_column, token, sequence_index=7)

        self.assertEqual(email, generate_field_value(email_column, token))
        self.assertTrue(email.endswith("@example.test"))
        self.assertEqual(len(password_hash), 64)
        self.assertIsInstance(amount, Decimal)
        self.assertGreater(amount, 0)
        self.assertIsInstance(materials, list)
        self.assertTrue(materials)
        self.assertTrue(snapshot.startswith("snapshot_"))
        self.assertIsInstance(snapshot_version, int)
        self.assertGreater(snapshot_version, 0)
        self.assertEqual(sequence, 7)

    def test_short_email_column_still_receives_email_shaped_value(self):
        email = generate_field_value(
            column("email", "VARCHAR(8)", length=8),
            "token",
        )

        self.assertEqual(len(email), 8)
        self.assertIn("@", email)

    def test_ambiguous_suffixes_and_incompatible_types_are_not_inferred(self):
        self.assertIsNone(infer_field_semantic(column("material_id", "INTEGER")))
        self.assertIsNone(infer_field_semantic(column("price_status")))
        self.assertIsNone(infer_field_semantic(column("email_verified", "BOOLEAN")))
        self.assertIsNone(infer_field_semantic(column("contact_email", "INTEGER")))

    def test_enum_metadata_takes_priority_over_name_inference(self):
        status = column(
            "price_status",
            "ENUM",
            enum_values=["pending", "complete"],
        )

        self.assertEqual(generate_field_value(status, "token"), "pending")


if __name__ == "__main__":
    unittest.main()
