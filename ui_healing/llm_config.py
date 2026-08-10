# -*- coding: utf-8 -*-
"""UI 自愈 LLM 配置加载（读取同目录 llm.env）。"""

import os
from pathlib import Path
from typing import Any, Dict

from utils.logger import get_logger

logger = get_logger(__name__)

_UI_HEALING_DIR = Path(__file__).resolve().parent

PLACEHOLDER_API_KEYS = {
    "",
    "your_api_key",
    "your_openai_compatible_api_key",
    "changeme",
    "replace_me",
    "xxx",
    "sk-your-api-key",
}


def llm_env_path() -> Path:
    """llm.env 路径；可用 CLOUD_HEALING_LLM_ENV 覆盖。"""
    configured = os.environ.get("CLOUD_HEALING_LLM_ENV", "").strip()
    if configured:
        return Path(configured)
    return _UI_HEALING_DIR / "llm.env"


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
    """聚合 OpenAICompatible 所需的 api_key / api_base / model / finder / verifier。"""
    load_llm_env()
    api_key = (
        os.environ.get("REOLINK_RAG_LLM_API_KEY", "").strip()
        or os.environ.get("OPENAI_API_KEY", "").strip()
    )
    api_base = (
        os.environ.get("REOLINK_RAG_LLM_API_BASE", "").strip()
        or os.environ.get("OPENAI_API_BASE", "").strip()
        or "https://api.openai.com/v1"
    )
    model = (
        os.environ.get("REOLINK_RAG_LLM_MODEL", "").strip()
        or os.environ.get("OPENAI_MODEL", "").strip()
        or "gpt-4o-mini"
    )
    return {
        "provider": (
            os.environ.get("REOLINK_RAG_LLM_PROVIDER", "").strip().lower() or "openai"
        ),
        "api_key": api_key,
        "api_base": api_base.rstrip("/"),
        "model": model,
        "finder_model": (
            os.environ.get("CLOUD_HEALING_FINDER_MODEL", "").strip()
            or os.environ.get("REOLINK_RAG_LLM_FINDER_MODEL", "").strip()
        ),
        "verifier_model": (
            os.environ.get("CLOUD_HEALING_VERIFIER_MODEL", "").strip()
            or os.environ.get("REOLINK_RAG_LLM_VERIFIER_MODEL", "").strip()
        ),
    }


def is_llm_available() -> bool:
    """配置是否足以发起 Agently OpenAICompatible 调用。"""
    cfg = get_llm_config()
    api_key = cfg.get("api_key") or ""
    if not api_key or api_key.strip().lower() in PLACEHOLDER_API_KEYS:
        return False
    if not (cfg.get("api_base") or "").strip():
        return False
    return not api_key.strip().startswith("crsr_")


def get_llm_status() -> Dict[str, Any]:
    """供连通性探测展示的脱敏状态。"""
    cfg = get_llm_config()
    key = cfg.get("api_key") or ""
    masked = ""
    if key:
        masked = key[:6] + "..." + key[-4:] if len(key) > 12 else "***"
    return {
        "provider": cfg.get("provider"),
        "api_base": cfg.get("api_base"),
        "model": cfg.get("model"),
        "finder_model": cfg.get("finder_model"),
        "verifier_model": cfg.get("verifier_model"),
        "api_key_masked": masked,
        "available": is_llm_available(),
        "llm_env": str(llm_env_path()),
    }


# 导入时预载 llm.env，便于后续 get_healing_config / 连通性探测直接读环境变量
load_llm_env()
