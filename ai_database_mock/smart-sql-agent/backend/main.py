import logging
import os
import hashlib
import hmac
import secrets
from pathlib import Path
from typing import Optional

from flask import Flask, jsonify, request, send_from_directory
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

try:
    from .models import APIResponse, ExecuteRequest, QueryRequest, RequestValidationError
    from .new_sql_agent import (
        NewSQLAgent,
        execute_sql_safe,
        is_hierarchical_plan_text,
        parse_hierarchical_plan,
        render_hierarchical_sql,
    )
except ImportError:  # Support `python backend/main.py`.
    from models import APIResponse, ExecuteRequest, QueryRequest, RequestValidationError
    from new_sql_agent import (
        NewSQLAgent,
        execute_sql_safe,
        is_hierarchical_plan_text,
        parse_hierarchical_plan,
        render_hierarchical_sql,
    )


BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"

app = Flask(__name__, static_folder=str(FRONTEND_DIR), static_url_path="")
app.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024

agent = NewSQLAgent()
logger = logging.getLogger(__name__)
confirmation_serializer = URLSafeTimedSerializer(
    os.getenv("CONFIRMATION_SECRET") or secrets.token_urlsafe(32),
    salt="smart-sql-agent-write-confirmation",
)
CONFIRMATION_MAX_AGE_SECONDS = int(os.getenv("CONFIRMATION_MAX_AGE_SECONDS", "300"))


def respond(response: APIResponse, status_code: int = 200):
    return jsonify(response.to_dict()), status_code


def sql_digest(sql: str) -> str:
    return hashlib.sha256(sql.encode("utf-8")).hexdigest()


def issue_confirmation_token(sql: str) -> str:
    return confirmation_serializer.dumps({"sql_digest": sql_digest(sql)})


def validate_confirmation_token(sql: str, token: Optional[str]) -> None:
    if not token:
        raise RequestValidationError("写操作必须先预览，再使用确认令牌执行")
    try:
        payload = confirmation_serializer.loads(
            token,
            max_age=CONFIRMATION_MAX_AGE_SECONDS,
        )
    except SignatureExpired as exc:
        raise RequestValidationError("确认令牌已过期，请重新预览 SQL") from exc
    except BadSignature as exc:
        raise RequestValidationError("确认令牌无效，请重新预览 SQL") from exc

    expected_digest = payload.get("sql_digest", "")
    if not hmac.compare_digest(expected_digest, sql_digest(sql)):
        raise RequestValidationError("SQL 已发生变化，请重新预览后再确认")


@app.get("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.post("/generate")
def generate_sql():
    try:
        query_request = QueryRequest.from_payload(request.get_json(silent=True))
        artifact = agent.generate_sql(query_request.natural_language)
        artifact_type = "data_plan" if is_hierarchical_plan_text(artifact) else "sql"
        message = "分层数据计划生成成功" if artifact_type == "data_plan" else "SQL 生成成功"
        response_data = {"sql": artifact, "artifact_type": artifact_type}
        if artifact_type == "data_plan":
            plan = parse_hierarchical_plan(artifact, agent.graph, require_plan=True)
            response_data["sql_preview"] = render_hierarchical_sql(plan, agent.graph)
        return respond(
            APIResponse(
                True,
                message,
                response_data,
            )
        )
    except RequestValidationError as exc:
        return respond(APIResponse(False, str(exc)), 400)
    except Exception as exc:
        logger.exception("SQL generation failed")
        return respond(APIResponse(False, f"生成失败: {exc}"), 500)


@app.post("/execute")
def execute_sql():
    try:
        execute_request = ExecuteRequest.from_payload(request.get_json(silent=True))
        if execute_request.confirm:
            validate_confirmation_token(
                execute_request.sql,
                execute_request.confirmation_token,
            )
        result = execute_sql_safe(
            execute_request.sql,
            preview_only=not execute_request.confirm,
        )
        if result["type"] == "error":
            return respond(APIResponse(False, result["message"]), 400)

        requires_confirmation = bool(result.pop("requires_confirmation", False))
        if requires_confirmation:
            if result["type"] == "data_plan_preview":
                message = (
                    f"分层数据计划将写入 {result['total_rows']} 行，"
                    "请核对各层数量后确认"
                )
            elif int(result.get("dependency_rows_added", 0)):
                dependency_rows_added = int(result["dependency_rows_added"])
                inferred_values_added = int(result.get("inferred_values_added", 0))
                inferred_message = (
                    f"，并生成 {inferred_values_added} 个缺省字段值"
                    if inferred_values_added
                    else ""
                )
                message = (
                    f"已自动补齐 {dependency_rows_added} 条缺失依赖记录"
                    f"{inferred_message}，"
                    "请核对完整写入计划后确认"
                )
            elif int(result.get("inferred_values_added", 0)):
                message = (
                    f"已根据字段语义生成 {result['inferred_values_added']} 个缺省值，"
                    "请核对完整写入计划后确认"
                )
            else:
                message = "请核对预览结果，然后确认执行写操作"
            confirmation_artifact = (
                result.get("planned_artifact")
                or result.get("planned_sql")
                or execute_request.sql
            )
            result["confirmation_token"] = issue_confirmation_token(
                confirmation_artifact
            )
        elif result["type"] == "data_plan_execution":
            message = f"分层数据写入完成，共插入 {result['total_rows']} 行"
        elif result["type"] == "batch_execution":
            message = f"批量执行完成，共执行 {result['statements_count']} 条语句"
        else:
            message = "执行成功"

        return respond(
            APIResponse(
                True,
                message,
                result,
                requires_confirmation=requires_confirmation,
            )
        )
    except RequestValidationError as exc:
        return respond(APIResponse(False, str(exc)), 400)
    except Exception as exc:
        logger.exception("SQL execution failed")
        return respond(APIResponse(False, f"执行失败: {exc}"), 500)


@app.errorhandler(413)
def request_too_large(_error):
    return respond(APIResponse(False, "请求内容过大"), 413)


if __name__ == "__main__":
    app.run(
        host=os.getenv("APP_HOST", "127.0.0.1"),
        port=int(os.getenv("APP_PORT", "8003")),
        debug=os.getenv("FLASK_DEBUG", "0") == "1",
    )
