# -*- coding: utf-8 -*-
"""ai_trace 配置：阈值、时间窗、LLM 环境加载。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

_AI_TRACE_DIR = Path(__file__).resolve().parent

PLACEHOLDER_API_KEYS = {
    "",
    "your_api_key",
    "your_openai_compatible_api_key",
    "changeme",
    "replace_me",
    "xxx",
    "sk-your-api-key",
}

# 异常检测
DEFAULT_CONTAMINATION = 0.08
MIN_EVENTS_FOR_MODEL = 8
TFIDF_MAX_FEATURES = 2048

# 事件链
CHAIN_WINDOW_SECONDS = 30
CHAIN_NEIGHBOR_COUNT = 8
MAX_EVENTS_FOR_LLM = 80

# LLM
DEFAULT_LLM_TIMEOUT = 60
DEFAULT_LLM_TEMPERATURE = 0.2


@dataclass
class TraceConfig:
    """运行时配置快照。"""

    contamination: float = DEFAULT_CONTAMINATION
    min_events_for_model: int = MIN_EVENTS_FOR_MODEL
    tfidf_max_features: int = TFIDF_MAX_FEATURES
    chain_window_seconds: int = CHAIN_WINDOW_SECONDS
    chain_neighbor_count: int = CHAIN_NEIGHBOR_COUNT
    max_events_for_llm: int = MAX_EVENTS_FOR_LLM
    llm_timeout: int = DEFAULT_LLM_TIMEOUT
    llm_temperature: float = DEFAULT_LLM_TEMPERATURE


def llm_env_path() -> Path:
    """llm.env 路径；可用 AI_TRACE_LLM_ENV 覆盖。"""
    configured = os.environ.get("AI_TRACE_LLM_ENV", "").strip()
    if configured:
        return Path(configured)
    return _AI_TRACE_DIR / "llm.env"


def load_llm_env(env_path: Path = None) -> bool:
    """把 llm.env 写入进程环境（已存在的键不覆盖）。"""
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


def get_llm_config() -> Dict[str, str]:
    """聚合 OpenAI Compatible 所需的 api_key / api_base / model。"""
    load_llm_env()
    api_key = (
        os.environ.get("AI_TRACE_LLM_API_KEY", "").strip()
        or os.environ.get("REOLINK_RAG_LLM_API_KEY", "").strip()
        or os.environ.get("OPENAI_API_KEY", "").strip()
    )
    api_base = (
        os.environ.get("AI_TRACE_LLM_API_BASE", "").strip()
        or os.environ.get("REOLINK_RAG_LLM_API_BASE", "").strip()
        or os.environ.get("OPENAI_API_BASE", "").strip()
        or "https://api.openai.com/v1"
    )
    model = (
        os.environ.get("AI_TRACE_LLM_MODEL", "").strip()
        or os.environ.get("REOLINK_RAG_LLM_MODEL", "").strip()
        or os.environ.get("OPENAI_MODEL", "").strip()
        or "gpt-4o-mini"
    )
    return {
        "api_key": api_key,
        "api_base": api_base.rstrip("/"),
        "model": model,
    }


def is_llm_available() -> bool:
    """配置是否足以发起 LLM 调用。"""
    cfg = get_llm_config()
    api_key = cfg.get("api_key") or ""
    if not api_key or api_key.strip().lower() in PLACEHOLDER_API_KEYS:
        return False
    if not (cfg.get("api_base") or "").strip():
        return False
    return not api_key.strip().startswith("crsr_")


def get_llm_status() -> Dict[str, Any]:
    """供健康检查展示的脱敏状态。"""
    cfg = get_llm_config()
    key = cfg.get("api_key") or ""
    masked = ""
    if key:
        masked = key[:6] + "..." + key[-4:] if len(key) > 12 else "***"
    return {
        "api_base": cfg.get("api_base"),
        "model": cfg.get("model"),
        "api_key_masked": masked,
        "available": is_llm_available(),
        "llm_env": str(llm_env_path()),
    }


def get_trace_config() -> TraceConfig:
    """读取运行参数，支持环境变量覆盖。"""
    load_llm_env()
    return TraceConfig(
        contamination=float(
            os.environ.get("AI_TRACE_CONTAMINATION", DEFAULT_CONTAMINATION)
        ),
        min_events_for_model=int(
            os.environ.get("AI_TRACE_MIN_EVENTS_FOR_MODEL", MIN_EVENTS_FOR_MODEL)
        ),
        tfidf_max_features=int(
            os.environ.get("AI_TRACE_TFIDF_MAX_FEATURES", TFIDF_MAX_FEATURES)
        ),
        chain_window_seconds=int(
            os.environ.get("AI_TRACE_CHAIN_WINDOW_SECONDS", CHAIN_WINDOW_SECONDS)
        ),
        chain_neighbor_count=int(
            os.environ.get("AI_TRACE_CHAIN_NEIGHBOR_COUNT", CHAIN_NEIGHBOR_COUNT)
        ),
        max_events_for_llm=int(
            os.environ.get("AI_TRACE_MAX_EVENTS_FOR_LLM", MAX_EVENTS_FOR_LLM)
        ),
        llm_timeout=int(
            os.environ.get("AI_TRACE_LLM_TIMEOUT", DEFAULT_LLM_TIMEOUT)
        ),
        llm_temperature=float(
            os.environ.get("AI_TRACE_LLM_TEMPERATURE", DEFAULT_LLM_TEMPERATURE)
        ),
    )


load_llm_env()
