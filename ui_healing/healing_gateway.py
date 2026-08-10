# -*- coding: utf-8 -*-
"""元素自愈编排：捕获失败 → DOM → LLM → 校验 → 持久化。"""

from typing import Any, Dict, Optional, Set

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from page_ele.ui_healing.audit_log import append_audit_record
from page_ele.ui_healing.config import HealingConfig, get_healing_config
from page_ele.ui_healing.dom_extractor import build_metadata, extract_dom
from page_ele.ui_healing.element_def import ElementDef
from page_ele.ui_healing.heal_skip import should_skip_heal
from page_ele.ui_healing.healing_context import HealingContext
from page_ele.ui_healing.llm_client import suggest_locator_candidates
from page_ele.ui_healing.locator_persister import save_page_yaml_key, update_pd_value
from page_ele.ui_healing.locator_validator import pick_valid_candidate
from utils.logger import get_logger

logger = get_logger(__name__)

_HEALABLE_ERRORS = (PlaywrightTimeoutError, PlaywrightError, TimeoutError, AssertionError)
_YAML_BACKUP_HINT = "data/healing_audit/yaml_backups/"


class HealingGateway:
    """单次运行内限制 LLM 次数，并对同一元素只自愈一次。"""

    def __init__(self):
        self._llm_calls = 0
        self._healed_cache: Set[str] = set()

    def reset_run(self) -> None:
        """用例/批次开始时清空计数与缓存。"""
        self._llm_calls = 0
        self._healed_cache.clear()

    def should_attempt_heal(
        self,
        exc: BaseException,
        ctx: Optional[HealingContext] = None,
    ) -> bool:
        """是否应对该异常尝试自愈（开关、跳过规则、次数、异常类型）。"""
        cfg = get_healing_config()
        if not cfg.enabled:
            return False
        if ctx is not None and should_skip_heal(ctx):
            return False
        if self._llm_calls >= cfg.max_per_run:
            logger.warning("已达单次运行 LLM 调用上限 %s，跳过自愈", cfg.max_per_run)
            return False
        return isinstance(exc, _HEALABLE_ERRORS)

    def heal(self, ctx: HealingContext, exc: BaseException) -> ElementDef:
        """对失效元素推理新选择器；失败则重新抛出原异常。"""
        if ctx.cache_key in self._healed_cache:
            raise exc
        if should_skip_heal(ctx):
            raise exc
        cfg = get_healing_config()
        if not cfg.enabled:
            raise exc

        old_selector = ctx.element.selector
        meta = build_metadata(ctx.page, error_message=str(exc))
        payload = self._build_llm_payload(ctx, old_selector, meta, cfg.dom_max_chars)

        self._llm_calls += 1
        self._healed_cache.add(ctx.cache_key)
        candidates = suggest_locator_candidates(payload)
        picked = pick_valid_candidate(ctx.root, candidates, max_candidates=cfg.max_candidates)
        if picked is None:
            append_audit_record(
                self._audit_record(
                    ctx, cfg, meta, status="failed", old_selector=old_selector, error=str(exc)[:500]
                )
            )
            raise exc

        return self._commit_healed(ctx, cfg, meta, old_selector, picked)

    def _build_llm_payload(
        self,
        ctx: HealingContext,
        old_selector: str,
        meta: Dict[str, Any],
        dom_max_chars: int,
    ) -> Dict[str, Any]:
        """组装发给 LLM 的上下文。"""
        return {
            "element_key": ctx.element_key,
            "element_semantic": ctx.element.semantic,
            "old_selector": old_selector,
            "locator_type": ctx.element.locator_type,
            "parent_keys": ctx.parent_keys,
            "dom_snippet": extract_dom(ctx.page, root=ctx.root, max_chars=dom_max_chars),
            **meta,
        }

    def _commit_healed(
        self,
        ctx: HealingContext,
        cfg: HealingConfig,
        meta: Dict[str, Any],
        old_selector: str,
        picked: ElementDef,
    ) -> ElementDef:
        """写回内存/_pd，按需持久化 YAML，并记成功审计。"""
        # 保留原 semantic/scope，只替换定位信息
        new_element = ElementDef(
            key=ctx.element_key,
            selector=picked.selector,
            semantic=ctx.element.semantic,
            locator_type=picked.locator_type,
            scope=ctx.element.scope,
        )
        update_pd_value(ctx.pd, ctx.element_key, new_element)
        ctx.element = new_element
        append_audit_record(
            self._audit_record(
                ctx,
                cfg,
                meta,
                status="success",
                old_selector=old_selector,
                new=new_element.selector,
                locator_type=new_element.locator_type,
                yaml_backup=_YAML_BACKUP_HINT,
            )
        )
        if cfg.persist:
            save_page_yaml_key(ctx.yaml_parts, ctx.element_key, new_element)
        logger.info(
            "元素自愈成功: %s/%s -> %s",
            ctx.yaml_file,
            ctx.element_key,
            new_element.selector,
        )
        return new_element

    @staticmethod
    def _audit_record(
        ctx: HealingContext,
        cfg: HealingConfig,
        meta: Dict[str, Any],
        *,
        status: str,
        old_selector: str,
        **extra: Any,
    ) -> Dict[str, Any]:
        """构造审计字段；extra 中值为 None 的键不会写入。"""
        record: Dict[str, Any] = {
            "status": status,
            "yaml": ctx.yaml_file,
            "key": ctx.element_key,
            "old": old_selector,
            "url": meta.get("page_url"),
            "testcase_id": cfg.testcase_id,
            "llm_model": cfg.finder_model or cfg.model,
        }
        for key, value in extra.items():
            if value is not None:
                record[key] = value
        return record


_gateway: Optional[HealingGateway] = None


def get_healing_gateway() -> HealingGateway:
    """进程内单例网关。"""
    global _gateway
    if _gateway is None:
        _gateway = HealingGateway()
    return _gateway
