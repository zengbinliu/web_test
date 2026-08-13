from __future__ import annotations

import json
import os
import pathlib
from typing import Any

import requests

from cursor_rag_client import generate_answer_via_cursor_agent


DEFAULT_TIMEOUT = 60
PLACEHOLDER_API_KEYS = {
    "",
    "your_api_key",
    "your_cursor_api_key",
    "your_openai_compatible_api_key",
    "changeme",
    "replace_me",
    "xxx",
    "sk-your-api-key",
}


def llm_env_path() -> pathlib.Path:
    configured = os.environ.get("REOLINK_RAG_LLM_ENV", "").strip()
    if configured:
        return pathlib.Path(configured)
    return pathlib.Path(__file__).resolve().parent / "llm.env"


def load_llm_env(env_path: pathlib.Path | None = None) -> bool:
    path = env_path or llm_env_path()
    if not path.exists():
        return False
    loaded = False
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("set "):
            line = line[4:].strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if not key:
            continue
        if not os.environ.get(key):
            os.environ[key] = value
            loaded = True
    return loaded


load_llm_env()


def is_placeholder_api_key(api_key: str) -> bool:
    return api_key.strip().lower() in PLACEHOLDER_API_KEYS


def llm_provider() -> str:
    configured = os.environ.get("REOLINK_RAG_LLM_PROVIDER", "").strip().lower()
    if configured:
        return configured
    if cursor_api_key() and is_cursor_api_key(cursor_api_key()):
        return "cursor"
    api_key = os.environ.get("REOLINK_RAG_LLM_API_KEY", "").strip() or os.environ.get("OPENAI_API_KEY", "").strip()
    if api_key.startswith("crsr_"):
        return "cursor"
    return "openai"


def cursor_api_key() -> str:
    return (
        os.environ.get("CURSOR_API_KEY", "").strip()
        or os.environ.get("REOLINK_RAG_LLM_API_KEY", "").strip()
    )


def is_cursor_api_key(api_key: str) -> bool:
    return api_key.strip().startswith("crsr_")


def verify_cursor_api_key(api_key: str) -> dict[str, str]:
    if not api_key:
        return {}
    response = requests.get(
        "https://api.cursor.com/v1/me",
        headers={"Authorization": "Bearer %s" % api_key},
        timeout=DEFAULT_TIMEOUT,
    )
    response.raise_for_status()
    data = response.json()
    return {
        "api_key_name": str(data.get("apiKeyName") or ""),
        "user_email": str(data.get("userEmail") or ""),
    }


def llm_config() -> dict[str, str]:
    provider = llm_provider()
    if provider == "cursor":
        return {
            "provider": "cursor",
            "api_key": cursor_api_key(),
            "api_base": "https://api.cursor.com/v1",
            "model": (
                os.environ.get("REOLINK_RAG_LLM_MODEL", "").strip()
                or os.environ.get("CURSOR_RAG_MODEL", "").strip()
                or "auto"
            ),
        }
    api_key = os.environ.get("REOLINK_RAG_LLM_API_KEY", "").strip() or os.environ.get("OPENAI_API_KEY", "").strip()
    api_base = os.environ.get("REOLINK_RAG_LLM_API_BASE", "").strip() or os.environ.get("OPENAI_API_BASE", "").strip()
    if not api_base:
        api_base = "https://api.openai.com/v1"
    model = os.environ.get("REOLINK_RAG_LLM_MODEL", "").strip() or os.environ.get("OPENAI_MODEL", "").strip() or "gpt-4o-mini"
    return {
        "provider": "openai",
        "api_key": api_key,
        "api_base": api_base.rstrip("/"),
        "model": model,
    }


def llm_available() -> bool:
    config = llm_config()
    api_key = config["api_key"]
    if not api_key or is_placeholder_api_key(api_key):
        return False
    if config["provider"] == "cursor":
        if not is_cursor_api_key(api_key):
            return False
        try:
            verify_cursor_api_key(api_key)
            return True
        except Exception:
            return False
    if is_cursor_api_key(api_key):
        return False
    return True


def cursor_api_status() -> dict[str, Any]:
    api_key = cursor_api_key()
    if not api_key or is_placeholder_api_key(api_key):
        return {"configured": False}
    if not is_cursor_api_key(api_key):
        return {"configured": False}
    try:
        profile = verify_cursor_api_key(api_key)
        return {"configured": True, "verified": True, **profile}
    except Exception as exc:
        return {"configured": True, "verified": False, "error": str(exc)}


DEFAULT_SYSTEM_PROMPT = (
    "你是 Reolink 测试业务知识库助手。请仅依据提供的禅道测试用例片段回答问题。"
    "如果依据不足，请明确说明“依据不足”。"
    "回答必须中文，先给出简洁结论，再列出引用的 case_id。"
    "不要编造未出现在依据中的业务规则。"
)
DEFAULT_USER_PROMPT_TEMPLATE = (
    "问题：%s\n\n"
    "请基于以下检索到的用例片段作答，并在结尾列出引用 case_id：\n\n"
    "%s"
)


def build_rag_prompt(
    question: str,
    context_blocks: list[str],
    *,
    system_prompt: str | None = None,
    user_prompt_template: str | None = None,
) -> list[dict[str, str]]:
    context = "\n\n".join(context_blocks)
    system = system_prompt or DEFAULT_SYSTEM_PROMPT
    template = user_prompt_template or DEFAULT_USER_PROMPT_TEMPLATE
    user_prompt = template % (question, context)
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user_prompt},
    ]


def generate_rag_answer_openai(
    question: str,
    context_blocks: list[str],
    config: dict[str, str],
    *,
    system_prompt: str | None = None,
    user_prompt_template: str | None = None,
) -> str:
    if not config["api_key"]:
        raise RuntimeError("未配置 LLM API Key。请设置 REOLINK_RAG_LLM_API_KEY 或 OPENAI_API_KEY。")
    if not context_blocks:
        return "未检索到足够依据，无法生成回答。"

    messages = build_rag_prompt(
        question,
        context_blocks,
        system_prompt=system_prompt,
        user_prompt_template=user_prompt_template,
    )
    url = "%s/chat/completions" % config["api_base"]
    payload = {
        "model": config["model"],
        "messages": messages,
        "temperature": 0.2,
    }
    headers = {
        "Authorization": "Bearer %s" % config["api_key"],
        "Content-Type": "application/json",
    }
    response = requests.post(url, headers=headers, json=payload, timeout=DEFAULT_TIMEOUT)
    response.raise_for_status()
    data = response.json()
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("LLM 返回为空。")
    message = choices[0].get("message") or {}
    content = str(message.get("content") or "").strip()
    if not content:
        raise RuntimeError("LLM 未返回文本内容。")
    return content


def generate_rag_answer(
    question: str,
    context_blocks: list[str],
    *,
    system_prompt: str | None = None,
    user_prompt_template: str | None = None,
    cursor_prompt_builder=None,
    agent_name: str = "askreolink-rag",
) -> str:
    config = llm_config()
    if config["provider"] == "cursor":
        return generate_answer_via_cursor_agent(
            config["api_key"],
            question,
            context_blocks,
            prompt_builder=cursor_prompt_builder,
            agent_name=agent_name,
        )
    return generate_rag_answer_openai(
        question,
        context_blocks,
        config,
        system_prompt=system_prompt,
        user_prompt_template=user_prompt_template,
    )


def synthesize_extractive_answer(question: str, context_blocks: list[str], direct_answer_lines: list[str]) -> str:
    if direct_answer_lines:
        body = []
        for line in direct_answer_lines:
            stripped = str(line).strip()
            if stripped and stripped != "结论:":
                body.append(stripped.lstrip("- ").strip())
        if body:
            return "结论：%s" % "；".join(body[:3])

    if not context_blocks:
        return "未检索到足够依据。"

    snippets: list[str] = []
    for block in context_blocks[:3]:
        for line in block.splitlines():
            line = line.strip()
            if line.startswith("预期:") or line.startswith("步骤:"):
                snippets.append(line.split(":", 1)[1].strip())
            elif line.startswith("标题:"):
                snippets.append(line.split(":", 1)[1].strip())
    snippets = [item for item in snippets if item]
    if snippets:
        return "结论：%s" % "；".join(snippets[:3])
    return "已检索到相关用例，请查看下方引用依据。"
