# -*- coding: utf-8 -*-
"""自愈运行时配置（优先读 page_ele/ui_healing/llm.env，再回落 configs 默认值）。"""

import os
from dataclasses import dataclass

from configs import config as _cfg
from page_ele.ui_healing.llm_config import get_llm_config, load_llm_env

_DEFAULT_FINDER_MODEL = "gpt-5.6-terra-medium"
_DEFAULT_VERIFIER_MODEL = "gpt-5.6-luna-medium"


@dataclass
class HealingConfig:
    """一次自愈运行所需的开关与 LLM 参数快照。"""

    enabled: bool
    persist: bool
    max_per_run: int
    provider: str
    api_base: str
    api_key: str
    model: str
    finder_model: str
    verifier_model: str
    api_timeout_s: int
    dom_max_chars: int
    max_candidates: int
    testcase_id: str


def _env_flag(name: str, default: str) -> bool:
    """解析 1/true/yes 类开关。"""
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes")


def _env_int(name: str, default: int) -> int:
    """解析整数环境变量，非法时回落 default。"""
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def get_healing_config() -> HealingConfig:
    """合并 llm.env 与环境变量；行为开关以 llm.env / CLOUD_HEALING_* 为准。"""
    load_llm_env()
    llm = get_llm_config()
    provider = os.getenv("CLOUD_HEALING_LLM_PROVIDER", "").strip() or llm.get("provider", "openai")
    api_key = (
        os.getenv("CLOUD_HEALING_API_KEY", "").strip()
        or os.getenv("REOLINK_RAG_LLM_API_KEY", "").strip()
        or os.getenv("OPENAI_API_KEY", "").strip()
        or llm.get("api_key", "")
    )
    api_base = (
        os.getenv("CLOUD_HEALING_API_BASE", "").strip()
        or os.getenv("REOLINK_RAG_LLM_API_BASE", "").strip()
        or os.getenv("OPENAI_API_BASE", "").strip()
        or llm.get("api_base", "")
    )
    finder_model = (
        os.getenv("CLOUD_HEALING_FINDER_MODEL", "").strip()
        or os.getenv("REOLINK_RAG_LLM_FINDER_MODEL", "").strip()
        or llm.get("finder_model", "")
        or _DEFAULT_FINDER_MODEL
    )
    verifier_model = (
        os.getenv("CLOUD_HEALING_VERIFIER_MODEL", "").strip()
        or os.getenv("REOLINK_RAG_LLM_VERIFIER_MODEL", "").strip()
        or llm.get("verifier_model", "")
        or _DEFAULT_VERIFIER_MODEL
    )
    model = (
        os.getenv("CLOUD_HEALING_MODEL", "").strip()
        or llm.get("model", "")
        or finder_model
    )
    return HealingConfig(
        enabled=_env_flag("CLOUD_HEALING_ENABLED", "1" if _cfg.HEALING_ENABLED else "0"),
        persist=_env_flag("CLOUD_HEALING_PERSIST", "1" if _cfg.HEALING_PERSIST else "0"),
        max_per_run=_env_int("CLOUD_HEALING_MAX_PER_RUN", _cfg.HEALING_MAX_PER_RUN),
        provider=provider or "openai",
        api_base=api_base.rstrip("/") if api_base else "",
        api_key=api_key,
        model=model,
        finder_model=finder_model,
        verifier_model=verifier_model,
        api_timeout_s=_env_int("CLOUD_HEALING_API_TIMEOUT_S", _cfg.HEALING_API_TIMEOUT_S),
        dom_max_chars=_env_int("CLOUD_HEALING_DOM_MAX_CHARS", _cfg.HEALING_DOM_MAX_CHARS),
        max_candidates=_env_int("CLOUD_HEALING_MAX_CANDIDATES", _cfg.HEALING_MAX_CANDIDATES),
        testcase_id=os.getenv("CLOUD_HEALING_TESTCASE_ID", _cfg.HEALING_TESTCASE_ID).strip(),
    )
