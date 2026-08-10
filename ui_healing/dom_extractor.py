# -*- coding: utf-8 -*-
"""页面 DOM 提取、脱敏与压缩。"""

import re
from typing import Optional, Union

from playwright.sync_api import FrameLocator, Locator, Page

from utils.logger import get_logger

logger = get_logger(__name__)

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_CARD_RE = re.compile(r"\b\d{13,19}\b")
_TOKEN_RE = re.compile(r"(token|password|secret|api[_-]?key)\s*[:=]\s*['\"]?[^'\"\s>]+", re.I)


def _sanitize_text(text: str) -> str:
    """脱敏邮箱、卡号、token 等敏感片段。"""
    text = _EMAIL_RE.sub("***@***.***", text)
    text = _CARD_RE.sub("****", text)
    text = _TOKEN_RE.sub(r"\1=***", text)
    return text


def _strip_noise(html: str) -> str:
    """去掉 script/style/注释及部分噪声属性。"""
    html = re.sub(r"<script[\s\S]*?</script>", "", html, flags=re.I)
    html = re.sub(r"<style[\s\S]*?</style>", "", html, flags=re.I)
    html = re.sub(r"<!--[\s\S]*?-->", "", html)
    html = re.sub(r'\s(?:style|onclick|onload)="[^"]*"', "", html, flags=re.I)
    html = re.sub(r"\s{2,}", " ", html)
    return html.strip()


def _truncate(html: str, max_chars: int) -> str:
    """超长则保留头尾，中间插入截断标记。"""
    if len(html) <= max_chars:
        return html
    head = max_chars // 2
    tail = max_chars - head - 32
    return f"{html[:head]}\n<!-- ... truncated ... -->\n{html[-tail:]}"


def _read_root_html(page: Page, root: Optional[Union[Page, FrameLocator, Locator]]) -> str:
    """按 root 类型取 HTML；Frame 取 body，失败由上层回退。"""
    if root is None or root is page:
        return page.content()
    if isinstance(root, Locator):
        return root.first.evaluate("el => el ? el.outerHTML : document.documentElement.outerHTML")
    # FrameLocator：取 frame 内 body
    html = root.locator("body").first.evaluate(
        "el => el ? el.outerHTML : ''",
        timeout=5000,
    )
    return html or page.content()


def extract_dom(
    page: Page,
    *,
    root: Optional[Union[Page, FrameLocator, Locator]] = None,
    max_chars: int = 24000,
) -> str:
    """提取并压缩 DOM，供 LLM 输入。"""
    try:
        html = _read_root_html(page, root)
    except Exception as exc:
        logger.warning("按 root 提取 DOM 失败，回退 page.content(): %s", exc)
        html = page.content()

    html = _strip_noise(html)
    html = _sanitize_text(html)
    return _truncate(html, max_chars)


def build_metadata(page: Page, *, error_message: str = "") -> dict:
    """页面 URL/标题/视口与错误摘要，附在 LLM payload 上。"""
    viewport = page.viewport_size or {"width": 0, "height": 0}
    return {
        "page_url": page.url,
        "page_title": page.title(),
        "error_message": error_message[:2000],
        "viewport": viewport,
    }
