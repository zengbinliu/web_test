import hashlib
import re
import uuid
from datetime import date, datetime, time as datetime_time
from decimal import Decimal
from typing import Any, Dict, List, Optional


TEXT_TYPES = {"char", "varchar", "nvarchar", "nchar", "text", "tinytext", "mediumtext", "longtext", "clob", "nclob", "xml", "string"}
INTEGER_TYPES = {
    "tinyint",
    "smallint",
    "mediumint",
    "int",
    "integer",
    "bigint",
    "serial",
    "bigserial",
    "smallserial",
    "year",
}
DECIMAL_TYPES = {"number", "numeric", "decimal", "dec", "money", "smallmoney"}
FLOAT_TYPES = {"real", "double", "float", "binary_float", "binary_double"}
JSON_TYPES = {"json", "jsonb"}


def identifier_tokens(name: Any) -> List[str]:
    raw = str(name or "")
    raw = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", raw)
    return [item for item in re.split(r"[^A-Za-z0-9]+", raw.lower()) if item]


def column_base_type(column: Dict[str, Any]) -> str:
    return re.split(
        r"[\s(]",
        str(column.get("type") or "").lower(),
        maxsplit=1,
    )[0]


def column_length(column: Dict[str, Any]) -> Optional[int]:
    configured = column.get("length")
    if isinstance(configured, int) and configured > 0:
        return configured
    match = re.search(r"\((\d+)\)", str(column.get("type") or ""))
    return int(match.group(1)) if match else None


def _compatible_semantic(
    column: Dict[str, Any],
    semantic: str,
) -> Optional[str]:
    if column.get("enum_values"):
        return semantic
    base_type = column_base_type(column)
    is_text = base_type in TEXT_TYPES or any(
        marker in base_type for marker in ("char", "text", "clob", "string")
    )
    is_numeric = base_type in INTEGER_TYPES | DECIMAL_TYPES | FLOAT_TYPES
    is_json = base_type in JSON_TYPES
    compatible = {
        "sequence": is_numeric or is_text,
        "email": is_text,
        "password_hash": is_text,
        "password": is_text,
        "salt": is_text,
        "phone": is_text,
        "url": is_text,
        "ip_address": is_text,
        "money": is_numeric or is_text,
        "quantity": is_numeric or is_text,
        "material": is_json or is_text,
        "snapshot": is_json or is_numeric or is_text,
        "code": is_text,
        "name": is_text,
    }
    return semantic if compatible.get(semantic, False) else None


def infer_field_semantic(column: Dict[str, Any]) -> Optional[str]:
    raw_name = str(column.get("name") or "")
    tokens = identifier_tokens(raw_name)
    token_set = set(tokens)
    compact = "".join(tokens)
    unicode_compact = re.sub(
        r"[\W_]+",
        "",
        raw_name.lower(),
        flags=re.UNICODE,
    )
    blocked_suffixes = {
        "id",
        "key",
        "status",
        "state",
        "type",
        "kind",
        "flag",
        "enabled",
        "verified",
        "currency",
        "unit",
        "format",
    }
    if (
        len(tokens) > 1
        and tokens[-1] in blocked_suffixes
    ) or any(
        unicode_compact.endswith(suffix)
        for suffix in ("状态", "类型", "标志", "是否启用", "是否验证", "币种", "单位", "格式")
    ):
        return None

    sequence_names = {
        "lineno",
        "linenumber",
        "lineindex",
        "sequenceno",
        "sequencenumber",
        "sequenceindex",
        "seq",
        "seqno",
        "sortorder",
        "sortindex",
        "position",
        "positionno",
        "positionindex",
        "ordinal",
        "rowno",
        "rownumber",
    }
    if compact in sequence_names or any(
        keyword in unicode_compact
        for keyword in ("行号", "行序号", "序号", "顺序号", "排序号", "位置号")
    ):
        return _compatible_semantic(column, "sequence")
    if token_set & {"email", "emailaddress", "mail", "mailaddress"} or compact in {
        "email",
        "emailaddress",
        "mail",
        "mailaddress",
    } or any(
        keyword in unicode_compact
        for keyword in ("邮箱", "电子邮件", "邮件地址")
    ):
        return _compatible_semantic(column, "email")
    if (
        "salt" in token_set
        or compact.endswith("salt")
        or any(keyword in unicode_compact for keyword in ("密码盐", "盐值"))
    ):
        return _compatible_semantic(column, "salt")
    if token_set & {"password", "passwd", "pwd"} or any(
        keyword in unicode_compact for keyword in ("密码", "口令")
    ):
        if (
            token_set & {"hash", "hashed", "digest"}
            or compact.endswith("hash")
            or any(keyword in unicode_compact for keyword in ("哈希", "摘要"))
        ):
            return _compatible_semantic(column, "password_hash")
        return _compatible_semantic(column, "password")
    if token_set & {"phone", "mobile", "telephone", "tel"} or any(
        keyword in unicode_compact for keyword in ("手机号", "手机号码", "联系电话", "电话")
    ):
        return _compatible_semantic(column, "phone")
    if token_set & {"url", "uri", "website", "homepage"} or any(
        keyword in unicode_compact for keyword in ("网址", "链接地址")
    ):
        return _compatible_semantic(column, "url")
    if (
        token_set & {"ip", "ipaddress"}
        or compact == "ipaddress"
        or "ip地址" in unicode_compact
    ):
        return _compatible_semantic(column, "ip_address")
    if token_set & {
        "amount",
        "price",
        "cost",
        "fee",
        "balance",
        "revenue",
        "salary",
        "tax",
    } or any(
        keyword in unicode_compact
        for keyword in ("金额", "价格", "单价", "成本", "费用", "余额", "税额", "薪资", "收入")
    ):
        return _compatible_semantic(column, "money")
    if token_set & {"quantity", "qty", "count"} or any(
        keyword in unicode_compact for keyword in ("数量", "个数")
    ):
        return _compatible_semantic(column, "quantity")
    if token_set & {"material", "materials", "ingredient", "ingredients"} or any(
        keyword in unicode_compact for keyword in ("材料", "物料", "原料", "配料", "成分")
    ):
        return _compatible_semantic(column, "material")
    if (
        "snapshot" in token_set
        or compact.startswith("snapshot")
        or "快照" in unicode_compact
    ):
        return _compatible_semantic(column, "snapshot")
    if token_set & {"code", "reference", "ref", "number"} or any(
        keyword in unicode_compact for keyword in ("编码", "代码", "编号")
    ):
        return _compatible_semantic(column, "code")
    if token_set & {"name", "title", "label"} or any(
        keyword in unicode_compact for keyword in ("名称", "姓名", "标题", "标签")
    ):
        return _compatible_semantic(column, "name")
    return None


def _fit_text(value: str, maximum_length: Optional[int]) -> str:
    if maximum_length is None:
        return value
    return value[:maximum_length]


def _email_value(token: str, maximum_length: Optional[int]) -> str:
    local = "test_" + token[:12]
    if maximum_length is None:
        return local + "@example.test"
    for domain in ("@example.test", "@x.test", "@x.co", "@b"):
        available = maximum_length - len(domain)
        if available > 0:
            return local[:available] + domain
    raise ValueError("邮箱字段长度不足，至少需要 3 个字符")


def _positive_decimal(
    column: Dict[str, Any],
    number: int,
    default_scale: int = 2,
) -> Decimal:
    precision = column.get("precision")
    scale = column.get("scale")
    precision = precision if isinstance(precision, int) and precision > 0 else 10
    scale = scale if isinstance(scale, int) and scale >= 0 else default_scale
    if scale >= precision:
        scale = max(precision - 1, 0)
    integer_digits = max(precision - scale, 1)
    integer_limit = min((10**integer_digits) - 1, 1000000)
    integer_part = 1 + number % max(integer_limit, 1)
    if scale:
        fractional = number % (10**scale)
        return Decimal(f"{integer_part}.{fractional:0{scale}d}")
    return Decimal(integer_part)


def _positive_numeric_value(
    column: Dict[str, Any],
    base_type: str,
    number: int,
) -> Any:
    if base_type == "tinyint":
        return number % 100 + 1
    if base_type == "smallint":
        return number % 30000 + 1
    if base_type in INTEGER_TYPES:
        return number % 800000000 + 1
    if base_type in FLOAT_TYPES:
        return float(f"{number % 100000}.{number % 1000:03d}")
    return _positive_decimal(column, number)


def generate_field_value(
    column: Dict[str, Any],
    token: str,
    sequence_index: int = 1,
    value_prefix: str = "test",
) -> Any:
    name = str(column.get("name") or "")
    base_type = column_base_type(column)
    type_name = str(column.get("type") or "").lower()
    maximum_length = column_length(column)
    digest = hashlib.sha256(f"{token}:{name}".encode("utf-8")).hexdigest()
    number = int(digest[:8], 16)
    semantic = infer_field_semantic(column)
    enum_values = list(column.get("enum_values") or [])

    if enum_values:
        return enum_values[0]
    if "enum" in type_name or type_name.startswith("set"):
        raise ValueError(
            f"无法安全生成枚举字段 {name}，请重新生成包含枚举值的图谱"
        )

    is_text = base_type in TEXT_TYPES or any(
        marker in base_type for marker in ("char", "text", "clob", "string")
    )
    is_numeric = base_type in INTEGER_TYPES | DECIMAL_TYPES | FLOAT_TYPES
    is_json = base_type in JSON_TYPES

    if semantic == "sequence":
        if is_numeric:
            return sequence_index
        if is_text:
            return _fit_text(str(sequence_index), maximum_length)
    if semantic == "email" and is_text:
        return _email_value(digest, maximum_length)
    if semantic == "password_hash" and is_text:
        return _fit_text(digest, maximum_length)
    if semantic == "password" and is_text:
        return _fit_text(f"Test!{digest[:16]}", maximum_length)
    if semantic == "salt" and is_text:
        return _fit_text(f"salt_{digest[:16]}", maximum_length)
    if semantic == "phone" and is_text:
        digits = str(number).zfill(10)[-10:]
        return _fit_text(f"+1{digits}", maximum_length)
    if semantic == "url" and is_text:
        return _fit_text(f"https://example.test/{digest[:12]}", maximum_length)
    if semantic == "ip_address" and is_text:
        return _fit_text(f"192.0.2.{number % 253 + 1}", maximum_length)
    if semantic == "money":
        value = _positive_numeric_value(column, base_type, number)
        if is_numeric:
            return value
        if is_text:
            return _fit_text(str(value), maximum_length)
    if semantic == "quantity":
        value = number % 9 + 1
        if is_numeric:
            return value
        if is_text:
            return _fit_text(str(value), maximum_length)
    if semantic == "material":
        if is_json:
            return [{"name": f"sample_{digest[:8]}", "value": "test"}]
        if is_text:
            return _fit_text(f"sample_material_{digest[:8]}", maximum_length)
    if semantic == "snapshot":
        if is_json:
            return {"value": f"snapshot_{digest[:12]}"}
        if is_numeric:
            return _positive_numeric_value(column, base_type, number)
        if is_text:
            return _fit_text(f"snapshot_{digest[:12]}", maximum_length)
    if semantic == "code" and is_text:
        return _fit_text(f"TST-{digest[:12]}", maximum_length)
    if semantic == "name" and is_text:
        return _fit_text(f"test_{digest[:12]}", maximum_length)

    if base_type in {"uuid", "uniqueidentifier"}:
        return str(uuid.UUID(digest[:32]))
    if is_json:
        return {"value": f"{value_prefix}_{digest[:12]}"}
    if base_type in {"bool", "boolean", "bit"}:
        return True
    if base_type in DECIMAL_TYPES:
        return _positive_decimal(column, number, default_scale=0)
    if base_type == "tinyint":
        return _positive_numeric_value(column, base_type, number)
    if base_type == "smallint":
        return _positive_numeric_value(column, base_type, number)
    if base_type in INTEGER_TYPES:
        return _positive_numeric_value(column, base_type, number)
    if base_type in FLOAT_TYPES:
        return _positive_numeric_value(column, base_type, number)
    if base_type in {"timestamp", "datetime", "datetime2", "smalldatetime"}:
        return datetime.now().replace(microsecond=0)
    if base_type == "date":
        return date.today()
    if base_type in {"time", "timetz"}:
        current = datetime.now()
        return datetime_time(current.hour, current.minute, current.second)
    if is_text:
        prefix = re.sub(r"[^a-z0-9]", "_", name.lower())[:20] or "value"
        value = f"{value_prefix}_{prefix}_{digest[:16]}"
        fitted = _fit_text(value, maximum_length)
        if fitted:
            return fitted
        raise ValueError(f"无法为字段 {name} 生成非空文本")
    raise ValueError(f"无法安全生成字段 {name}（类型 {column.get('type')}）")
