# -*- coding: utf-8 -*-
"""带自愈能力的 Playwright Locator 包装。"""

from typing import Any, Callable, Optional

from playwright.sync_api import FrameLocator, Locator, Page

from page_ele.ui_healing.element_def import get_element_from_pd
from page_ele.ui_healing.healing_context import HealingContext
from page_ele.ui_healing.healing_gateway import HealingGateway
from page_ele.ui_healing.locator_adapter import to_playwright_locator


class HealingLocator:
    """API 贴近 Playwright Locator；click/fill 等失败时走自愈后重试。"""

    def __init__(
        self,
        ctx: HealingContext,
        gateway: HealingGateway,
        *,
        use_first: bool = False,
        inner: Optional[Locator] = None,
    ):
        self._ctx = ctx
        self._gateway = gateway
        self._use_first = use_first
        self._inner = inner

    @property
    def raw(self) -> Locator:
        """当前生效的原生 Locator（已应用 first / nth）。"""
        loc = self._inner or to_playwright_locator(self._ctx.root, self._ctx.element)
        return loc.first if self._use_first else loc

    @property
    def first(self) -> "HealingLocator":
        """取匹配集合中的第一个。"""
        return HealingLocator(self._ctx, self._gateway, use_first=True, inner=self._inner)

    def nth(self, index: int) -> "HealingLocator":
        """取匹配集合中的第 index 个。"""
        base = self._inner or to_playwright_locator(self._ctx.root, self._ctx.element)
        return HealingLocator(self._ctx, self._gateway, use_first=False, inner=base.nth(index))

    def _retry(self, action: Callable[[Locator], Any]) -> Any:
        """执行 action；可自愈异常则愈完后用新选择器再执行一次。"""
        try:
            return action(self.raw)
        except Exception as exc:
            if not self._gateway.should_attempt_heal(exc, self._ctx):
                raise
            self._ctx.element = self._gateway.heal(self._ctx, exc)
            self._inner = None
            return action(self.raw)

    def click(self, **kwargs):
        """点击；失败时可自愈后重试。"""
        return self._retry(lambda loc: loc.click(**kwargs))

    def fill(self, value: str, **kwargs):
        """填充；失败时可自愈后重试。"""
        return self._retry(lambda loc: loc.fill(value, **kwargs))

    def type(self, text: str, **kwargs):
        """逐字输入；失败时可自愈后重试。"""
        return self._retry(lambda loc: loc.type(text, **kwargs))

    def press(self, key: str, **kwargs):
        """按键；失败时可自愈后重试。"""
        return self._retry(lambda loc: loc.press(key, **kwargs))

    def check(self, **kwargs):
        """勾选；失败时可自愈后重试。"""
        return self._retry(lambda loc: loc.check(**kwargs))

    def uncheck(self, **kwargs):
        """取消勾选；失败时可自愈后重试。"""
        return self._retry(lambda loc: loc.uncheck(**kwargs))

    def select_option(self, **kwargs):
        """下拉选择；失败时可自愈后重试。"""
        return self._retry(lambda loc: loc.select_option(**kwargs))

    def wait_for(self, **kwargs):
        """等待状态；失败时可自愈后重试。"""
        return self._retry(lambda loc: loc.wait_for(**kwargs))

    def scroll_into_view_if_needed(self, **kwargs):
        """滚入视口；失败时可自愈后重试。"""
        return self._retry(lambda loc: loc.scroll_into_view_if_needed(**kwargs))

    def inner_text(self, **kwargs) -> str:
        """读取 innerText；失败时可自愈后重试。"""
        return self._retry(lambda loc: loc.inner_text(**kwargs))

    def text_content(self, **kwargs) -> Optional[str]:
        """读取 textContent；失败时可自愈后重试。"""
        return self._retry(lambda loc: loc.text_content(**kwargs))

    def is_visible(self, **kwargs) -> bool:
        """是否可见；失败时可自愈后重试。"""
        return self._retry(lambda loc: loc.is_visible(**kwargs))

    def count(self) -> int:
        """匹配个数；失败时可自愈后重试。"""
        return self._retry(lambda loc: loc.count())

    def locator(self, selector: str) -> Locator:
        """子定位（原生 Locator，不再包一层自愈）。"""
        return self.raw.locator(selector)

    def filter(self, **kwargs) -> Locator:
        """过滤（原生 Locator）。"""
        return self.raw.filter(**kwargs)

    def evaluate(self, expression: str, **kwargs):
        """在元素上 evaluate；失败时可自愈后重试。"""
        return self._retry(lambda loc: loc.evaluate(expression, **kwargs))

    def __getattr__(self, item: str):
        """未显式包装的属性转发到原生 Locator。"""
        return getattr(self.raw, item)


class FrameHealingContext:
    """iframe 内定位上下文，支持嵌套 frame_locator。"""

    def __init__(
        self,
        page: Page,
        ctx_base: dict,
        iframe_key: str,
        *,
        parent_frame: Optional[FrameLocator] = None,
    ):
        self.page = page
        self.ctx_base = ctx_base
        self.iframe_key = iframe_key
        self.parent_frame = parent_frame
        self._frame: Optional[FrameLocator] = None

    @property
    def parent_keys(self):
        """从外到内的 iframe 键链，用于审计与 cache_key。"""
        keys = list(self.ctx_base.get("parent_keys", []))
        keys.append(self.iframe_key)
        return keys

    def _resolve_frame(self) -> FrameLocator:
        """解析并缓存当前 iframe FrameLocator。"""
        if self._frame is not None:
            return self._frame
        selector = get_element_from_pd(self.ctx_base["pd"], self.iframe_key).selector
        root = self.parent_frame if self.parent_frame is not None else self.page
        self._frame = root.frame_locator(selector).first
        return self._frame

    def locate(self, element_key: str) -> HealingLocator:
        """在当前 iframe 内按键定位。"""
        ctx = HealingContext(
            page=self.page,
            yaml_parts=self.ctx_base["yaml_parts"],
            pd=self.ctx_base["pd"],
            element_key=element_key,
            element=get_element_from_pd(self.ctx_base["pd"], element_key),
            root=self._resolve_frame(),
            parent_keys=self.parent_keys,
        )
        return HealingLocator(ctx, self.ctx_base["gateway"])

    def frame_locator(self, nested_iframe_key: str) -> "FrameHealingContext":
        """进入嵌套 iframe。"""
        return FrameHealingContext(
            self.page,
            {**self.ctx_base, "parent_keys": self.parent_keys},
            nested_iframe_key,
            parent_frame=self._resolve_frame(),
        )
