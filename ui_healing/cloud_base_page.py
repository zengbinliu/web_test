# -*- coding: utf-8 -*-
"""Cloud Page Object 基类：统一自愈定位入口。"""

from typing import Any, Dict, List, Optional, Tuple, Union

from playwright.sync_api import FrameLocator, Locator, Page, expect

from page_ele.ui_healing.element_def import get_element_from_pd
from page_ele.ui_healing.healing_context import HealingContext
from page_ele.ui_healing.healing_gateway import get_healing_gateway
from page_ele.ui_healing.healing_locator import FrameHealingContext, HealingLocator
from page_ele.ui_healing.locator_adapter import to_playwright_locator


class CloudBasePage:
    """Cloud Page Object 基类；子类设置 YAML_PARTS / _pd 后使用 locate 系列 API。"""

    YAML_PARTS: Tuple[str, ...] = ()
    _pd: Dict[str, Any] = {}

    def __init__(self, page: Page):
        self.page = page
        self._gateway = get_healing_gateway()

    def _make_context(
        self,
        key: str,
        *,
        root: Optional[Union[Page, FrameLocator, Locator]] = None,
        parent_keys: Optional[List[str]] = None,
    ) -> HealingContext:
        """组装自愈上下文；root 默认当前 page。"""
        return HealingContext(
            page=self.page,
            yaml_parts=self.YAML_PARTS,
            pd=self._pd,
            element_key=key,
            element=get_element_from_pd(self._pd, key),
            root=self.page if root is None else root,
            parent_keys=list(parent_keys or []),
        )

    def locate(self, key: str) -> HealingLocator:
        """按 YAML 键定位页面元素（失败时可自愈）。"""
        return HealingLocator(self._make_context(key), self._gateway)

    def locate_on(
        self,
        root: Union[Page, FrameLocator, Locator],
        key: str,
        *,
        parent_keys=None,
    ) -> HealingLocator:
        """在指定 root（页面/frame/locator）上按键定位。"""
        return HealingLocator(
            self._make_context(key, root=root, parent_keys=parent_keys),
            self._gateway,
        )

    def frame_locate(self, iframe_key: str) -> FrameHealingContext:
        """进入 iframe，再对其内部元素 locate。"""
        return FrameHealingContext(
            self.page,
            {
                "yaml_parts": self.YAML_PARTS,
                "pd": self._pd,
                "gateway": self._gateway,
                "parent_keys": [],
            },
            iframe_key,
        )

    def expect_visible(self, key: str, *, timeout: int = None):
        """断言元素可见；断言失败且可自愈时愈完再断言一次。"""
        def _assert_visible(locator: HealingLocator) -> None:
            if timeout is None:
                expect(locator.raw).to_be_visible()
            else:
                expect(locator.raw).to_be_visible(timeout=timeout)

        loc = self.locate(key)
        try:
            _assert_visible(loc)
        except Exception as exc:
            ctx = self._make_context(key)
            if not self._gateway.should_attempt_heal(exc, ctx):
                raise
            self._gateway.heal(ctx, exc)
            _assert_visible(self.locate(key))

    def pw_locator(self, key: str) -> Locator:
        """返回原生 Playwright Locator（expect_popup 等不能走 HealingLocator）。"""
        return to_playwright_locator(self.page, get_element_from_pd(self._pd, key))
