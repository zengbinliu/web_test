# -*- coding: utf-8 -*-
"""校验 LLM 返回的候选选择器。"""

from typing import List, Optional, Union

from playwright.sync_api import FrameLocator, Locator, Page

from page_ele.ui_healing.element_def import (
    ElementDef,
    infer_locator_type,
    locator_priority_rank,
    normalize_locator_type,
)
from page_ele.ui_healing.locator_adapter import locator_is_usable, to_playwright_locator


def pick_valid_candidate(
    root: Union[Page, FrameLocator, Locator],
    candidates: List[dict],
    *,
    max_candidates: int = 3,
) -> Optional[ElementDef]:
    """按定位优先级排序后试候选，返回第一个可用的；都失败返回 None。"""
    prepared = []
    for item in candidates:
        selector = str(item.get("selector", "")).strip()
        if not selector:
            continue
        locator_type = normalize_locator_type(
            str(item.get("locator_type") or infer_locator_type(selector)).strip()
        )
        prepared.append(
            (
                locator_priority_rank(locator_type),
                ElementDef(
                    key="_candidate",
                    selector=selector,
                    locator_type=locator_type,
                    semantic=str(item.get("reason", "")),
                ),
            )
        )

    prepared.sort(key=lambda pair: pair[0])
    for _, element in prepared[:max_candidates]:
        if locator_is_usable(to_playwright_locator(root, element)):
            return element
    return None
