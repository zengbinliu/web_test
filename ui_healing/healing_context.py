# -*- coding: utf-8 -*-
"""自愈运行时上下文。"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple, Union

from playwright.sync_api import FrameLocator, Locator, Page

from page_ele.ui_healing.element_def import ElementDef


@dataclass
class HealingContext:
    """一次定位/自愈所需的页面、YAML、元素与 root 信息。"""

    page: Page
    yaml_parts: Tuple[str, ...]
    pd: Dict[str, Any]
    element_key: str
    element: ElementDef
    root: Union[Page, FrameLocator, Locator]
    parent_keys: List[str] = field(default_factory=list)

    @property
    def yaml_file(self) -> str:
        """YAML 相对路径，用于日志与审计。"""
        return "/".join(self.yaml_parts)

    @property
    def cache_key(self) -> str:
        """同一运行内「只愈一次」的去重键。"""
        parents = ",".join(self.parent_keys) if self.parent_keys else "page"
        return f"{self.yaml_file}::{parents}::{self.element_key}"
