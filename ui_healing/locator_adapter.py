# -*- coding: utf-8 -*-
"""将 YAML 选择器方言转换为 Playwright Locator。"""

import re
from typing import Union

from playwright.sync_api import FrameLocator, Locator, Page

from page_ele.ui_healing.element_def import ElementDef, normalize_locator_type, parse_role_selector


def _plain_value(selector: str, prefix: str) -> str:
    """去掉方言前缀与可选引号。"""
    value = selector[len(prefix) :].strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def _text_pattern(value: str):
    """用户可见文案：忽略大小写匹配。"""
    return re.compile(re.escape(value), re.I)


def to_playwright_locator(
    root: Union[Page, FrameLocator, Locator],
    element: ElementDef,
) -> Locator:
    """把 ElementDef 转为 Playwright Locator（按用户可见语义优先的方言）。"""
    selector = element.selector.strip()
    locator_type = normalize_locator_type(element.locator_type)

    if locator_type == "role" or selector.startswith("role="):
        role, name = parse_role_selector(selector)
        if name is not None:
            return root.get_by_role(role, name=_text_pattern(name))
        return root.get_by_role(role)

    if locator_type == "text" or selector.startswith("text="):
        return root.get_by_text(_plain_value(selector, "text="))

    if locator_type == "label" or selector.startswith("label="):
        return root.get_by_label(_text_pattern(_plain_value(selector, "label=")))

    if locator_type == "placeholder" or selector.startswith("placeholder="):
        return root.get_by_placeholder(_text_pattern(_plain_value(selector, "placeholder=")))

    if locator_type == "alt_text" or selector.startswith(("alt=", "alt_text=")):
        prefix = "alt_text=" if selector.startswith("alt_text=") else "alt="
        return root.get_by_alt_text(_text_pattern(_plain_value(selector, prefix)))

    if locator_type == "title" or selector.startswith("title="):
        return root.get_by_title(_text_pattern(_plain_value(selector, "title=")))

    if locator_type == "test_id" or selector.startswith(("testid=", "test_id=")):
        prefix = "test_id=" if selector.startswith("test_id=") else "testid="
        # Playwright 默认读 data-testid；可用 selectors.set_test_id_attribute 改属性名
        return root.get_by_test_id(_plain_value(selector, prefix))

    if locator_type == "xpath" or selector.startswith("xpath="):
        xpath = selector[6:] if selector.startswith("xpath=") else selector
        return root.locator(f"xpath={xpath}")

    return root.locator(selector)


def locator_is_usable(locator: Locator, *, require_visible: bool = True) -> bool:
    """候选探测：须恰好匹配 1 个（满足 Playwright strict），且（可选）可见；异常视为不可用。"""
    try:
        # 禁止 count>1：否则 fill/click 会报 strict mode violation，却仍被自愈落盘
        if locator.count() != 1:
            return False
        if require_visible:
            return locator.is_visible()
        return True
    except Exception:
        return False
