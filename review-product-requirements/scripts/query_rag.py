#!/usr/bin/env python3
"""Generic, fail-closed HTTP adapter for requirement-review RAG retrieval.

The adapter remains disabled until the five primary placeholders are replaced and
RAG_ADAPTER_READY=true. Adapt build_request(), extract_items(), and
normalize_result() to the real platform schema before enabling live calls.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any


PLACEHOLDERS = {
    "platform": "<RAG_PLATFORM>",
    "query_interface": "<RAG_QUERY_INTERFACE>",
    "auth_method": "<RAG_AUTH_METHOD>",
    "schema": "<RAG_REQUEST_RESPONSE_SCHEMA>",
    "filter_fields": "<RAG_FILTER_FIELDS>",
}


def is_placeholder(value: str | None) -> bool:
    if value is None:
        return True
    stripped = value.strip()
    return not stripped or (stripped.startswith("<") and stripped.endswith(">"))


def parse_bool(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def parse_positive_int(value: str | None, default: int) -> int:
    try:
        parsed = int(value or default)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


def parse_optional_float(value: str | None) -> float | None:
    if not value or is_placeholder(value):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def load_config() -> dict[str, Any]:
    raw_filter_fields = os.getenv("RAG_FILTER_FIELDS", PLACEHOLDERS["filter_fields"])
    filter_fields = []
    if not is_placeholder(raw_filter_fields) and raw_filter_fields.lower() != "none":
        filter_fields = [item.strip() for item in raw_filter_fields.split(",") if item.strip()]

    config = {
        "platform": os.getenv("RAG_PLATFORM", PLACEHOLDERS["platform"]),
        "query_interface": os.getenv(
            "RAG_QUERY_ENDPOINT", PLACEHOLDERS["query_interface"]
        ),
        "auth_method": os.getenv("RAG_AUTH_METHOD", PLACEHOLDERS["auth_method"]),
        "schema": os.getenv("RAG_SCHEMA_ID", PLACEHOLDERS["schema"]),
        "raw_filter_fields": raw_filter_fields,
        "filter_fields": filter_fields,
        "adapter_ready_requested": parse_bool(os.getenv("RAG_ADAPTER_READY")),
        "token": os.getenv("RAG_API_TOKEN", ""),
        "auth_header": os.getenv("RAG_AUTH_HEADER", "X-API-Key"),
        "default_top_k": parse_positive_int(os.getenv("RAG_TOP_K"), 5),
        "min_relevance": parse_optional_float(os.getenv("RAG_MIN_RELEVANCE")),
    }

    missing = []
    for key in ("platform", "query_interface", "auth_method", "schema"):
        if is_placeholder(config[key]):
            missing.append(PLACEHOLDERS[key])
    if is_placeholder(config["raw_filter_fields"]):
        missing.append(PLACEHOLDERS["filter_fields"])

    auth_method = str(config["auth_method"]).strip().lower()
    if auth_method not in {"none", "no-auth"} and not config["token"]:
        missing.append("RAG_API_TOKEN")

    config["missing"] = missing
    config["ready"] = config["adapter_ready_requested"] and not missing
    return config


def public_config(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "platform": config["platform"],
        "query_interface": config["query_interface"],
        "auth_method": config["auth_method"],
        "schema": config["schema"],
        "filter_fields": config["raw_filter_fields"],
        "adapter_ready_requested": config["adapter_ready_requested"],
        "ready": config["ready"],
        "missing": config["missing"],
        "token_configured": bool(config["token"]),
        "default_top_k": config["default_top_k"],
        "min_relevance": config["min_relevance"],
    }


def parse_filters(values: list[str], allowed_fields: list[str]) -> dict[str, str]:
    filters: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"Invalid filter '{value}'; expected KEY=VALUE")
        key, item_value = value.split("=", 1)
        key = key.strip()
        item_value = item_value.strip()
        if not key or not item_value:
            raise ValueError(f"Invalid filter '{value}'; key and value are required")
        if allowed_fields and "*" not in allowed_fields and key not in allowed_fields:
            raise ValueError(
                f"Filter '{key}' is not in configured RAG_FILTER_FIELDS: "
                + ", ".join(allowed_fields)
            )
        filters[key] = item_value
    return filters


def build_request(args: argparse.Namespace, filters: dict[str, str]) -> dict[str, Any]:
    """Map canonical fields to the real request schema after it is confirmed."""
    payload: dict[str, Any] = {
        "query": args.query,
        "top_k": args.top_k,
        "filters": filters,
    }
    if args.product:
        payload["product"] = args.product
    if args.knowledge_type:
        payload["knowledge_types"] = args.knowledge_type
    return payload


def request_headers(config: dict[str, Any]) -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json; charset=utf-8",
        "User-Agent": "review-product-requirements-rag-adapter/1.0",
    }
    auth_method = str(config["auth_method"]).strip().lower()
    if auth_method == "bearer":
        headers["Authorization"] = f"Bearer {config['token']}"
    elif auth_method in {"api-key", "apikey"}:
        headers[str(config["auth_header"])] = str(config["token"])
    elif auth_method not in {"none", "no-auth"}:
        raise ValueError(
            "Unsupported RAG_AUTH_METHOD. Adapt request_headers() to the confirmed method."
        )
    return headers


def extract_items(raw: Any) -> list[Any]:
    """Extract common result containers; adapt this to the confirmed response schema."""
    if isinstance(raw, list):
        return raw
    if not isinstance(raw, dict):
        return []

    for key in ("results", "documents", "chunks", "matches", "items"):
        value = raw.get(key)
        if isinstance(value, list):
            return value

    data = raw.get("data")
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return extract_items(data)
    return []


def first_value(containers: list[dict[str, Any]], keys: tuple[str, ...]) -> Any:
    for container in containers:
        for key in keys:
            value = container.get(key)
            if value is not None and value != "":
                return value
    return None


def normalize_result(item: Any) -> dict[str, Any]:
    """Normalize common field aliases; adapt mappings to the confirmed schema."""
    if isinstance(item, str):
        return {
            "document_id": None,
            "title": None,
            "knowledge_type": None,
            "version": None,
            "updated_at": None,
            "section": None,
            "content": item,
            "source_url": None,
            "relevance_score": None,
            "valid_from": None,
            "valid_to": None,
        }
    if not isinstance(item, dict):
        return normalize_result(str(item))

    metadata = item.get("metadata")
    containers = [item, metadata] if isinstance(metadata, dict) else [item]
    score = first_value(containers, ("relevance_score", "score", "similarity"))
    try:
        normalized_score = float(score) if score is not None else None
    except (TypeError, ValueError):
        normalized_score = None

    return {
        "document_id": first_value(containers, ("document_id", "doc_id", "id")),
        "title": first_value(containers, ("title", "document_title", "name")),
        "knowledge_type": first_value(containers, ("knowledge_type", "type", "category")),
        "version": first_value(containers, ("version", "document_version")),
        "updated_at": first_value(containers, ("updated_at", "modified_at", "last_updated")),
        "section": first_value(containers, ("section", "section_id", "chunk_id", "location")),
        "content": first_value(containers, ("content", "text", "snippet", "page_content")),
        "source_url": first_value(containers, ("source_url", "url", "uri", "source")),
        "relevance_score": normalized_score,
        "valid_from": first_value(containers, ("valid_from", "effective_from")),
        "valid_to": first_value(containers, ("valid_to", "effective_to", "expires_at")),
    }


def query_rag(
    config: dict[str, Any], payload: dict[str, Any], timeout: float
) -> tuple[Any, list[dict[str, Any]]]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        str(config["query_interface"]),
        data=body,
        headers=request_headers(config),
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = json.loads(response.read().decode("utf-8"))
    normalized = [normalize_result(item) for item in extract_items(raw)]

    min_relevance = config["min_relevance"]
    if min_relevance is not None:
        normalized = [
            item
            for item in normalized
            if item["relevance_score"] is None
            or item["relevance_score"] >= min_relevance
        ]
    return raw, normalized


def emit(data: dict[str, Any], pretty: bool) -> None:
    print(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2 if pretty else None,
            separators=None if pretty else (",", ":"),
        )
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Query a configured RAG HTTP endpoint and normalize evidence metadata."
    )
    parser.add_argument("--query", help="Focused retrieval question")
    parser.add_argument("--product", help="Product or module filter")
    parser.add_argument(
        "--knowledge-type",
        action="append",
        default=[],
        help="Knowledge type; repeat for multiple values",
    )
    parser.add_argument(
        "--filter",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Configured server-side filter; repeat for multiple values",
    )
    parser.add_argument("--top-k", type=int, help="Maximum candidate results")
    parser.add_argument("--timeout", type=float, default=20.0, help="HTTP timeout in seconds")
    parser.add_argument("--show-config", action="store_true", help="Show safe configuration status")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    config = load_config()
    if args.top_k is None:
        args.top_k = config["default_top_k"]

    if args.show_config:
        emit({"status": "configuration", **public_config(config)}, args.pretty)
        return 0

    if not args.query:
        parser.error("--query is required unless --show-config is used")
    if not config["ready"]:
        emit(
            {
                "status": "not_configured",
                "message": "RAG retrieval was not attempted. Replace placeholders and set RAG_ADAPTER_READY=true.",
                "configuration": public_config(config),
            },
            args.pretty,
        )
        return 0

    try:
        filters = parse_filters(args.filter, config["filter_fields"])
        payload = build_request(args, filters)
        _raw, results = query_rag(config, payload, args.timeout)
        emit(
            {
                "status": "ok" if results else "no_results",
                "platform": config["platform"],
                "schema": config["schema"],
                "query": args.query,
                "filters": filters,
                "result_count": len(results),
                "results": results,
            },
            args.pretty,
        )
        return 0
    except ValueError as error:
        emit({"status": "configuration_error", "message": str(error)}, args.pretty)
        return 2
    except urllib.error.HTTPError as error:
        emit(
            {
                "status": "http_error",
                "http_status": error.code,
                "message": "RAG service returned an HTTP error; response body was not printed.",
            },
            args.pretty,
        )
        return 3
    except urllib.error.URLError as error:
        emit(
            {
                "status": "connection_error",
                "message": str(error.reason),
            },
            args.pretty,
        )
        return 4
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        emit(
            {
                "status": "response_error",
                "message": f"RAG response was not valid UTF-8 JSON: {error}",
            },
            args.pretty,
        )
        return 5


if __name__ == "__main__":
    sys.exit(main())
