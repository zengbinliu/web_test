#!/usr/bin/env python3
"""Inspect a relational database and export a reusable table relationship graph."""

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import networkx as nx
from pyvis.network import Network
from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError

from database_config import (
    DEMO_ROOT,
    create_database_engine,
    get_backend_name,
    get_configured_schema,
    get_database_url,
    get_dialect_label,
    get_sqlglot_dialect,
)


GRAPH_VERSION = 3
INTEGER_TYPES = {"tinyint", "smallint", "mediumint", "int", "integer", "bigint"}


def table_name_candidates(base_name: str) -> list[str]:
    candidates = [base_name]
    if base_name.endswith("ies") and len(base_name) > 3:
        candidates.append(base_name[:-3] + "y")
    elif base_name.endswith("s") and not base_name.endswith("ss"):
        candidates.append(base_name[:-1])
    else:
        candidates.append(base_name + "s")
        if base_name.endswith("y") and len(base_name) > 1:
            candidates.append(base_name[:-1] + "ies")
    return list(dict.fromkeys(candidates))


def normalized_type(type_name: str) -> str:
    return type_name.lower().split("(", 1)[0].strip().split()[0]


def columns_are_compatible(source: dict[str, Any], target: dict[str, Any]) -> bool:
    source_type = normalized_type(source["type"])
    target_type = normalized_type(target["type"])
    if source_type == target_type:
        return True
    return source_type in INTEGER_TYPES and target_type in INTEGER_TYPES


def load_relation_hints() -> dict[str, str]:
    raw_hints = os.getenv("RELATION_HINTS_JSON", "").strip()
    if not raw_hints:
        return {}
    try:
        hints = json.loads(raw_hints)
    except json.JSONDecodeError as exc:
        raise ValueError(f"RELATION_HINTS_JSON 不是合法 JSON: {exc}") from exc
    if not isinstance(hints, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in hints.items()
    ):
        raise ValueError("RELATION_HINTS_JSON 必须是 table.column 到 table.column 的对象")
    return hints


def parse_qualified_column(value: str) -> tuple[str, str]:
    if "." not in value:
        raise ValueError(f"'{value}' 应使用 table.column 格式")
    table, column = value.rsplit(".", 1)
    if not table or not column:
        raise ValueError(f"'{value}' 应使用 table.column 格式")
    return table, column


def json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(item) for item in value]
    return str(value)


def get_table_comment(
    inspector,
    table_name: str,
    schema: Optional[str],
) -> Optional[str]:
    try:
        comment = inspector.get_table_comment(table_name, schema=schema).get("text")
        return str(comment) if comment else None
    except (NotImplementedError, SQLAlchemyError):
        return None


def build_table_relationship_graph(
    engine=None,
    schema: Optional[str] = None,
    include_views: bool = False,
) -> nx.MultiDiGraph:
    owns_engine = engine is None
    engine = engine or create_database_engine()
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))

        inspector = inspect(engine)
        selected_schema = schema if schema is not None else get_configured_schema()
        if selected_schema is None:
            selected_schema = inspector.default_schema_name

        table_names = list(inspector.get_table_names(schema=selected_schema))
        view_names = list(inspector.get_view_names(schema=selected_schema)) if include_views else []
        object_names = list(dict.fromkeys([*table_names, *view_names]))
        if not object_names:
            raise RuntimeError(f"schema {selected_schema or '(default)'} 中没有可读取的表")

        backend_name = engine.url.get_backend_name()
        graph = nx.MultiDiGraph(
            graph_version=GRAPH_VERSION,
            generated_at=datetime.now(timezone.utc).isoformat(),
            dialect=backend_name,
            sqlglot_dialect=get_sqlglot_dialect(backend_name),
            dialect_label=get_dialect_label(backend_name),
            database=engine.url.database,
            schema=selected_schema,
        )

        column_metadata: dict[tuple[str, str], dict[str, Any]] = {}
        primary_keys: dict[str, list[str]] = {}
        for table_name in object_names:
            raw_columns = inspector.get_columns(table_name, schema=selected_schema)
            primary_key = inspector.get_pk_constraint(table_name, schema=selected_schema)
            pk_columns = list(primary_key.get("constrained_columns") or [])
            primary_keys[table_name] = pk_columns

            unique_constraints = []
            check_constraints = []
            if table_name not in view_names:
                try:
                    unique_constraints = [
                        {
                            "name": item.get("name"),
                            "columns": list(item.get("column_names") or []),
                        }
                        for item in inspector.get_unique_constraints(
                            table_name,
                            schema=selected_schema,
                        )
                        if item.get("column_names")
                    ]
                except (NotImplementedError, SQLAlchemyError):
                    unique_constraints = []
                try:
                    check_constraints = [
                        {
                            "name": item.get("name"),
                            "sqltext": json_value(item.get("sqltext")),
                        }
                        for item in inspector.get_check_constraints(
                            table_name,
                            schema=selected_schema,
                        )
                    ]
                except (NotImplementedError, SQLAlchemyError):
                    check_constraints = []

            columns = []
            for raw_column in raw_columns:
                column_type = raw_column["type"]
                identity = json_value(raw_column.get("identity"))
                computed = json_value(raw_column.get("computed"))
                autoincrement = json_value(raw_column.get("autoincrement"))
                column = {
                    "name": raw_column["name"],
                    "type": str(column_type),
                    "nullable": bool(raw_column.get("nullable", True)),
                    "default": json_value(raw_column.get("default")),
                    "primary_key": raw_column["name"] in pk_columns,
                    "comment": json_value(raw_column.get("comment")),
                    "length": json_value(getattr(column_type, "length", None)),
                    "precision": json_value(getattr(column_type, "precision", None)),
                    "scale": json_value(getattr(column_type, "scale", None)),
                    "enum_values": json_value(
                        getattr(column_type, "enums", None)
                        or getattr(column_type, "values", None)
                        or []
                    ),
                    "autoincrement": autoincrement,
                    "identity": identity,
                    "computed": computed,
                    "generated": bool(
                        autoincrement is True or identity is not None or computed is not None
                    ),
                }
                columns.append(column)
                column_metadata[(table_name, raw_column["name"])] = column

            graph.add_node(
                table_name,
                columns=columns,
                primary_keys=pk_columns,
                primary_key=pk_columns[0] if len(pk_columns) == 1 else None,
                schema=selected_schema,
                object_type="view" if table_name in view_names else "table",
                comment=get_table_comment(inspector, table_name, selected_schema),
                unique_constraints=unique_constraints,
                check_constraints=check_constraints,
            )

        known_relations = set()
        for source_table in object_names:
            if source_table in view_names:
                continue
            for foreign_key in inspector.get_foreign_keys(source_table, schema=selected_schema):
                target_table = foreign_key.get("referred_table")
                target_schema = foreign_key.get("referred_schema") or selected_schema
                if target_table not in graph or target_schema != selected_schema:
                    continue
                for source_column, target_column in zip(
                    foreign_key.get("constrained_columns") or [],
                    foreign_key.get("referred_columns") or [],
                ):
                    relation = (source_table, source_column, target_table, target_column)
                    if relation in known_relations:
                        continue
                    graph.add_edge(
                        source_table,
                        target_table,
                        src_col=source_column,
                        dst_col=target_column,
                        type="explicit_fk",
                        confidence=1.0,
                        constraint_name=foreign_key.get("name"),
                        constrained_columns=list(
                            foreign_key.get("constrained_columns") or []
                        ),
                        referred_columns=list(
                            foreign_key.get("referred_columns") or []
                        ),
                        label=f"{source_column} -> {target_column}",
                    )
                    known_relations.add(relation)

        table_lookup = {table_name.lower(): table_name for table_name in object_names}
        for (source_table, source_column), source_info in column_metadata.items():
            lowered_column = source_column.lower()
            if not lowered_column.endswith("_id") or len(lowered_column) <= 3:
                continue
            base_name = lowered_column[:-3]
            for candidate in table_name_candidates(base_name):
                target_table = table_lookup.get(candidate)
                if not target_table or target_table == source_table:
                    continue
                target_primary_keys = primary_keys.get(target_table, [])
                if len(target_primary_keys) != 1:
                    continue
                target_column = target_primary_keys[0]
                relation = (source_table, source_column, target_table, target_column)
                if relation in known_relations:
                    break
                target_info = column_metadata[(target_table, target_column)]
                if not columns_are_compatible(source_info, target_info):
                    continue
                graph.add_edge(
                    source_table,
                    target_table,
                    src_col=source_column,
                    dst_col=target_column,
                    type="inferred_naming",
                    confidence=0.85,
                    label=f"{source_column} -> {target_column} (?)",
                )
                known_relations.add(relation)
                break

        for source_ref, target_ref in load_relation_hints().items():
            source_table, source_column = parse_qualified_column(source_ref)
            target_table, target_column = parse_qualified_column(target_ref)
            source_key = (source_table, source_column)
            target_key = (target_table, target_column)
            if source_key not in column_metadata or target_key not in column_metadata:
                raise ValueError(f"关系提示引用了不存在的字段: {source_ref} -> {target_ref}")
            relation = (source_table, source_column, target_table, target_column)
            if relation in known_relations:
                continue
            if not columns_are_compatible(column_metadata[source_key], column_metadata[target_key]):
                raise ValueError(f"关系提示字段类型不兼容: {source_ref} -> {target_ref}")
            graph.add_edge(
                source_table,
                target_table,
                src_col=source_column,
                dst_col=target_column,
                type="inferred_hint",
                confidence=0.95,
                label=f"{source_column} -> {target_column} (hint)",
            )
            known_relations.add(relation)
        return graph
    finally:
        if owns_engine:
            engine.dispose()


def node_link_data(graph: nx.MultiDiGraph) -> dict[str, Any]:
    try:
        return nx.node_link_data(graph, edges="links")
    except TypeError:
        return nx.node_link_data(graph, link="links")


def write_graph_json(graph: nx.MultiDiGraph, output_file: Path) -> None:
    temporary_file = output_file.with_suffix(output_file.suffix + ".tmp")
    with temporary_file.open("w", encoding="utf-8") as file:
        json.dump(node_link_data(graph), file, indent=2, ensure_ascii=False)
    temporary_file.replace(output_file)


def visualize_graph(graph: nx.MultiDiGraph, output_file: Path) -> None:
    network = Network(
        height="800px",
        width="100%",
        directed=True,
        notebook=False,
        bgcolor="#ffffff",
        font_color="#202326",
    )
    network.set_options(
        '{"physics":{"enabled":true,"barnesHut":{"gravitationalConstant":-8000,"springLength":200}}}'
    )
    for node_name, attributes in graph.nodes(data=True):
        column_names = [column["name"] for column in attributes.get("columns", [])]
        primary_key_text = ", ".join(attributes.get("primary_keys", [])) or "无"
        title = (
            f"<b>{node_name}</b><br>类型: {attributes.get('object_type', 'table')}"
            f"<br>主键: {primary_key_text}<br>字段: {', '.join(column_names)}"
        )
        network.add_node(
            node_name,
            label=node_name,
            title=title,
            color="#4f8f79" if attributes.get("primary_keys") else "#c86b5a",
        )
    for source, target, data in graph.edges(data=True):
        explicit = data["type"] == "explicit_fk"
        network.add_edge(
            source,
            target,
            title=data["label"],
            color="#2f6f55" if explicit else "#b36b22",
            dashes=not explicit,
        )
    network.write_html(str(output_file), open_browser=False)


def parse_args():
    parser = argparse.ArgumentParser(description="从关系型数据库构建表结构关系图")
    parser.add_argument("--output-dir", type=Path, default=DEMO_ROOT)
    parser.add_argument("--schema", default=None, help="覆盖 .env 中的 DB_SCHEMA")
    parser.add_argument("--include-views", action="store_true", help="同时读取视图")
    parser.add_argument("--no-html", action="store_true", help="不生成关系图 HTML")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    try:
        graph = build_table_relationship_graph(
            schema=args.schema,
            include_views=args.include_views,
        )
        graph_file = args.output_dir / "table_graph.json"
        write_graph_json(graph, graph_file)
        if not args.no_html:
            visualize_graph(graph, args.output_dir / "table_relations.html")
    except (SQLAlchemyError, RuntimeError, ValueError) as exc:
        print(f"生成表关系图失败: {exc}")
        return 1

    print(f"数据库: {get_database_url().render_as_string(hide_password=True)}")
    print(f"方言: {get_dialect_label(get_backend_name())}")
    print(f"表数量: {graph.number_of_nodes()}")
    print(f"关系数量: {graph.number_of_edges()}")
    print(f"图谱文件: {graph_file.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
