# -*- coding: utf-8 -*-
"""解析 page_ele YAML 中的元素定义。"""

import re
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple, Union

_CONFIG_SUFFIXES = (
    "_ms",
    "_s",
    "_url",
    "_timeout",
    "_retries",
    "_attempts",
    "_px",
    "_offset",
    "_interval",
    "_fragment",
    "_label",
    "_pattern",
    "_patterns",
    "_data",
    "_btn_patterns",
    "_button_patterns",
)

_CONFIG_EXACT_KEYS = {
    "dashboard_url",
    "cloud_home_url",
    "my_payment_url",
    "my_devices_url",
    "payment_history_url",
    "page_settle_ms",
    "page_load_wait_ms",
    "api_wait_timeout_ms",
    "payment_success_text",
}

# 自愈推荐/校验优先级（数字越小越优先）
# 1 role → 2 用户可见语义 → 3 test_id → 4 css/xpath
LOCATOR_TYPE_PRIORITY = {
    "role": 1,
    "text": 2,
    "label": 2,
    "placeholder": 2,
    "alt_text": 2,
    "title": 2,
    "test_id": 3,
    "css": 4,
    "xpath": 5,
}

_LOCATOR_TYPE_ALIASES = {
    "alt": "alt_text",
    "testid": "test_id",
    "test-id": "test_id",
}

# 显式方言前缀 → locator_type（顺序无关，最长匹配靠更具体前缀排前）
_EXPLICIT_PREFIXES = (
    ("placeholder=", "placeholder"),
    ("alt_text=", "alt_text"),
    ("test_id=", "test_id"),
    ("testid=", "test_id"),
    ("label=", "label"),
    ("title=", "title"),
    ("alt=", "alt_text"),
    ("role=", "role"),
    ("text=", "text"),
    ("xpath=", "xpath"),
)

LOCATOR_PRIORITY_HINT = (
    "硬性约束：选择器必须在页面上唯一命中目标元素（Playwright strict）；"
    "若 get_by_系列 会匹配多个同文案节点，必须改用唯一 id/CSS（如 #password），不要选歧义语义定位。\n"
    "1) get_by_role（用户如何看见/操作控件，优先带 accessible name）\n"
    "2) get_by_text / get_by_label / get_by_placeholder / get_by_alt_text / get_by_title\n"
    "3) get_by_test_id（测试契约；默认属性 data-testid，非用户可见语义）\n"
    "4) CSS / XPath（最后手段；语义定位不唯一时优先用唯一 id）"
)


@dataclass
class ElementDef:
    """单个可定位元素：选择器 + 语义 + 类型 + 可选父 scope。"""

    key: str
    selector: str
    semantic: str = ""
    locator_type: str = "css"
    scope: Optional[str] = None


def normalize_locator_type(locator_type: str) -> str:
    """统一别名（alt/testid 等）到标准 locator_type。"""
    raw = (locator_type or "css").strip().lower()
    return _LOCATOR_TYPE_ALIASES.get(raw, raw)


def locator_priority_rank(locator_type: str) -> int:
    """返回定位类型优先级排名（越小越优先）。"""
    return LOCATOR_TYPE_PRIORITY.get(normalize_locator_type(locator_type), 4)


def infer_locator_type(selector: str) -> str:
    """根据选择器前缀推断 locator_type。"""
    stripped = selector.strip()
    for prefix, loc_type in _EXPLICIT_PREFIXES:
        if stripped.startswith(prefix):
            return loc_type
    return "css"


def is_locator_element(key: str, value: Any) -> bool:
    """是否为可自愈定位项（排除超时/URL 等配置；显式方言前缀即使键名像配置也算元素）。"""
    if key in _CONFIG_EXACT_KEYS:
        return False
    if isinstance(value, dict):
        return "selector" in value
    if not isinstance(value, str):
        return False

    stripped = value.strip()
    if not stripped:
        return False
    if any(stripped.startswith(prefix) for prefix, _ in _EXPLICIT_PREFIXES):
        return True
    if any(key.endswith(suffix) for suffix in _CONFIG_SUFFIXES):
        return False
    return True


def parse_element_def(key: str, value: Any) -> ElementDef:
    """把 YAML 值解析为 ElementDef；无 semantic 时用键名空格化兜底。"""
    if isinstance(value, dict):
        selector = str(value.get("selector", "")).strip()
        semantic = str(value.get("semantic", "")).strip()
        locator_type = normalize_locator_type(
            str(value.get("locator_type", infer_locator_type(selector))).strip()
        )
        scope = value.get("scope")
        return ElementDef(
            key=key,
            selector=selector,
            semantic=semantic or key.replace("_", " "),
            locator_type=locator_type or "css",
            scope=str(scope) if scope else None,
        )
    selector = str(value).strip()
    return ElementDef(
        key=key,
        selector=selector,
        semantic=key.replace("_", " "),
        locator_type=infer_locator_type(selector),
    )


def get_element_from_pd(pd: Dict[str, Any], key: str) -> ElementDef:
    """从已加载的 page_ele dict 取元素；非定位键抛 ValueError。"""
    if key not in pd:
        raise KeyError(f"page_ele 中不存在元素键: {key}")
    value = pd[key]
    if not is_locator_element(key, value):
        raise ValueError(f"键 {key} 不是元素定位项，请直接使用 _pd['{key}']")
    return parse_element_def(key, value)


def format_selector_for_yaml(element: ElementDef, *, as_structured: bool = False) -> Union[str, dict]:
    """写回 YAML 时的值形态：纯字符串或结构化 dict。"""
    if as_structured or element.semantic or element.scope:
        payload = {"selector": element.selector, "locator_type": element.locator_type}
        if element.semantic:
            payload["semantic"] = element.semantic
        if element.scope:
            payload["scope"] = element.scope
        return payload
    return element.selector


_ROLE_RE = re.compile(
    r"""^role=(?P<role>[a-zA-Z]+)(?:\[name=(?P<quote>['"])(?P<name>.*?)(?P=quote)\])?$"""
)


def parse_role_selector(selector: str) -> Tuple[str, Optional[str]]:
    """解析 role=button[name='...'] 方言。"""
    match = _ROLE_RE.match(selector.strip())
    if not match:
        raise ValueError(f"无法解析 role 选择器: {selector}")
    return match.group("role"), match.group("name")
