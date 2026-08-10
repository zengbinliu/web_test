# -*- coding: utf-8 -*-
"""自愈跳过规则：加载 heal_skip.yml，判断本次失败是否应跳过 LLM。"""

from functools import lru_cache
from pathlib import Path
from typing import List, Optional, Set, Tuple

import yaml

from page_ele.ui_healing.healing_context import HealingContext
from utils.logger import get_logger

logger = get_logger(__name__)

_SKIP_FILE = Path(__file__).resolve().parent / "heal_skip.yml"


@lru_cache(maxsize=1)
def _load_skip_rules() -> Tuple[Set[str], Tuple[str, ...]]:
    """读取 skip_elements / skip_when_page_text；文件缺失则空规则。"""
    if not _SKIP_FILE.is_file():
        return set(), ()
    try:
        raw = yaml.safe_load(_SKIP_FILE.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        logger.warning("加载 heal_skip.yml 失败: %s", exc)
        return set(), ()

    elements: Set[str] = set()
    for item in raw.get("skip_elements") or []:
        text = str(item).strip().replace("\\", "/")
        if text:
            elements.add(text)

    patterns: List[str] = []
    for item in raw.get("skip_when_page_text") or []:
        text = str(item).strip()
        if text:
            patterns.append(text)
    return elements, tuple(patterns)


def reload_skip_rules() -> None:
    """测试或热更新时清空缓存。"""
    _load_skip_rules.cache_clear()


def _match_skip_element(ctx: HealingContext, elements: Set[str]) -> Optional[str]:
    """命中 skip_elements 时返回匹配条目，否则 None。"""
    yaml_key = f"{ctx.yaml_file}/{ctx.element_key}".replace("\\", "/")
    if yaml_key in elements:
        return yaml_key
    if ctx.element_key in elements:
        return ctx.element_key
    return None


def _match_page_text(ctx: HealingContext, patterns: Tuple[str, ...]) -> Optional[str]:
    """页面可见文案命中任一模式时返回该模式，否则 None。"""
    if not patterns:
        return None
    try:
        body = (ctx.page.locator("body").inner_text(timeout=2000) or "").strip()
    except Exception:
        return None
    if not body:
        return None
    lowered = body.lower()
    for pattern in patterns:
        if pattern.lower() in lowered:
            return pattern
    return None


def should_skip_heal(ctx: HealingContext) -> bool:
    """是否因配置规则跳过本次自愈。"""
    elements, patterns = _load_skip_rules()
    matched = _match_skip_element(ctx, elements)
    if matched:
        logger.info(
            "跳过 AI 自愈（skip_elements=%s）: %s/%s",
            matched,
            ctx.yaml_file,
            ctx.element_key,
        )
        return True

    matched_text = _match_page_text(ctx, patterns)
    if matched_text:
        logger.info(
            "跳过 AI 自愈（页面文案含 %r）: %s/%s",
            matched_text,
            ctx.yaml_file,
            ctx.element_key,
        )
        return True
    return False
