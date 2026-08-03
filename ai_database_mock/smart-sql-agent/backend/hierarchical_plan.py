import hashlib
import json
import math
import os
import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time as datetime_time
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence, Tuple

import networkx as nx
from sqlalchemy import MetaData, Table, text

try:
    from .field_semantics import generate_field_value, infer_field_semantic
except ImportError:  # pragma: no cover - direct script import fallback
    from field_semantics import generate_field_value, infer_field_semantic  # type: ignore


PLAN_KIND = "hierarchical_insert"
PLAN_VERSION = 1
ENTITY_ID_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
ALLOWED_TOP_LEVEL_FIELDS = {
    "kind",
    "version",
    "seed",
    "graph_fingerprint",
    "entities",
}
ALLOWED_ENTITY_FIELDS = {
    "id",
    "table",
    "parent",
    "relationship",
    "count",
    "count_per_parent",
    "count_mode",
    "values",
    "generators",
}
GENERATOR_STRATEGIES = {"sequence", "lookup", "snowflake", "prefixed_sequence"}
SEQUENCE_GENERATOR_FIELDS = {"strategy", "start", "step", "scope"}
LOOKUP_GENERATOR_FIELDS = {"strategy", "table", "column", "offset", "order_by", "assign"}
SNOWFLAKE_GENERATOR_FIELDS = {"strategy", "scope"}
PREFIXED_SEQUENCE_GENERATOR_FIELDS = {
    "strategy",
    "prefix",
    "start",
    "step",
    "pad",
    "scope",
}
SEQUENCE_NUMERIC_TYPES = {
    "tinyint",
    "smallint",
    "mediumint",
    "int",
    "integer",
    "bigint",
    "number",
    "numeric",
    "decimal",
    "dec",
    "real",
    "double",
    "float",
}
STRING_LIKE_TYPES = {
    "char",
    "varchar",
    "nvarchar",
    "nchar",
    "text",
    "tinytext",
    "mediumtext",
    "longtext",
    "string",
    "clob",
}


class DataPlanError(ValueError):
    pass


@dataclass(frozen=True)
class PlanRelationship:
    child_table: str
    parent_table: str
    pairs: Tuple[Tuple[str, str], ...]
    constraint_name: Optional[str] = None


@dataclass(frozen=True)
class PlanEntity:
    entity_id: str
    table: str
    count: int
    total_rows: int
    parent_id: Optional[str]
    count_mode: str
    values: Dict[str, Any]
    generators: Dict[str, Dict[str, Any]]
    relationship: Optional[PlanRelationship] = None


@dataclass(frozen=True)
class HierarchicalInsertPlan:
    entities: Tuple[PlanEntity, ...]
    graph_fingerprint: str
    seed: str

    @property
    def total_rows(self) -> int:
        return sum(entity.total_rows for entity in self.entities)


@dataclass(frozen=True)
class SQLReference:
    sql: str


def _positive_setting(name: str, default: int) -> int:
    raw_value = os.getenv(name, str(default)).strip()
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise DataPlanError(f"{name} 必须是正整数") from exc
    if value <= 0:
        raise DataPlanError(f"{name} 必须是正整数")
    return value


def graph_fingerprint(graph: nx.MultiDiGraph) -> str:
    nodes = [
        {"id": str(name), "attributes": attributes}
        for name, attributes in sorted(graph.nodes(data=True), key=lambda item: str(item[0]))
    ]
    edges = [
        {
            "source": str(source),
            "target": str(target),
            "key": str(key),
            "attributes": attributes,
        }
        for source, target, key, attributes in sorted(
            graph.edges(keys=True, data=True),
            key=lambda item: (str(item[0]), str(item[1]), str(item[2])),
        )
    ]
    payload = {"graph": dict(graph.graph), "nodes": nodes, "edges": edges}
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def is_hierarchical_plan_text(content: str) -> bool:
    try:
        payload = json.loads(content)
    except (TypeError, json.JSONDecodeError):
        return False
    return isinstance(payload, dict) and payload.get("kind") == PLAN_KIND


def _table_columns(graph: nx.MultiDiGraph, table_name: str) -> Dict[str, Dict[str, Any]]:
    return {
        str(column["name"]).lower(): column
        for column in graph.nodes[table_name].get("columns", [])
        if isinstance(column, dict) and column.get("name")
    }


def _column_is_generated(column: Dict[str, Any]) -> bool:
    return bool(
        column.get("generated")
        or column.get("computed") is not None
        or column.get("identity") is not None
        or column.get("autoincrement") is True
    )


def _explicit_relationships(
    graph: nx.MultiDiGraph,
    child_table: str,
) -> List[PlanRelationship]:
    grouped: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for _, parent_table, attributes in graph.out_edges(child_table, data=True):
        if attributes.get("type") != "explicit_fk":
            continue
        constrained = list(attributes.get("constrained_columns") or [])
        referred = list(attributes.get("referred_columns") or [])
        constraint_name = attributes.get("constraint_name")
        if constrained and len(constrained) == len(referred):
            pairs = list(zip(constrained, referred))
            group_id = str(constraint_name or pairs)
        else:
            source = str(attributes.get("src_col") or "")
            target = str(attributes.get("dst_col") or "")
            if not source or not target:
                continue
            pairs = [(source, target)]
            group_id = str(constraint_name or f"{source}->{target}")
        key = (str(parent_table), group_id)
        group = grouped.setdefault(
            key,
            {
                "parent_table": str(parent_table),
                "constraint_name": str(constraint_name) if constraint_name else None,
                "pairs": [],
            },
        )
        for pair in pairs:
            normalized_pair = (str(pair[0]), str(pair[1]))
            if normalized_pair not in group["pairs"]:
                group["pairs"].append(normalized_pair)
    return [
        PlanRelationship(
            child_table=child_table,
            parent_table=item["parent_table"],
            pairs=tuple(item["pairs"]),
            constraint_name=item["constraint_name"],
        )
        for item in grouped.values()
    ]


def _require_count(value: Any, field_name: str, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise DataPlanError(f"{field_name} 必须是正整数")
    if value > maximum:
        raise DataPlanError(f"{field_name} 不能超过 {maximum}")
    return value


def _validate_scalar(value: Any, field_name: str) -> None:
    if value is None or isinstance(value, (str, int, bool)):
        if isinstance(value, str) and len(value) > 2000:
            raise DataPlanError(f"{field_name} 的文本不能超过 2000 个字符")
        return
    if isinstance(value, float) and math.isfinite(value):
        return
    raise DataPlanError(f"{field_name} 只允许 JSON 标量值")


def _validate_json_value(
    value: Any,
    field_name: str,
    depth: int = 0,
    item_budget: int = 200,
) -> int:
    if depth > 8:
        raise DataPlanError(f"{field_name} 的 JSON 嵌套不能超过 8 层")
    if value is None or isinstance(value, (str, int, bool)):
        _validate_scalar(value, field_name)
        return item_budget - 1
    if isinstance(value, float):
        _validate_scalar(value, field_name)
        return item_budget - 1
    if isinstance(value, list):
        remaining = item_budget - 1
        for index, item in enumerate(value):
            if remaining <= 0:
                raise DataPlanError(f"{field_name} 的 JSON 内容过大")
            remaining = _validate_json_value(
                item,
                f"{field_name}[{index}]",
                depth + 1,
                remaining,
            )
        return remaining
    if isinstance(value, dict):
        remaining = item_budget - 1
        for key, item in value.items():
            if not isinstance(key, str) or len(key) > 200:
                raise DataPlanError(f"{field_name} 的 JSON 键格式无效")
            if remaining <= 0:
                raise DataPlanError(f"{field_name} 的 JSON 内容过大")
            remaining = _validate_json_value(
                item,
                f"{field_name}.{key}",
                depth + 1,
                remaining,
            )
        return remaining
    raise DataPlanError(f"{field_name} 必须是合法 JSON 值")


def _column_base_type(column: Dict[str, Any]) -> str:
    return re.split(
        r"[\s(]",
        str(column.get("type") or "").lower(),
        maxsplit=1,
    )[0]


def _parse_scope(raw_generator: Dict[str, Any], location: str, default: str = "parent") -> str:
    scope = raw_generator.get("scope", default)
    if scope not in {"parent", "entity"}:
        raise DataPlanError(f"{location}.scope 只能是 parent 或 entity")
    return scope


def _parse_int_field(
    raw_generator: Dict[str, Any],
    field_name: str,
    location: str,
    *,
    default: int,
    allow_zero: bool = True,
    minimum: Optional[int] = None,
) -> int:
    value = raw_generator.get(field_name, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise DataPlanError(f"{location}.{field_name} 必须是整数")
    if not allow_zero and value == 0:
        raise DataPlanError(f"{location}.{field_name} 必须是非零整数")
    if minimum is not None and value < minimum:
        raise DataPlanError(f"{location}.{field_name} 必须 >= {minimum}")
    return value


def _parse_sequence_generator(
    raw_generator: Dict[str, Any],
    column: Dict[str, Any],
    location: str,
    table_name: str,
) -> Dict[str, Any]:
    unknown_fields = set(raw_generator) - SEQUENCE_GENERATOR_FIELDS
    if unknown_fields:
        raise DataPlanError(
            f"{location} 包含不支持的字段: " + ", ".join(sorted(unknown_fields))
        )
    if _column_base_type(column) not in SEQUENCE_NUMERIC_TYPES:
        raise DataPlanError(
            f"sequence 生成器只支持数值字段: {table_name}.{column['name']}"
        )
    return {
        "strategy": "sequence",
        "start": _parse_int_field(raw_generator, "start", location, default=1),
        "step": _parse_int_field(
            raw_generator, "step", location, default=1, allow_zero=False
        ),
        "scope": _parse_scope(raw_generator, location),
    }


def _parse_lookup_generator(
    raw_generator: Dict[str, Any],
    graph: nx.MultiDiGraph,
    location: str,
) -> Dict[str, Any]:
    unknown_fields = set(raw_generator) - LOOKUP_GENERATOR_FIELDS
    if unknown_fields:
        raise DataPlanError(
            f"{location} 包含不支持的字段: " + ", ".join(sorted(unknown_fields))
        )
    raw_table = raw_generator.get("table")
    raw_column = raw_generator.get("column")
    if not isinstance(raw_table, str) or not raw_table.strip():
        raise DataPlanError(f"{location}.table 必须是真实表名")
    if not isinstance(raw_column, str) or not raw_column.strip():
        raise DataPlanError(f"{location}.column 必须是真实字段名")

    table_lookup = {str(name).lower(): str(name) for name in graph.nodes}
    table_name = table_lookup.get(raw_table.strip().lower())
    if table_name is None:
        raise DataPlanError(f"{location}.table 不是当前关系图中的表: {raw_table}")
    column_lookup = _table_columns(graph, table_name)
    column = column_lookup.get(raw_column.strip().lower())
    if column is None:
        raise DataPlanError(f"{table_name} 中不存在字段 {raw_column}")

    offset = _parse_int_field(
        raw_generator, "offset", location, default=1, minimum=1
    )
    assign = raw_generator.get("assign", "fixed")
    if assign not in {"fixed", "each"}:
        raise DataPlanError(f"{location}.assign 只能是 fixed 或 each")
    order_by_name = str(column["name"])
    raw_order_by = raw_generator.get("order_by")
    if raw_order_by is not None:
        if not isinstance(raw_order_by, str) or not raw_order_by.strip():
            raise DataPlanError(f"{location}.order_by 必须是真实字段名")
        order_column = column_lookup.get(raw_order_by.strip().lower())
        if order_column is None:
            raise DataPlanError(f"{table_name} 中不存在排序字段 {raw_order_by}")
        order_by_name = str(order_column["name"])

    return {
        "strategy": "lookup",
        "table": table_name,
        "column": str(column["name"]),
        "offset": offset,
        "order_by": order_by_name,
        "assign": assign,
    }


def _parse_snowflake_generator(
    raw_generator: Dict[str, Any],
    column: Dict[str, Any],
    location: str,
    table_name: str,
) -> Dict[str, Any]:
    unknown_fields = set(raw_generator) - SNOWFLAKE_GENERATOR_FIELDS
    if unknown_fields:
        raise DataPlanError(
            f"{location} 包含不支持的字段: " + ", ".join(sorted(unknown_fields))
        )
    if _column_base_type(column) not in SEQUENCE_NUMERIC_TYPES:
        raise DataPlanError(
            f"snowflake 生成器只支持数值字段: {table_name}.{column['name']}"
        )
    return {
        "strategy": "snowflake",
        "scope": _parse_scope(raw_generator, location, default="entity"),
    }


def _parse_prefixed_sequence_generator(
    raw_generator: Dict[str, Any],
    column: Dict[str, Any],
    location: str,
    table_name: str,
) -> Dict[str, Any]:
    unknown_fields = set(raw_generator) - PREFIXED_SEQUENCE_GENERATOR_FIELDS
    if unknown_fields:
        raise DataPlanError(
            f"{location} 包含不支持的字段: " + ", ".join(sorted(unknown_fields))
        )
    if _column_base_type(column) not in STRING_LIKE_TYPES:
        raise DataPlanError(
            f"prefixed_sequence 生成器只支持字符串字段: {table_name}.{column['name']}"
        )
    prefix = raw_generator.get("prefix")
    if not isinstance(prefix, str) or prefix == "":
        raise DataPlanError(f"{location}.prefix 必须是非空字符串")
    if len(prefix) > 200:
        raise DataPlanError(f"{location}.prefix 过长")
    return {
        "strategy": "prefixed_sequence",
        "prefix": prefix,
        "start": _parse_int_field(raw_generator, "start", location, default=1),
        "step": _parse_int_field(
            raw_generator, "step", location, default=1, allow_zero=False
        ),
        "pad": _parse_int_field(
            raw_generator, "pad", location, default=3, minimum=0
        ),
        "scope": _parse_scope(raw_generator, location, default="entity"),
    }


def _parse_generators(
    raw_generators: Any,
    column_lookup: Dict[str, Dict[str, Any]],
    values: Dict[str, Any],
    location: str,
    table_name: str,
    graph: nx.MultiDiGraph,
) -> Dict[str, Dict[str, Any]]:
    if not isinstance(raw_generators, dict):
        raise DataPlanError(f"{location}.generators 必须是 JSON 对象")
    generators: Dict[str, Dict[str, Any]] = {}
    for raw_column_name, raw_generator in raw_generators.items():
        if not isinstance(raw_column_name, str):
            raise DataPlanError(f"{location}.generators 的字段名必须是字符串")
        column = column_lookup.get(raw_column_name.lower())
        if column is None:
            raise DataPlanError(f"{table_name} 中不存在字段 {raw_column_name}")
        actual_name = str(column["name"])
        if actual_name in values:
            raise DataPlanError(
                f"{table_name}.{actual_name} 不能同时配置 values 和 generators"
            )
        if _column_is_generated(column):
            raise DataPlanError(
                f"数据计划不能为数据库生成字段配置生成器: {table_name}.{actual_name}"
            )
        if not isinstance(raw_generator, dict):
            raise DataPlanError(
                f"{location}.generators.{raw_column_name} 必须是 JSON 对象"
            )
        generator_location = f"{location}.generators.{raw_column_name}"
        strategy = raw_generator.get("strategy")
        if strategy not in GENERATOR_STRATEGIES:
            raise DataPlanError(
                f"{generator_location}.strategy 只能是 "
                + ", ".join(sorted(GENERATOR_STRATEGIES))
            )
        if strategy == "sequence":
            parsed = _parse_sequence_generator(
                raw_generator, column, generator_location, table_name
            )
        elif strategy == "lookup":
            parsed = _parse_lookup_generator(raw_generator, graph, generator_location)
        elif strategy == "snowflake":
            parsed = _parse_snowflake_generator(
                raw_generator, column, generator_location, table_name
            )
        else:
            parsed = _parse_prefixed_sequence_generator(
                raw_generator, column, generator_location, table_name
            )
        generators[actual_name] = parsed
    return generators


def _select_relationship(
    graph: nx.MultiDiGraph,
    child_table: str,
    parent_table: str,
    requested_name: Optional[str],
) -> PlanRelationship:
    candidates = [
        item
        for item in _explicit_relationships(graph, child_table)
        if item.parent_table == parent_table
    ]
    if requested_name:
        requested_lower = requested_name.strip().lower()
        named_candidates = [
            item
            for item in candidates
            if item.constraint_name and item.constraint_name.lower() == requested_lower
        ]
        if not named_candidates:
            named_candidates = [
                item
                for item in candidates
                if _relationship_expression_matches(requested_name, item)
            ]
        candidates = named_candidates
    if not candidates:
        suffix = f"（约束 {requested_name}）" if requested_name else ""
        raise DataPlanError(
            f"关系图中不存在 {child_table} -> {parent_table} 的显式外键{suffix}"
        )
    if len(candidates) > 1:
        names = [item.constraint_name or str(item.pairs) for item in candidates]
        raise DataPlanError(
            f"{child_table} 到 {parent_table} 有多个外键，请在 relationship 中指定: "
            + ", ".join(names)
        )
    return candidates[0]


def _relationship_expression_matches(
    requested_value: str,
    relationship: PlanRelationship,
) -> bool:
    cleaned = re.sub(r"[`\"\[\]]", "", requested_value.lower())
    references = re.findall(
        r"([\w$]+)\.([\w$]+)\s*(?:=|->)\s*([\w$]+)\.([\w$]+)",
        cleaned,
    )
    if len(references) != len(relationship.pairs):
        return False
    actual_pairs = {
        frozenset(((left_table, left_column), (right_table, right_column)))
        for left_table, left_column, right_table, right_column in references
    }
    expected_pairs = {
        frozenset(
            (
                (relationship.child_table.lower(), child_column.lower()),
                (relationship.parent_table.lower(), parent_column.lower()),
            )
        )
        for child_column, parent_column in relationship.pairs
    }
    return actual_pairs == expected_pairs


def parse_hierarchical_plan(
    content: str,
    graph: nx.MultiDiGraph,
    require_plan: bool = False,
) -> Optional[HierarchicalInsertPlan]:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        if require_plan:
            raise DataPlanError(f"层级数据计划不是合法 JSON: {exc}") from exc
        return None
    if not isinstance(payload, dict) or payload.get("kind") != PLAN_KIND:
        if require_plan:
            raise DataPlanError(f"模型必须返回 kind={PLAN_KIND} 的数据计划")
        return None
    unknown_top_level = set(payload) - ALLOWED_TOP_LEVEL_FIELDS
    if unknown_top_level:
        raise DataPlanError(
            "数据计划包含不支持的顶层字段: " + ", ".join(sorted(unknown_top_level))
        )
    if payload.get("version") != PLAN_VERSION:
        raise DataPlanError(f"数据计划 version 必须为 {PLAN_VERSION}")

    current_fingerprint = graph_fingerprint(graph)
    supplied_fingerprint = payload.get("graph_fingerprint")
    if supplied_fingerprint is not None and supplied_fingerprint != current_fingerprint:
        raise DataPlanError("表结构图已发生变化，请重新生成数据计划")
    supplied_seed = payload.get("seed")
    if supplied_seed is None:
        seed = uuid.uuid4().hex
    elif isinstance(supplied_seed, str) and re.fullmatch(r"[0-9a-fA-F]{32}", supplied_seed):
        seed = supplied_seed.lower()
    else:
        raise DataPlanError("数据计划 seed 必须是 32 位十六进制字符串")

    raw_entities = payload.get("entities")
    if not isinstance(raw_entities, list) or not raw_entities:
        raise DataPlanError("数据计划 entities 必须是非空数组")
    max_entities = _positive_setting("DATA_PLAN_MAX_ENTITIES", 20)
    if len(raw_entities) > max_entities:
        raise DataPlanError(f"数据计划实体数量不能超过 {max_entities}")
    max_per_parent = _positive_setting("DATA_PLAN_MAX_PER_PARENT", 1000)
    max_rows = _positive_setting("DATA_PLAN_MAX_ROWS", 2000)

    table_lookup = {str(table).lower(): str(table) for table in graph.nodes}
    normalized: List[Dict[str, Any]] = []
    entity_ids = set()
    for index, raw_entity in enumerate(raw_entities):
        location = f"entities[{index}]"
        if not isinstance(raw_entity, dict):
            raise DataPlanError(f"{location} 必须是 JSON 对象")
        unknown_fields = set(raw_entity) - ALLOWED_ENTITY_FIELDS
        if unknown_fields:
            raise DataPlanError(
                f"{location} 包含不支持的字段: " + ", ".join(sorted(unknown_fields))
            )
        entity_id = raw_entity.get("id")
        if not isinstance(entity_id, str) or not ENTITY_ID_PATTERN.fullmatch(entity_id):
            raise DataPlanError(f"{location}.id 必须是字母开头的标识符")
        if entity_id in entity_ids:
            raise DataPlanError(f"数据计划包含重复实体 id: {entity_id}")
        entity_ids.add(entity_id)

        raw_table = raw_entity.get("table")
        if not isinstance(raw_table, str):
            raise DataPlanError(f"{location}.table 不能为空")
        table_name = table_lookup.get(raw_table.lower())
        if table_name is None:
            raise DataPlanError(f"数据计划引用了图谱之外的表: {raw_table}")
        object_type = str(graph.nodes[table_name].get("object_type") or "table").lower()
        if "view" in object_type:
            raise DataPlanError(f"层级数据计划不能写入视图: {table_name}")

        parent_id = raw_entity.get("parent")
        if parent_id is not None and not isinstance(parent_id, str):
            raise DataPlanError(f"{location}.parent 必须是实体 id")
        if parent_id is None:
            if "count_per_parent" in raw_entity:
                raise DataPlanError(f"根实体 {entity_id} 应使用 count")
            count = _require_count(raw_entity.get("count"), f"{location}.count", max_per_parent)
        else:
            if "count" in raw_entity:
                raise DataPlanError(f"子实体 {entity_id} 应使用 count_per_parent")
            count = _require_count(
                raw_entity.get("count_per_parent"),
                f"{location}.count_per_parent",
                max_per_parent,
            )

        count_mode = raw_entity.get("count_mode", "exactly")
        if count_mode not in {"exactly", "at_least"}:
            raise DataPlanError(f"{location}.count_mode 只能是 exactly 或 at_least")
        relationship_name = raw_entity.get("relationship")
        if relationship_name is not None and not isinstance(relationship_name, str):
            raise DataPlanError(f"{location}.relationship 必须是外键约束名")
        raw_values = raw_entity.get("values", {})
        if not isinstance(raw_values, dict):
            raise DataPlanError(f"{location}.values 必须是 JSON 对象")
        if len(raw_values) > 100:
            raise DataPlanError(f"{location}.values 字段过多")
        column_lookup = _table_columns(graph, table_name)
        values = {}
        for raw_column_name, value in raw_values.items():
            if not isinstance(raw_column_name, str):
                raise DataPlanError(f"{location}.values 的字段名必须是字符串")
            column = column_lookup.get(raw_column_name.lower())
            if column is None:
                raise DataPlanError(f"{table_name} 中不存在字段 {raw_column_name}")
            actual_name = str(column["name"])
            if _column_is_generated(column):
                raise DataPlanError(f"数据计划不能为数据库生成字段赋值: {table_name}.{actual_name}")
            if "json" in str(column.get("type") or "").lower():
                _validate_json_value(value, f"{table_name}.{actual_name}")
            else:
                _validate_scalar(value, f"{table_name}.{actual_name}")
            if value is None and column.get("nullable") is False:
                raise DataPlanError(f"非空字段不能设置为 NULL: {table_name}.{actual_name}")
            values[actual_name] = value
        generators = _parse_generators(
            raw_entity.get("generators", {}),
            column_lookup,
            values,
            location,
            table_name,
            graph,
        )
        normalized.append(
            {
                "entity_id": entity_id,
                "table": table_name,
                "parent_id": parent_id,
                "count": count,
                "count_mode": count_mode,
                "relationship_name": relationship_name,
                "values": values,
                "generators": generators,
                "index": index,
            }
        )

    by_id = {item["entity_id"]: item for item in normalized}
    ordering = nx.DiGraph()
    ordering.add_nodes_from(by_id)
    for item in normalized:
        parent_id = item["parent_id"]
        if parent_id is None:
            continue
        if parent_id not in by_id:
            raise DataPlanError(f"实体 {item['entity_id']} 引用了不存在的 parent: {parent_id}")
        ordering.add_edge(parent_id, item["entity_id"])
    if not nx.is_directed_acyclic_graph(ordering):
        raise DataPlanError("层级数据计划不能包含循环父子关系")

    totals: Dict[str, int] = {}
    relationships: Dict[str, PlanRelationship] = {}
    pending = list(normalized)
    while pending:
        progressed = False
        for item in list(pending):
            parent_id = item["parent_id"]
            if parent_id is not None and parent_id not in totals:
                continue
            if parent_id is None:
                total_rows = item["count"]
            else:
                total_rows = totals[parent_id] * item["count"]
                parent_table = by_id[parent_id]["table"]
                relationship = _select_relationship(
                    graph,
                    item["table"],
                    parent_table,
                    item["relationship_name"],
                )
                relation_columns = {source.lower() for source, _ in relationship.pairs}
                conflicting_values = [
                    name for name in item["values"] if name.lower() in relation_columns
                ]
                conflicting_generators = [
                    name
                    for name in item["generators"]
                    if name.lower() in relation_columns
                ]
                if conflicting_values or conflicting_generators:
                    raise DataPlanError(
                        f"实体 {item['entity_id']} 的外键由 parent 自动回填，"
                        "values/generators 中不能包含: "
                        + ", ".join(conflicting_values + conflicting_generators)
                    )
                relationships[item["entity_id"]] = relationship
            totals[item["entity_id"]] = total_rows
            pending.remove(item)
            progressed = True
        if not progressed:
            raise DataPlanError("无法解析层级数据计划的父子顺序")

    if sum(totals.values()) > max_rows:
        raise DataPlanError(
            f"数据计划总行数 {sum(totals.values())} 超过 DATA_PLAN_MAX_ROWS={max_rows}"
        )

    entities = []
    for item in normalized:
        relationship = relationships.get(item["entity_id"])
        covered_relationship = relationship
        for foreign_key in _explicit_relationships(graph, item["table"]):
            if covered_relationship == foreign_key:
                continue
            columns = _table_columns(graph, item["table"])
            required = any(
                columns[source.lower()].get("nullable") is False
                for source, _ in foreign_key.pairs
                if source.lower() in columns
            )
            supplied = all(
                any(name.lower() == source.lower() for name in item["values"])
                or any(name.lower() == source.lower() for name in item["generators"])
                for source, _ in foreign_key.pairs
            )
            if required and not supplied:
                raise DataPlanError(
                    f"实体 {item['entity_id']} 缺少必填外键 {foreign_key.child_table} -> "
                    f"{foreign_key.parent_table}；请将该父表加入计划，"
                    "或在 values / generators.lookup 中提供外键值"
                )

        unique_constraints = graph.nodes[item["table"]].get("unique_constraints", [])
        if totals[item["entity_id"]] > 1:
            for constraint in unique_constraints:
                unique_columns = list(constraint.get("columns") or [])
                if len(unique_columns) != 1:
                    continue
                unique_name = str(unique_columns[0])
                if any(name.lower() == unique_name.lower() for name in item["values"]):
                    raise DataPlanError(
                        f"实体 {item['entity_id']} 会生成多行，唯一字段 {unique_name} "
                        "不能使用同一个固定值"
                    )

        entities.append(
            PlanEntity(
                entity_id=item["entity_id"],
                table=item["table"],
                count=item["count"],
                total_rows=totals[item["entity_id"]],
                parent_id=item["parent_id"],
                count_mode=item["count_mode"],
                values=item["values"],
                generators=item["generators"],
                relationship=relationship,
            )
        )
    return HierarchicalInsertPlan(tuple(entities), current_fingerprint, seed)


def canonical_hierarchical_plan(plan: HierarchicalInsertPlan) -> str:
    entities = []
    for entity in plan.entities:
        item: Dict[str, Any] = {
            "id": entity.entity_id,
            "table": entity.table,
            "count_mode": entity.count_mode,
            "values": entity.values,
        }
        if entity.generators:
            item["generators"] = entity.generators
        if entity.parent_id is None:
            item["count"] = entity.count
        else:
            item["parent"] = entity.parent_id
            item["count_per_parent"] = entity.count
            if entity.relationship and entity.relationship.constraint_name:
                item["relationship"] = entity.relationship.constraint_name
        entities.append(item)
    payload = {
        "kind": PLAN_KIND,
        "version": PLAN_VERSION,
        "seed": plan.seed,
        "graph_fingerprint": plan.graph_fingerprint,
        "entities": entities,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)


def validate_plan_values(
    plan: HierarchicalInsertPlan,
    graph: nx.MultiDiGraph,
) -> None:
    missing_by_entity = []
    invalid_by_entity = []
    for entity in plan.entities:
        column_lookup = _table_columns(graph, entity.table)
        supplied = {name.lower(): value for name, value in entity.values.items()}
        generated_by_plan = {name.lower() for name in entity.generators}
        foreign_columns = {
            source.lower()
            for relationship in _explicit_relationships(graph, entity.table)
            for source, _ in relationship.pairs
        }
        automatically_unique = _unique_columns(graph, entity.table)
        required = set()
        inferred = set()
        for name, column in column_lookup.items():
            if (
                _column_is_generated(column)
                or name in foreign_columns
                or name in automatically_unique
            ):
                continue
            if infer_field_semantic(column):
                inferred.add(name)
            if column.get("nullable") is False and column.get("default") is None:
                required.add(name)
        covered = set(supplied) | generated_by_plan | inferred
        missing = sorted(required - covered)
        if missing:
            missing_by_entity.append(
                f"{entity.entity_id}({entity.table}): {', '.join(missing)}"
            )
        invalid = []
        for name in sorted(required & set(supplied)):
            value = supplied[name]
            empty = (
                value is None
                or (isinstance(value, str) and not value.strip())
                or (isinstance(value, (dict, list)) and not value)
            )
            if empty:
                invalid.append(name)
        if invalid:
            invalid_by_entity.append(
                f"{entity.entity_id}({entity.table}): {', '.join(invalid)}"
            )
    if missing_by_entity:
        raise DataPlanError(
            "分层数据计划缺少无默认值的必填字段: "
            + "; ".join(missing_by_entity)
            + "。请在 values 填写具体值，或使用 generators.lookup/"
            "prefixed_sequence/snowflake/sequence 生成"
        )
    if invalid_by_entity:
        raise DataPlanError(
            "分层数据计划的必填字段不能使用 NULL 或空内容: "
            + "; ".join(invalid_by_entity)
        )


def preview_hierarchical_plan(
    plan: HierarchicalInsertPlan,
    graph: nx.MultiDiGraph,
) -> Dict[str, Any]:
    validate_plan_values(plan, graph)
    details = []
    for entity in plan.entities:
        foreign_columns = {
            source.lower()
            for relationship in _explicit_relationships(graph, entity.table)
            for source, _ in relationship.pairs
        }
        configured_columns = {
            name.lower() for name in entity.values
        } | {name.lower() for name in entity.generators}
        inferred_fields = []
        for column in graph.nodes[entity.table].get("columns", []):
            if not isinstance(column, dict) or not column.get("name"):
                continue
            name = str(column["name"])
            semantic = infer_field_semantic(column)
            if (
                semantic
                and name.lower() not in configured_columns
                and name.lower() not in foreign_columns
                and not _column_is_generated(column)
            ):
                inferred_fields.append({"column": name, "semantic": semantic})
        relation = None
        if entity.relationship:
            relation = {
                "parent": entity.parent_id,
                "foreign_key": entity.relationship.constraint_name,
                "columns": [
                    {"child": source, "parent": target}
                    for source, target in entity.relationship.pairs
                ],
            }
        details.append(
            {
                "id": entity.entity_id,
                "table": entity.table,
                "rows": entity.total_rows,
                "parent": entity.parent_id,
                "count_per_parent": entity.count if entity.parent_id else None,
                "count_mode": entity.count_mode,
                "relationship": relation,
                "inferred_fields": inferred_fields,
            }
        )
    return {
        "type": "data_plan_preview",
        "entity_count": len(plan.entities),
        "total_rows": plan.total_rows,
        "statements_count": plan.total_rows,
        "entities": details,
        "sql_preview": render_hierarchical_sql(plan, graph),
        "planned_artifact": canonical_hierarchical_plan(plan),
        "requires_confirmation": True,
    }


def _quote_identifier(identifier: str, dialect: str) -> str:
    if dialect in {"mysql", "mariadb"}:
        return "`" + identifier.replace("`", "``") + "`"
    if dialect in {"mssql", "sqlserver"}:
        return "[" + identifier.replace("]", "]]" ) + "]"
    return '"' + identifier.replace('"', '""') + '"'


def _qualified_table_sql(
    graph: nx.MultiDiGraph,
    table_name: str,
    dialect: str,
) -> str:
    quoted_table = _quote_identifier(table_name, dialect)
    schema = graph.graph.get("schema")
    if schema:
        return f"{_quote_identifier(str(schema), dialect)}.{quoted_table}"
    return quoted_table


def _sql_literal(value: Any, dialect: str) -> str:
    if isinstance(value, SQLReference):
        return value.sql
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if dialect in {"mysql", "mariadb", "mssql", "sqlserver"} and value else (
            "0" if dialect in {"mysql", "mariadb", "mssql", "sqlserver"} else str(value).upper()
        )
    if isinstance(value, (int, float, Decimal)):
        return str(value)
    if isinstance(value, (dict, list)):
        value = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    if isinstance(value, datetime):
        value = value.isoformat(sep=" ")
    elif isinstance(value, (date, datetime_time)):
        value = value.isoformat()
    if isinstance(value, bytes):
        return "X'" + value.hex() + "'"
    return "'" + str(value).replace("'", "''") + "'"


def render_hierarchical_sql(
    plan: HierarchicalInsertPlan,
    graph: nx.MultiDiGraph,
) -> str:
    dialect = str(graph.graph.get("dialect") or "").lower().split("+", 1)[0]
    mysql_compatible = dialect in {"mysql", "mariadb"}
    statements = [
        "-- 分层写入 SQL；父子主键由数据库生成后通过会话变量传递。",
        "START TRANSACTION;" if mysql_compatible else "BEGIN;",
    ]
    by_id = {entity.entity_id: entity for entity in plan.entities}
    children: Dict[str, List[PlanEntity]] = {entity.entity_id: [] for entity in plan.entities}
    roots = []
    for entity in plan.entities:
        if entity.parent_id is None:
            roots.append(entity)
        else:
            children[entity.parent_id].append(entity)
    emitted_counts = {entity.entity_id: 0 for entity in plan.entities}

    def emit_instances(
        entity: PlanEntity,
        parent_values: Optional[Dict[str, Any]],
        count: int,
    ) -> None:
        for sibling_offset in range(count):
            entity_ordinal = emitted_counts[entity.entity_id] + 1
            values = _row_values(
                graph,
                entity,
                parent_values,
                entity_ordinal,
                sibling_offset + 1,
                plan.seed,
                dialect=dialect,
            )
            column_order = [
                str(column["name"])
                for column in graph.nodes[entity.table].get("columns", [])
                if isinstance(column, dict) and column.get("name") in values
            ]
            columns_sql = ", ".join(
                _quote_identifier(name, dialect) for name in column_order
            )
            values_sql = ", ".join(
                _sql_literal(values[name], dialect) for name in column_order
            )
            statements.append(
                f"INSERT INTO {_qualified_table_sql(graph, entity.table, dialect)} "
                f"({columns_sql}) VALUES ({values_sql});"
            )

            emitted_counts[entity.entity_id] += 1
            inserted_values = dict(values)
            primary_keys = list(graph.nodes[entity.table].get("primary_keys") or [])
            column_lookup = _table_columns(graph, entity.table)
            for primary_key in primary_keys:
                actual_name = str(column_lookup[str(primary_key).lower()]["name"])
                if actual_name in inserted_values:
                    continue
                variable_name = (
                    f"plan_{entity.entity_id}_{entity_ordinal}_{actual_name}"
                )
                if mysql_compatible and len(primary_keys) == 1:
                    reference = SQLReference(f"@{variable_name}")
                    statements.append(
                        f"SET {reference.sql} = LAST_INSERT_ID();"
                    )
                else:
                    reference = SQLReference(f":{variable_name}")
                    statements.append(
                        f"-- {reference.sql} 由应用读取刚插入的 {entity.table}.{actual_name} 后回填"
                    )
                inserted_values[actual_name] = reference

            for child in children[entity.entity_id]:
                emit_instances(child, inserted_values, child.count)

    for root in roots:
        emit_instances(root, None, root.count)
    statements.append("COMMIT;")
    return "\n".join(statements)


def _synthesized_value(
    column: Dict[str, Any],
    entity_id: str,
    ordinal: int,
    seed: str,
    sequence_index: int,
) -> Any:
    try:
        return generate_field_value(
            column,
            token=f"{seed}:{entity_id}:{ordinal}",
            sequence_index=sequence_index,
            value_prefix="plan",
        )
    except ValueError as exc:
        raise DataPlanError(str(exc)) from exc


def _unique_columns(graph: nx.MultiDiGraph, table_name: str) -> set:
    columns = set()
    primary_keys = list(graph.nodes[table_name].get("primary_keys") or [])
    if len(primary_keys) == 1:
        columns.add(str(primary_keys[0]).lower())
    for constraint in graph.nodes[table_name].get("unique_constraints", []):
        for name in constraint.get("columns") or []:
            columns.add(str(name).lower())
    return columns


def _sequence_index(generator: Dict[str, Any], ordinal: int, sibling_index: int) -> int:
    scope = generator.get("scope", "entity")
    return sibling_index if scope == "parent" else ordinal


def _snowflake_id(seed: str, ordinal: int) -> int:
    """Deterministic snowflake-like 64-bit id for reproducible test data."""
    digest = hashlib.sha256(f"{seed}:snowflake".encode("utf-8")).digest()
    worker_id = int.from_bytes(digest[:2], "big") & 0x3FF
    timestamp_ms = int.from_bytes(digest[2:7], "big") & ((1 << 41) - 1)
    sequence = (ordinal - 1) & 0xFFF
    return (timestamp_ms << 22) | (worker_id << 12) | sequence


def _prefixed_sequence_value(generator: Dict[str, Any], sequence_index: int) -> str:
    number = generator["start"] + (sequence_index - 1) * generator["step"]
    if number < 0:
        raise DataPlanError("prefixed_sequence 生成了负数序号")
    pad = generator["pad"]
    suffix = str(number).zfill(pad) if pad > 0 else str(number)
    return f"{generator['prefix']}{suffix}"


def _lookup_sql(
    generator: Dict[str, Any],
    graph: nx.MultiDiGraph,
    dialect: str,
) -> str:
    table_sql = _qualified_table_sql(graph, generator["table"], dialect)
    column_sql = _quote_identifier(generator["column"], dialect)
    order_sql = _quote_identifier(generator["order_by"], dialect)
    offset = generator["offset"] - 1
    if dialect in {"mssql", "sqlserver"}:
        return (
            f"(SELECT {column_sql} FROM {table_sql} "
            f"ORDER BY {order_sql} "
            f"OFFSET {offset} ROWS FETCH NEXT 1 ROWS ONLY)"
        )
    return (
        f"(SELECT {column_sql} FROM {table_sql} "
        f"ORDER BY {order_sql} LIMIT 1 OFFSET {offset})"
    )


def _lookup_cache_key(generator: Dict[str, Any]) -> Tuple[str, str, str, int]:
    return (
        generator["table"],
        generator["column"],
        generator["order_by"],
        generator["offset"],
    )


def _row_values(
    graph: nx.MultiDiGraph,
    entity: PlanEntity,
    parent_values: Optional[Dict[str, Any]],
    ordinal: int,
    sibling_index: int,
    seed: str,
    *,
    dialect: Optional[str] = None,
    lookup_resolver=None,
) -> Dict[str, Any]:
    values = dict(entity.values)
    if entity.relationship:
        if parent_values is None:
            raise DataPlanError(f"实体 {entity.entity_id} 缺少父记录上下文")
        parent_lookup = {str(name).lower(): value for name, value in parent_values.items()}
        for child_column, parent_column in entity.relationship.pairs:
            if parent_column.lower() not in parent_lookup:
                raise DataPlanError(
                    f"数据库未返回父字段 {entity.relationship.parent_table}.{parent_column}，"
                    "无法回填子表外键"
                )
            values[child_column] = parent_lookup[parent_column.lower()]

    resolved_dialect = (
        dialect
        or str(graph.graph.get("dialect") or "").lower().split("+", 1)[0]
        or "sqlite"
    )
    for name, generator in entity.generators.items():
        strategy = generator["strategy"]
        if strategy == "sequence":
            sequence_index = _sequence_index(generator, ordinal, sibling_index)
            values[name] = generator["start"] + (sequence_index - 1) * generator["step"]
            continue
        if strategy == "prefixed_sequence":
            sequence_index = _sequence_index(generator, ordinal, sibling_index)
            values[name] = _prefixed_sequence_value(generator, sequence_index)
            continue
        if strategy == "snowflake":
            sequence_index = _sequence_index(generator, ordinal, sibling_index)
            values[name] = _snowflake_id(seed, sequence_index)
            continue
        if strategy == "lookup":
            effective = dict(generator)
            if generator.get("assign") == "each":
                sequence_index = _sequence_index(
                    {"scope": "entity"},
                    ordinal,
                    sibling_index,
                )
                effective["offset"] = generator["offset"] + sequence_index - 1
            if lookup_resolver is not None:
                values[name] = lookup_resolver(effective)
            else:
                values[name] = SQLReference(
                    _lookup_sql(effective, graph, resolved_dialect)
                )
            continue
        raise DataPlanError(f"不支持的生成器策略: {strategy}")

    unique_columns = _unique_columns(graph, entity.table)
    for column in graph.nodes[entity.table].get("columns", []):
        if not isinstance(column, dict) or not column.get("name"):
            continue
        name = str(column["name"])
        if name in values or _column_is_generated(column):
            continue
        required = (
            column.get("nullable") is False
            and column.get("default") is None
        )
        semantic = infer_field_semantic(column)
        if required or name.lower() in unique_columns or semantic:
            values[name] = _synthesized_value(
                column,
                entity.entity_id,
                ordinal,
                seed,
                sibling_index,
            )
    return values


def _inserted_values(table: Table, result, supplied_values: Dict[str, Any]) -> Dict[str, Any]:
    values = dict(supplied_values)
    primary_key_columns = list(table.primary_key.columns)
    try:
        primary_key_row = result.inserted_primary_key
        inserted_primary_key = list(primary_key_row) if primary_key_row is not None else []
    except Exception:
        inserted_primary_key = []
    for column, value in zip(primary_key_columns, inserted_primary_key):
        if value is not None:
            values[column.name] = value
    if len(primary_key_columns) == 1 and primary_key_columns[0].name not in values:
        lastrowid = getattr(result, "lastrowid", None)
        if lastrowid is not None:
            values[primary_key_columns[0].name] = lastrowid
    returned_defaults = getattr(result, "returned_defaults", None)
    if returned_defaults is not None:
        try:
            for key, value in returned_defaults._mapping.items():
                values[getattr(key, "name", str(key))] = value
        except (AttributeError, TypeError, ValueError):
            pass
    return values


def execute_hierarchical_plan(
    plan: HierarchicalInsertPlan,
    graph: nx.MultiDiGraph,
    engine_factory,
) -> Dict[str, Any]:
    validate_plan_values(plan, graph)
    engine = engine_factory()
    connection = None
    transaction = None
    try:
        connection = engine.connect()
        transaction = connection.begin()
        metadata = MetaData()
        schema = graph.graph.get("schema") or None
        tables: Dict[str, Table] = {}
        for entity in plan.entities:
            if entity.table not in tables:
                tables[entity.table] = Table(
                    entity.table,
                    metadata,
                    schema=schema,
                    autoload_with=connection,
                )

        reflected_columns = {
            table_name: {column.name.lower(): column.name for column in table.columns}
            for table_name, table in tables.items()
        }
        for entity in plan.entities:
            graph_column_names = set(_table_columns(graph, entity.table))
            database_column_names = set(reflected_columns[entity.table])
            if graph_column_names != database_column_names:
                raise DataPlanError(
                    f"数据库表 {entity.table} 与当前关系图字段不一致，请重新运行 build_table_graph.py"
                )
            for column_name in entity.values:
                if column_name.lower() not in reflected_columns[entity.table]:
                    raise DataPlanError(
                        f"数据库当前结构中不存在字段 {entity.table}.{column_name}，请重新建图"
                    )
            if entity.relationship:
                for source, _ in entity.relationship.pairs:
                    if source.lower() not in reflected_columns[entity.table]:
                        raise DataPlanError(
                            f"数据库当前结构中不存在外键字段 {entity.table}.{source}，请重新建图"
                        )

        by_id = {entity.entity_id: entity for entity in plan.entities}
        children: Dict[str, List[PlanEntity]] = {entity.entity_id: [] for entity in plan.entities}
        roots = []
        for entity in plan.entities:
            if entity.parent_id is None:
                roots.append(entity)
            else:
                children[entity.parent_id].append(entity)

        inserted_counts = {entity.entity_id: 0 for entity in plan.entities}
        ordinal = 0
        lookup_cache: Dict[Tuple[str, str, str, int], Any] = {}
        dialect = str(graph.graph.get("dialect") or "").lower().split("+", 1)[0]

        def resolve_lookup(generator: Dict[str, Any]) -> Any:
            cache_key = _lookup_cache_key(generator)
            if cache_key in lookup_cache:
                return lookup_cache[cache_key]
            sql = _lookup_sql(generator, graph, dialect or "sqlite")
            # _lookup_sql wraps a scalar subquery in parentheses; unwrap for execution.
            query = sql[1:-1] if sql.startswith("(") and sql.endswith(")") else sql
            value = connection.execute(text(query)).scalar()
            if value is None:
                raise DataPlanError(
                    f"lookup 未找到数据: {generator['table']}.{generator['column']} "
                    f"第 {generator['offset']} 条（按 {generator['order_by']} 排序）"
                )
            lookup_cache[cache_key] = value
            return value

        def insert_instances(
            entity: PlanEntity,
            parent_values: Optional[Dict[str, Any]],
            count: int,
        ) -> None:
            nonlocal ordinal
            table = tables[entity.table]
            actual_names = reflected_columns[entity.table]
            for sibling_offset in range(count):
                ordinal += 1
                entity_ordinal = inserted_counts[entity.entity_id] + 1
                values = _row_values(
                    graph,
                    entity,
                    parent_values,
                    entity_ordinal,
                    sibling_offset + 1,
                    plan.seed,
                    dialect=dialect,
                    lookup_resolver=resolve_lookup,
                )
                database_values = {
                    actual_names[name.lower()]: value
                    for name, value in values.items()
                    if name.lower() in actual_names
                }
                statement = table.insert().values(database_values)
                result = connection.execute(statement)
                inserted = _inserted_values(table, result, database_values)
                inserted_counts[entity.entity_id] += 1
                for child in children[entity.entity_id]:
                    insert_instances(child, inserted, child.count)

        for root in roots:
            insert_instances(root, None, root.count)

        for entity_id, entity in by_id.items():
            if inserted_counts[entity_id] != entity.total_rows:
                raise DataPlanError(
                    f"实体 {entity_id} 预计插入 {entity.total_rows} 行，"
                    f"实际完成 {inserted_counts[entity_id]} 行"
                )
        transaction.commit()
        return {
            "type": "data_plan_execution",
            "entity_count": len(plan.entities),
            "total_rows": sum(inserted_counts.values()),
            "statements_count": sum(inserted_counts.values()),
            "entities": [
                {
                    "id": entity.entity_id,
                    "table": entity.table,
                    "rows_inserted": inserted_counts[entity.entity_id],
                }
                for entity in plan.entities
            ],
        }
    except Exception:
        if transaction is not None and transaction.is_active:
            transaction.rollback()
        raise
    finally:
        if connection is not None:
            connection.close()
        engine.dispose()
