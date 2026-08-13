from __future__ import annotations

import os
import time
from typing import Any

import requests


CURSOR_API_BASE = "https://api.cursor.com/v1"
# auto / 省略 model → 走 IDE 同款 First-party 模型池；显式 composer-2.5 等会走 API 池并受 Spend Limit 约束
DEFAULT_CURSOR_MODEL = "auto"
DEFAULT_POLL_INTERVAL = 2.0
DEFAULT_MAX_WAIT_SECONDS = 180
TERMINAL_STATUSES = {"FINISHED", "ERROR", "CANCELLED", "EXPIRED"}


def cursor_api_base() -> str:
    configured = os.environ.get("REOLINK_RAG_CURSOR_API_BASE", "").strip()
    return configured.rstrip("/") if configured else CURSOR_API_BASE


def cursor_model_id() -> str:
    return (
        os.environ.get("REOLINK_RAG_LLM_MODEL", "").strip()
        or os.environ.get("CURSOR_RAG_MODEL", "").strip()
        or DEFAULT_CURSOR_MODEL
    )


def cursor_poll_interval() -> float:
    raw = os.environ.get("REOLINK_RAG_CURSOR_POLL_INTERVAL", "").strip()
    try:
        return max(0.5, float(raw))
    except ValueError:
        return DEFAULT_POLL_INTERVAL


def cursor_max_wait_seconds() -> int:
    raw = os.environ.get("REOLINK_RAG_CURSOR_TIMEOUT", "").strip()
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_MAX_WAIT_SECONDS
    return max(10, min(value, 600))


def cursor_headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": "Bearer %s" % api_key,
        "Content-Type": "application/json",
    }


def build_cursor_rag_prompt(question: str, context_blocks: list[str]) -> str:
    context = "\n\n".join(context_blocks)
    return (
        "你是 Reolink 禅道测试用例知识库助手。\n"
        "任务：仅依据下方检索到的用例片段，用中文回答用户问题。\n"
        "要求：\n"
        "1. 不要写代码、不要调用工具、不要修改文件。\n"
        "2. 若依据不足，明确说明“依据不足”。\n"
        "3. 先给出简洁结论，再列出引用的 case_id。\n"
        "4. 不要编造未出现在依据中的业务规则。\n\n"
        "用户问题：%s\n\n"
        "检索到的用例片段：\n%s"
    ) % (question, context)


def build_cursor_camovue_rag_prompt(question: str, context_blocks: list[str]) -> str:
    context = "\n\n".join(context_blocks)
    return (
        "你是 Camovue 2026 云服务类型套餐知识库助手。\n"
        "任务：仅依据下方检索到的知识片段，用中文回答用户问题。\n"
        "要求：\n"
        "1. 不要写代码、不要调用工具、不要修改文件。\n"
        "2. 若依据不足，明确说明“依据不足”。\n"
        "3. 先给出简洁结论，再列出引用的主题/entry_id。\n"
        "4. 不要编造未出现在依据中的业务规则。\n\n"
        "用户问题：%s\n\n"
        "检索到的知识片段：\n%s"
    ) % (question, context)


def should_omit_cursor_model(model_id: str) -> bool:
    normalized = (model_id or "").strip().lower()
    return normalized in {"", "default"}


def build_agent_model_payload(model_id: str) -> dict[str, Any] | None:
    if should_omit_cursor_model(model_id):
        return None
    return {"id": model_id.strip()}


def create_no_repo_agent(
    api_key: str,
    prompt_text: str,
    *,
    model_id: str,
    name: str = "askreolink-rag",
) -> tuple[str, str]:
    payload: dict[str, Any] = {
        "prompt": {"text": prompt_text},
        "name": name[:100],
    }
    model_payload = build_agent_model_payload(model_id)
    if model_payload is not None:
        payload["model"] = model_payload
    response = requests.post(
        "%s/agents" % cursor_api_base(),
        headers=cursor_headers(api_key),
        json=payload,
        timeout=60,
    )
    response.raise_for_status()
    data = response.json()
    agent = data.get("agent") or {}
    run = data.get("run") or {}
    agent_id = str(agent.get("id") or "").strip()
    run_id = str(run.get("id") or agent.get("latestRunId") or "").strip()
    if not agent_id or not run_id:
        raise RuntimeError("Cursor Cloud Agent 创建成功但未返回 agent/run ID。")
    return agent_id, run_id


def get_run(api_key: str, agent_id: str, run_id: str) -> dict[str, Any]:
    response = requests.get(
        "%s/agents/%s/runs/%s" % (cursor_api_base(), agent_id, run_id),
        headers=cursor_headers(api_key),
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


def archive_agent(api_key: str, agent_id: str) -> None:
    try:
        requests.post(
            "%s/agents/%s/archive" % (cursor_api_base(), agent_id),
            headers=cursor_headers(api_key),
            timeout=30,
        )
    except Exception:
        pass


def wait_for_run_result(api_key: str, agent_id: str, run_id: str) -> str:
    deadline = time.time() + cursor_max_wait_seconds()
    last_status = ""
    while time.time() < deadline:
        run = get_run(api_key, agent_id, run_id)
        status = str(run.get("status") or "").strip()
        last_status = status or last_status
        if status in TERMINAL_STATUSES:
            if status == "FINISHED":
                result = str(run.get("result") or "").strip()
                if result:
                    return result
                raise RuntimeError("Cursor Cloud Agent 已完成但未返回 result。")
            raise RuntimeError("Cursor Cloud Agent 运行失败，状态=%s。" % status)
        time.sleep(cursor_poll_interval())
    raise RuntimeError(
        "Cursor Cloud Agent 等待超时（%ss，最后状态=%s）。可通过 REOLINK_RAG_CURSOR_TIMEOUT 调整。"
        % (cursor_max_wait_seconds(), last_status or "unknown")
    )


def generate_answer_via_cursor_agent(
    api_key: str,
    question: str,
    context_blocks: list[str],
    *,
    prompt_builder=None,
    agent_name: str = "askreolink-rag",
) -> str:
    if not context_blocks:
        return "未检索到足够依据，无法生成回答。"
    builder = prompt_builder or build_cursor_rag_prompt
    prompt_text = builder(question, context_blocks)
    agent_id = ""
    try:
        agent_id, run_id = create_no_repo_agent(
            api_key,
            prompt_text,
            model_id=cursor_model_id(),
            name=agent_name,
        )
        return wait_for_run_result(api_key, agent_id, run_id)
    finally:
        if agent_id:
            archive_agent(api_key, agent_id)
