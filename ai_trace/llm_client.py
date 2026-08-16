# -*- coding: utf-8 -*-
"""OpenAI Compatible LLM 调用（自包含，不依赖 RAG 模块）。"""

from __future__ import annotations

from typing import Callable, List, Optional

import requests

from .config import get_llm_config, get_trace_config, is_llm_available

ChatFn = Callable[[List[dict]], str]


def chat_completions(
    messages: List[dict],
    *,
    timeout: Optional[int] = None,
    temperature: Optional[float] = None,
) -> str:
    """调用 chat/completions，返回助手文本。"""
    if not is_llm_available():
        raise RuntimeError(
            "未配置可用的 LLM。请在 ai_trace/llm.env 设置 AI_TRACE_LLM_API_KEY "
            "与 AI_TRACE_LLM_API_BASE，或设置对应环境变量。"
        )
    cfg = get_llm_config()
    trace_cfg = get_trace_config()
    url = "%s/chat/completions" % cfg["api_base"]
    payload = {
        "model": cfg["model"],
        "messages": messages,
        "temperature": (
            trace_cfg.llm_temperature if temperature is None else temperature
        ),
    }
    headers = {
        "Authorization": "Bearer %s" % cfg["api_key"],
        "Content-Type": "application/json",
    }
    response = requests.post(
        url,
        headers=headers,
        json=payload,
        timeout=timeout or trace_cfg.llm_timeout,
    )
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
