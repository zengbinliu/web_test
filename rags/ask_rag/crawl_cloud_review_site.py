from __future__ import annotations

import argparse
import base64
import json
import os
import pathlib
import re
import sys
import time
from collections import deque
from datetime import datetime
from typing import Any
from urllib.parse import urljoin, urlparse, urlunparse

import requests

ROOT = pathlib.Path(__file__).resolve().parent
OFFICIAL_SERVER_ROOT = pathlib.Path(
    r"d:\web_1151\05测试数据与脚本\自动化\official_website_server"
)
TESTCASES_PATH = ROOT / "data" / "testcases.jsonl"
SUPPLEMENTAL_PATH = ROOT / "data" / "supplemental_cases.json"
SITE_CRAWL_ROOT = ROOT / "data" / "site_crawl"

ALLOWED_HOSTS = {"cloud.reolink.review", "my.reolink.review", "apis.reolink.review"}
BASE_CASE_ID = 991000000
PAGE_CASE_ID_START = 991000001
API_CASE_ID_START = 991100000

KNOWN_SEED_PATHS = [
    "https://cloud.reolink.review/",
    "https://cloud.reolink.review/cloud-plan",
    "https://cloud.reolink.review/user/my-devices/",
    "https://cloud.reolink.review/user/cloud-library/",
    "https://cloud.reolink.review/user/subscribe-plan/sim/list",
    "https://cloud.reolink.review/terms-of-use/",
    "https://my.reolink.review/",
    "https://my.reolink.review/login/",
    "https://my.reolink.review/account/",
    "https://my.reolink.review/security/",
]

STATIC_EXT_RE = re.compile(
    r"\.(js|css|png|jpe?g|gif|svg|ico|woff2?|ttf|map|json|xml|pdf|zip|mp4|webm)(\?|$)",
    re.I,
)
REVIEW_URL_RE = re.compile(
    r"https?://(?:cloud|my|apis|r\d+\.cloud|www)\.reolink\.review[^\s\"'<>]*",
    re.I,
)
SPA_PATH_RE = re.compile(r'["\'](/(?:user|checkout|cloud-plan|app-free-plan|doorbell)[^"\']*)["\']')
LOGOUT_RE = re.compile(r"(logout|sign-out|signout|log-out)", re.I)
INVALID_PATH_RE = re.compile(r"[\n\r\u4e00-\u9fff（）]")
NUMERIC_SEGMENT_RE = re.compile(r"^\d{6,}$")
UID_SEGMENT_RE = re.compile(r"^[A-Za-z0-9]{10,}$")

sys.path.insert(0, str(OFFICIAL_SERVER_ROOT))


def configure_output() -> None:
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def load_llm_env() -> None:
    env_path = ROOT / "llm.env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and not os.environ.get(key):
            os.environ[key] = value


def normalize_url(url: str) -> str | None:
    url = (url or "").strip().split("\n")[0].split("\r")[0]
    if not url or url.startswith(("mailto:", "javascript:", "tel:", "#")):
        return None
    parsed = urlparse(url)
    if not parsed.scheme:
        return None
    if parsed.scheme not in ("http", "https"):
        return None
    host = (parsed.hostname or "").lower()
    if host not in ALLOWED_HOSTS:
        return None
    if host == "apis.reolink.review":
        return None
    path = parsed.path or "/"
    if INVALID_PATH_RE.search(path):
        return None
    if STATIC_EXT_RE.search(path):
        return None
    if LOGOUT_RE.search(path):
        return None
    cleaned = urlunparse((parsed.scheme, parsed.netloc, path, "", parsed.query, ""))
    return cleaned.rstrip("/") if path != "/" else cleaned


def canonical_path(path: str) -> str:
    parts = [p for p in (path or "/").split("/") if p]
    canonical_parts: list[str] = []
    for part in parts:
        if NUMERIC_SEGMENT_RE.match(part):
            canonical_parts.append("{id}")
        elif UID_SEGMENT_RE.match(part) and any(ch.isdigit() for ch in part):
            canonical_parts.append("{uid}")
        else:
            canonical_parts.append(part)
    return "/" + "/".join(canonical_parts) if canonical_parts else "/"


def canonical_route_key(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    return f"{host}{canonical_path(parsed.path or '/')}"


def route_key(url: str) -> str:
    return canonical_route_key(url)


def display_route_path(url: str) -> str:
    return canonical_path(urlparse(url).path or "/")


def is_404_page(dom_info: dict[str, Any]) -> bool:
    title = (dom_info.get("title") or "").strip().lower()
    if title.startswith("404") or " 404" in title or title.endswith("404"):
        return True
    headings = " ".join((dom_info.get("h1") or []) + (dom_info.get("h2") or [])).lower()
    if "404" in headings or "not found" in headings or "page not found" in headings:
        return True
    body_preview = (dom_info.get("body_text") or "")[:300].lower()
    if body_preview.startswith("404") or "page not found" in body_preview:
        return True
    return False


def path_slug(url: str) -> str:
    parsed = urlparse(url)
    slug = (parsed.hostname or "host").split(".")[0]
    path = (parsed.path or "/").strip("/").replace("/", "_") or "home"
    if len(path) > 120:
        path = path[:120]
    return f"{slug}_{path}"


def extract_seed_urls_from_testcases() -> list[str]:
    if not TESTCASES_PATH.exists():
        return []
    text = TESTCASES_PATH.read_text(encoding="utf-8", errors="replace")
    urls: set[str] = set()
    for match in REVIEW_URL_RE.findall(text):
        cleaned = (
            match.replace("&amp;", "&")
            .replace("&amp;amp;", "&")
            .split('"')[0]
            .split("'")[0]
            .split(" ")[0]
            .split("\n")[0]
            .split("\r")[0]
        )
        cleaned = re.sub(r"https?://(?:r\d+\.cloud|www)\.reolink\.review", "https://cloud.reolink.review", cleaned)
        normalized = normalize_url(cleaned)
        if normalized:
            urls.add(normalized)
    return sorted(urls)


def merge_seed_urls(extra: list[str] | None = None) -> list[str]:
    seeds: list[str] = []
    seen_urls: set[str] = set()
    seen_routes: set[str] = set()
    for url in KNOWN_SEED_PATHS + extract_seed_urls_from_testcases() + (extra or []):
        normalized = normalize_url(url)
        if not normalized or normalized in seen_urls:
            continue
        rkey = canonical_route_key(normalized)
        if rkey in seen_routes:
            continue
        seen_urls.add(normalized)
        seen_routes.add(rkey)
        seeds.append(normalized)
    return seeds


def extract_dom_info(page) -> dict[str, Any]:
    script = """
    () => {
      const visible = (el) => {
        if (!el) return false;
        const style = window.getComputedStyle(el);
        return style && style.visibility !== 'hidden' && style.display !== 'none';
      };
      const textList = (selector, limit=30) => {
        return Array.from(document.querySelectorAll(selector))
          .filter(visible)
          .map(el => (el.innerText || el.textContent || '').trim())
          .filter(Boolean)
          .slice(0, limit);
      };
      const links = Array.from(document.querySelectorAll('a[href]'))
        .filter(visible)
        .map(a => ({ text: (a.innerText || a.textContent || '').trim(), href: a.getAttribute('href') || '' }))
        .filter(x => x.href)
        .slice(0, 80);
      const meta = document.querySelector('meta[name="description"]');
      return {
        title: document.title || '',
        h1: textList('h1', 5),
        h2: textList('h2', 10),
        h3: textList('h3', 10),
        nav: textList('nav a, header a, [role="navigation"] a', 30),
        buttons: textList('button, [role="button"], input[type="submit"]', 30),
        labels: textList('label', 20),
        breadcrumbs: textList('[aria-label*="breadcrumb" i] *, .breadcrumb *, .breadcrumbs *', 15),
        meta_description: meta ? (meta.getAttribute('content') || '') : '',
        body_text: (document.body ? document.body.innerText : '').slice(0, 4000),
        links,
      };
    }
    """
    try:
        return page.evaluate(script)
    except Exception as exc:
        return {"title": page.title(), "error": str(exc), "links": []}


def dedupe_links_by_route(links: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for link in links:
        key = canonical_route_key(link)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(link)
    return deduped


def discover_links(page, current_url: str, dom_info: dict[str, Any]) -> list[str]:
    found: set[str] = set()
    for item in dom_info.get("links") or []:
        href = item.get("href") or ""
        absolute = urljoin(current_url, href)
        normalized = normalize_url(absolute)
        if normalized:
            found.add(normalized)
    try:
        html = page.content()
        for match in SPA_PATH_RE.findall(html):
            absolute = urljoin(current_url, match)
            normalized = normalize_url(absolute)
            if normalized:
                found.add(normalized)
    except Exception:
        pass
    return dedupe_links_by_route(sorted(found))


def dom_fallback_description(dom_info: dict[str, Any], url: str) -> dict[str, Any]:
    title = dom_info.get("title") or ""
    headings = dom_info.get("h1") or dom_info.get("h2") or []
    nav = dom_info.get("nav") or []
    buttons = dom_info.get("buttons") or []
    body_preview = (dom_info.get("body_text") or "").strip().replace("\n", " ")[:500]
    page_type = "未知页面"
    lower = f"{title} {url} {' '.join(headings)}".lower()
    if "dashboard" in lower or "/user/dashboard" in url:
        page_type = "Dashboard"
    elif "cloud-plan" in url or "cloud storage" in lower:
        page_type = "云套餐"
    elif "subscribe-plan/sim" in url or "cellular" in lower:
        page_type = "流量套餐"
    elif "cloud-library" in url or "library" in lower:
        page_type = "Library"
    elif "checkout" in url:
        page_type = "支付"
    elif "my-devices" in url:
        page_type = "My Devices"
    elif url.rstrip("/").endswith("cloud.reolink.review"):
        page_type = "首页"

    summary_parts = []
    if title:
        summary_parts.append(f"页面标题: {title}")
    if headings:
        summary_parts.append(f"主标题: {' | '.join(headings[:3])}")
    if nav:
        summary_parts.append(f"导航: {' | '.join(nav[:8])}")
    if body_preview:
        summary_parts.append(f"正文摘要: {body_preview}")

    return {
        "page_type": page_type,
        "visual_summary": "；".join(summary_parts) or f"页面 {url}",
        "key_ui_elements": ", ".join((headings[:5] + nav[:8] + buttons[:8])[:15]),
        "user_actions": ", ".join(buttons[:10]),
        "page_state": "需进一步确认",
        "vision_source": "dom_fallback",
    }


def describe_page_with_vision(screenshot_path: pathlib.Path, dom_info: dict[str, Any], url: str) -> dict[str, Any]:
    load_llm_env()
    crawl_key = os.environ.get("REOLINK_CRAWL_VISION_API_KEY", "").strip()
    crawl_base = os.environ.get("REOLINK_CRAWL_VISION_API_BASE", "").strip()
    crawl_model = os.environ.get("REOLINK_CRAWL_VISION_MODEL", "").strip()

    rag_key = os.environ.get("REOLINK_RAG_LLM_API_KEY", "").strip() or os.environ.get("OPENAI_API_KEY", "").strip()
    rag_base = (
        os.environ.get("REOLINK_RAG_LLM_API_BASE", "").strip()
        or os.environ.get("OPENAI_API_BASE", "").strip()
        or "https://api.openai.com/v1"
    ).rstrip("/")
    rag_model = os.environ.get("REOLINK_RAG_LLM_MODEL", "").strip() or "gpt-4o-mini"
    provider = os.environ.get("REOLINK_RAG_LLM_PROVIDER", "").strip().lower()

    if crawl_key:
        api_key = crawl_key
        api_base = (crawl_base or "https://api.openai.com/v1").rstrip("/")
        model = crawl_model or "gpt-4o-mini"
    elif provider == "cursor" or (rag_key and rag_key.startswith("crsr_")):
        return dom_fallback_description(dom_info, url)
    else:
        api_key = rag_key
        api_base = rag_base
        model = rag_model

    if not api_key or api_key.startswith("crsr_") or not screenshot_path.exists():
        return dom_fallback_description(dom_info, url)

    image_b64 = base64.b64encode(screenshot_path.read_bytes()).decode("ascii")
    title = dom_info.get("title") or ""
    prompt = (
        "你是 Reolink Cloud 测试服页面分析助手。请根据截图和 DOM 信息，用 JSON 回答，字段："
        "page_type, visual_summary, key_ui_elements, user_actions, page_state。"
        "全部使用中文。visual_summary 200-400字。"
        f"\nURL: {url}\nTitle: {title}\n"
        f"H1: {dom_info.get('h1')}\nNav: {dom_info.get('nav')[:10]}"
    )
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
                ],
            }
        ],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }
    try:
        resp = requests.post(
            f"{api_base}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=90,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        data = json.loads(content)
        data["vision_source"] = "openai_vision"
        return data
    except Exception:
        return dom_fallback_description(dom_info, url)


def infer_purpose(page_type: str, dom_info: dict[str, Any], url: str) -> str:
    title = dom_info.get("title") or ""
    mapping = {
        "Dashboard": "Cloud 用户控制台，查看订阅、设备与快捷入口",
        "云套餐": "云存储套餐展示与订阅入口",
        "流量套餐": "4G/SIM 流量套餐列表与购买入口",
        "Library": "云视频库 Event Library，管理上传录像",
        "支付": "Checkout 支付/切换/续费结算页",
        "My Devices": "我的设备列表，查看绑定设备与套餐关联",
        "首页": "Cloud 官网首页与产品介绍",
    }
    if page_type in mapping:
        return mapping[page_type]
    if "terms" in url:
        return "服务条款/隐私政策页面"
    if "my.reolink.review" in url:
        return "账户中心相关页面"
    return title or f"Cloud 测试服页面: {urlparse(url).path}"


def is_logged_in(page) -> bool:
    try:
        if page.locator('role=button[name="Log in"]').count() == 0:
            body = (page.locator("body").inner_text(timeout=3000) or "").lower()
            markers = ("dashboard", "my cloud", "my devices", "cloud library", "log out", "sign out", "退出")
            if any(m in body for m in markers):
                return True
        return page.locator('a[href*="/user/"]').count() > 0 and page.locator('role=button[name="Log in"]').count() == 0
    except Exception:
        return False


def fetch_mailproxy_code(email_account: str, target_email: str) -> str:
    from src.cloud.services.verify_code_service import get_verify_code_by_back

    os.chdir(OFFICIAL_SERVER_ROOT)
    try:
        return get_verify_code_by_back(email_account, target_email)
    finally:
        os.chdir(ROOT)


def login_cloud(
    session,
    account: str,
    passwd: str,
    email_account: str,
    email_passwd: str = "",
    get_code_type: str = "",
) -> None:
    import time

    from configs.cloud_payment_config import CLOUD_LOGIN_RATE_LIMIT_WAIT_S, CLOUD_LOGIN_URL, CLOUD_PAY_LOGIN_COOKIES
    from src.cloud.ui_flows.common.verify_code_providers import resolve_verify_code_provider
    from src.cloud.ui_pages.front.cloud_login_page import CloudLoginPage

    code_type = get_code_type
    if not code_type and email_passwd:
        code_type = ""  # IMAP
    elif not code_type:
        code_type = "back"

    os.chdir(OFFICIAL_SERVER_ROOT)
    try:
        session.add_cookies(CLOUD_PAY_LOGIN_COOKIES)
        if not session.page:
            session.new_page()
        page = session.page

        if is_logged_in(page):
            print("[login] 检测到已登录，跳过登录流程")
            return

        login_page = CloudLoginPage(page)
        provider = resolve_verify_code_provider(code_type)
        provider_name = "IMAP" if not code_type else "MailProxy"
        print(f"[login] 打开 Cloud 登录页: {CLOUD_LOGIN_URL}")
        login_page.open_cloud_home(CLOUD_LOGIN_URL)
        page.wait_for_timeout(2000)
        if is_logged_in(page):
            print("[login] 检测到已登录，跳过登录流程")
            return

        login_page.click_log_in_entry()
        print(f"[login] 输入账号: {account}")
        login_page.fill_email(account)
        login_page.fill_password(passwd)
        login_page.click_login_submit()
        page.wait_for_timeout(3000)

        if is_logged_in(page):
            print("[login] 提交账密后已登录，无需 2FA")
            return

        from src.cloud.page_ele import load_page_yaml

        _pd = load_page_yaml("front", "login_signup_page.yml")
        send_code = page.locator(_pd["send_code_button"])
        verify_btn = page.locator(_pd["verify_button"])

        for attempt in range(3):
            try:
                if is_logged_in(page):
                    print("[login] 检测到已登录")
                    return

                if send_code.count() and send_code.first.is_visible():
                    print("[login] 点击 Send Code")
                    send_code.first.click()
                    page.wait_for_timeout(2000)
                elif verify_btn.count() and verify_btn.first.is_visible():
                    print("[login] 已在验证码页")
                else:
                    page.wait_for_timeout(5000)
                    if is_logged_in(page):
                        print("[login] 等待后检测到已登录")
                        return
                    if attempt < 2:
                        wait_s = CLOUD_LOGIN_RATE_LIMIT_WAIT_S if attempt else 10
                        print(f"[login] 未出现 2FA 页面，等待 {wait_s}s 后重试")
                        time.sleep(wait_s)
                        continue
                    raise RuntimeError("登录后未进入 2FA 或已登录状态")

                if attempt > 0:
                    try:
                        login_page.click_resend_code()
                        print("[login] 点击 Resend Code")
                        page.wait_for_timeout(3000)
                    except Exception:
                        pass

                login_page.wait_verify_visible(timeout=10000)
                print(f"[login] 获取邮箱验证码 ({provider_name})")
                email_code = provider.get_code(email_account, account, email_passwd)
                print(f"[login] 输入验证码并 Verify")
                login_page.fill_email_code(email_code)
                login_page.click_verify()

                for _ in range(15):
                    page.wait_for_timeout(1000)
                    if is_logged_in(page):
                        print("[login] Cloud 登录完成")
                        return

                print("[login] 验证后仍未登录，准备重试")
            except Exception as exc:
                if is_logged_in(page):
                    print("[login] 登录流程异常但页面已登录，继续爬取")
                    return
                if attempt < 2:
                    print(f"[login] 2FA 异常: {exc}，等待 {CLOUD_LOGIN_RATE_LIMIT_WAIT_S}s 后重试")
                    time.sleep(CLOUD_LOGIN_RATE_LIMIT_WAIT_S)
                    continue
                raise
    finally:
        os.chdir(ROOT)

    if not is_logged_in(session.page):
        body_preview = ""
        try:
            body_preview = (session.page.locator("body").inner_text(timeout=3000) or "")[:500]
        except Exception:
            pass
        raise RuntimeError(f"Cloud 登录失败，未能进入已登录状态。页面摘要: {body_preview}")
    print("[login] Cloud 登录完成")


def crawl_site(
    account: str,
    passwd: str,
    email_account: str,
    email_passwd: str,
    run_id: str,
    max_pages: int,
    max_depth: int,
    headless: bool,
    use_proxy: bool,
    use_vision: bool,
    extra_seeds: list[str] | None = None,
) -> dict[str, Any]:
    from src.cloud.browser.session import BrowserSession

    run_dir = SITE_CRAWL_ROOT / run_id
    screenshot_dir = run_dir / "screenshots"
    screenshot_dir.mkdir(parents=True, exist_ok=True)

    proxy = {"server": "127.0.0.1:10809"} if use_proxy else None
    session = BrowserSession(headless=headless, proxy=proxy)
    session.open()
    session.new_page()
    page = session.page

    api_hits: dict[str, dict[str, Any]] = {}

    def on_request(request):
        try:
            req_url = request.url
            parsed = urlparse(req_url)
            if parsed.hostname != "apis.reolink.review":
                return
            key = f"{request.method} {parsed.path}"
            entry = api_hits.setdefault(
                key,
                {
                    "method": request.method,
                    "path": parsed.path,
                    "sample_url": req_url,
                    "trigger_pages": set(),
                    "count": 0,
                },
            )
            entry["count"] += 1
            if page.url:
                entry["trigger_pages"].add(page.url)
        except Exception:
            pass

    page.on("request", on_request)

    print("[crawl] 开始登录...")
    login_cloud(session, account, passwd, email_account, email_passwd)
    print("[crawl] 登录完成")

    seeds = merge_seed_urls(extra_seeds)
    queue: deque[tuple[str, int, str | None]] = deque((url, 0, None) for url in seeds)
    visited_routes: set[str] = set()
    pages: list[dict[str, Any]] = []
    route_map: dict[str, dict[str, Any]] = {}

    while queue and len(pages) < max_pages:
        url, depth, parent_url = queue.popleft()
        rkey = canonical_route_key(url)
        if rkey in visited_routes:
            continue
        visited_routes.add(rkey)

        print(f"[crawl] ({len(pages)+1}/{max_pages}) depth={depth} {url}")
        apis_before = set(api_hits.keys())
        dom_info: dict[str, Any] = {}
        error = ""
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(2000)
            dom_info = extract_dom_info(page)
        except Exception as exc:
            error = str(exc)
            dom_info = {"title": "", "links": [], "error": error}

        if not error and is_404_page(dom_info):
            print(f"[crawl] 跳过 404: {url}")
            continue

        shot_name = f"{path_slug(url)}.png"
        shot_path: pathlib.Path | None = screenshot_dir / shot_name
        try:
            page.screenshot(path=str(shot_path), full_page=True)
        except Exception as exc:
            shot_path = None
            error = error or str(exc)

        vision = dom_fallback_description(dom_info, url)
        if use_vision and shot_path and shot_path.exists():
            vision = describe_page_with_vision(shot_path, dom_info, url)

        child_links = discover_links(page, url, dom_info) if not error else []
        new_apis = [api_hits[k] for k in api_hits.keys() if k not in apis_before]

        page_record = {
            "url": url,
            "route_key": rkey,
            "route_path": display_route_path(url),
            "depth": depth,
            "parent_url": parent_url,
            "title": dom_info.get("title") or "",
            "dom": dom_info,
            "vision": vision,
            "purpose": infer_purpose(vision.get("page_type", ""), dom_info, url),
            "child_links": child_links,
            "apis": [
                {
                    "method": item["method"],
                    "path": item["path"],
                    "sample_url": item["sample_url"],
                }
                for item in new_apis
            ],
            "screenshot": str(shot_path.relative_to(ROOT)).replace("\\", "/") if shot_path and shot_path.exists() else "",
            "error": error,
            "crawled_at": datetime.now().isoformat(timespec="seconds"),
        }
        pages.append(page_record)

        existing = route_map.get(rkey)
        if existing:
            existing.setdefault("variants", []).append({"url": url, "query": urlparse(url).query})
        else:
            route_map[rkey] = {
                "route_key": rkey,
                "route_path": display_route_path(url),
                "url": url,
                "title": page_record["title"],
                "purpose": page_record["purpose"],
                "page_type": vision.get("page_type", ""),
                "parent_routes": [route_key(parent_url)] if parent_url else [],
                "child_links": child_links,
                "apis": page_record["apis"],
                "screenshot": page_record["screenshot"],
                "visual_summary": vision.get("visual_summary", ""),
            }

        if depth < max_depth and not error:
            for link in child_links:
                if canonical_route_key(link) not in visited_routes:
                    queue.append((link, depth + 1, url))

    session.close()

    for entry in api_hits.values():
        entry["trigger_pages"] = sorted(entry["trigger_pages"])

    pages_path = run_dir / "pages.jsonl"
    with pages_path.open("w", encoding="utf-8") as fh:
        for item in pages:
            fh.write(json.dumps(item, ensure_ascii=False) + "\n")

    site_map_path = run_dir / "site_map.json"
    site_map_path.write_text(
        json.dumps(list(route_map.values()), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    api_catalog_path = run_dir / "api_catalog.json"
    api_catalog_path.write_text(
        json.dumps(list(api_hits.values()), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    manifest = {
        "run_id": run_id,
        "account": account,
        "pages_total": len(pages),
        "routes_total": len(route_map),
        "apis_total": len(api_hits),
        "seeds_total": len(seeds),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "run_dir": run_dir,
        "pages": pages,
        "route_map": route_map,
        "api_hits": api_hits,
        "manifest": manifest,
    }


def module_path_for_route(rkey: str, page_type: str) -> str:
    host = rkey.split("/", 1)[0]
    if "my.reolink.review" in host:
        return f"补充知识 / 测试服站点 / my.reolink.review / {page_type or '页面'}"
    return f"补充知识 / 测试服站点 / cloud.reolink.review / {page_type or '页面'}"


def page_to_supplemental_case(case_id: int, route_entry: dict[str, Any], run_id: str) -> dict[str, Any]:
    url = route_entry.get("url") or ""
    path = route_entry.get("route_path") or display_route_path(url)
    vision_summary = route_entry.get("visual_summary") or ""
    child_links = route_entry.get("child_links") or []
    apis = route_entry.get("apis") or []
    page_type = route_entry.get("page_type") or "页面"
    title = route_entry.get("title") or page_type
    purpose = route_entry.get("purpose") or ""

    api_text = ", ".join(f"{a.get('method')} apis.reolink.review{a.get('path')}" for a in apis[:20])
    child_text = ", ".join(display_route_path(x) for x in child_links[:25])

    return {
        "case_id": case_id,
        "title": f"【站点知识】{title} ({path})",
        "link": url,
        "module_path_text": module_path_for_route(route_entry.get("route_key", ""), page_type),
        "precondition": (
            f"环境: cloud.reolink.review 测试服; 采集批次: {run_id}; "
            f"截图: {route_entry.get('screenshot', '')}"
        ),
        "keywords": f"{page_type} {path} {title} 路由 URL 测试服 cloud.reolink.review",
        "steps": [
            {"index": 1, "desc": "路由路径", "expect": path},
            {"index": 2, "desc": "示例 URL", "expect": url},
            {"index": 3, "desc": "页面作用", "expect": purpose},
            {"index": 4, "desc": "页面类型", "expect": page_type},
            {"index": 5, "desc": "视觉识别摘要", "expect": vision_summary},
            {"index": 6, "desc": "站内出站链接", "expect": child_text or "无"},
            {"index": 7, "desc": "关联 API", "expect": api_text or "无"},
        ],
    }


def build_overview_case(route_map: dict[str, dict[str, Any]], run_id: str) -> dict[str, Any]:
    lines = []
    for rkey in sorted(route_map.keys()):
        entry = route_map[rkey]
        path = entry.get("route_path") or display_route_path(entry.get("url", ""))
        lines.append(f"{path} | {entry.get('page_type','')} | {entry.get('purpose','')}")
    body = "\n".join(lines)
    return {
        "case_id": BASE_CASE_ID,
        "title": "【站点知识】Cloud 测试服全站路由总览",
        "link": "https://cloud.reolink.review/",
        "module_path_text": "补充知识 / 测试服站点 / 路由总览",
        "precondition": f"环境: cloud.reolink.review 测试服; 采集批次: {run_id}",
        "keywords": "路由 总览 sitemap cloud.reolink.review my.reolink.review 测试服 路径",
        "steps": [
            {"index": 1, "desc": "路由清单", "expect": body[:8000]},
            {"index": 2, "desc": "路由数量", "expect": str(len(route_map))},
        ],
    }


def build_api_cases(api_hits: dict[str, dict[str, Any]], run_id: str) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in api_hits.values():
        path = item.get("path") or "/"
        prefix = "/".join(path.split("/")[:3]) or path
        groups.setdefault(prefix, []).append(item)

    cases = []
    for idx, (prefix, items) in enumerate(sorted(groups.items())):
        lines = []
        for item in sorted(items, key=lambda x: x.get("path", "")):
            triggers = ", ".join(list(item.get("trigger_pages") or [])[:3])
            lines.append(
                f"{item.get('method')} {item.get('path')} (触发页面: {triggers or '未知'})"
            )
        cases.append(
            {
                "case_id": API_CASE_ID_START + idx,
                "title": f"【站点知识】API 分组 {prefix}",
                "link": f"https://apis.reolink.review{prefix}",
                "module_path_text": f"补充知识 / 测试服站点 / apis.reolink.review / {prefix}",
                "precondition": f"环境: apis.reolink.review 测试服; 采集批次: {run_id}",
                "keywords": f"API {prefix} apis.reolink.review 接口",
                "steps": [
                    {"index": 1, "desc": "接口清单", "expect": "\n".join(lines)[:8000]},
                    {"index": 2, "desc": "接口数量", "expect": str(len(items))},
                ],
            }
        )
    return cases


def write_corpus_markdown(route_map: dict[str, dict[str, Any]], run_id: str) -> pathlib.Path:
    out_path = ROOT / "corpus" / "site-cloud-review-map.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    groups: dict[str, list[dict[str, Any]]] = {}
    for entry in route_map.values():
        page_type = entry.get("page_type") or "其他"
        groups.setdefault(page_type, []).append(entry)

    lines = [
        "# Cloud 测试服站点路由地图",
        "",
        f"- 采集批次: `{run_id}`",
        f"- 生成时间: {datetime.now().isoformat(timespec='seconds')}",
        f"- 路由总数: {len(route_map)}",
        "",
    ]
    for page_type in sorted(groups.keys()):
        lines.append(f"## {page_type}")
        lines.append("")
        for entry in sorted(groups[page_type], key=lambda x: x.get("route_key", "")):
            path = entry.get("route_path") or display_route_path(entry.get("url", ""))
            lines.append(f"- `{path}` — {entry.get('purpose', '')}")
            if entry.get("visual_summary"):
                lines.append(f"  - {entry['visual_summary'][:200]}")
        lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


def is_site_knowledge_case(item: dict[str, Any]) -> bool:
    case_id = int(item.get("case_id") or 0)
    if case_id >= BASE_CASE_ID:
        return True
    title = item.get("title") or ""
    if title.startswith("【站点知识】"):
        return True
    module = item.get("module_path_text") or ""
    return "测试服站点" in module


def export_supplemental(
    route_map: dict[str, dict[str, Any]],
    api_hits: dict[str, dict[str, Any]],
    run_id: str,
    merge: bool = False,
) -> pathlib.Path:
    cases: list[dict[str, Any]] = [build_overview_case(route_map, run_id)]
    next_id = PAGE_CASE_ID_START
    for rkey in sorted(route_map.keys()):
        cases.append(page_to_supplemental_case(next_id, route_map[rkey], run_id))
        next_id += 1
    cases.extend(build_api_cases(api_hits, run_id))

    if merge and SUPPLEMENTAL_PATH.exists():
        existing = json.loads(SUPPLEMENTAL_PATH.read_text(encoding="utf-8"))
        if not isinstance(existing, list):
            existing = []
        preserved = [item for item in existing if not is_site_knowledge_case(item)]
        merged: dict[int, dict[str, Any]] = {item["case_id"]: item for item in preserved}
        for case in cases:
            merged[case["case_id"]] = case
        cases = sorted(merged.values(), key=lambda x: x.get("case_id", 0))

    SUPPLEMENTAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    SUPPLEMENTAL_PATH.write_text(json.dumps(cases, ensure_ascii=False, indent=2), encoding="utf-8")
    return SUPPLEMENTAL_PATH


def rebuild_rag_index() -> None:
    from build_rag_index import build_index

    build_index(rebuild=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="遍历 cloud.reolink.review 测试服并补充 askreolink 知识库。")
    parser.add_argument("--account", default="liuzb@reolink.com.cn")
    parser.add_argument("--passwd", default="bc123456.")
    parser.add_argument("--email-account", default="", help="取码邮箱账号，默认与 account 相同")
    parser.add_argument("--email-passwd", default="", help="IMAP 邮箱密码；提供时优先走 IMAP 取码")
    parser.add_argument("--run-id", default=datetime.now().strftime("%Y%m%d_%H%M%S"))
    parser.add_argument("--max-pages", type=int, default=200)
    parser.add_argument("--max-depth", type=int, default=4)
    parser.add_argument("--headless", action="store_true", default=False)
    parser.add_argument("--headed", action="store_true", help="显示浏览器窗口（默认已显示）")
    parser.add_argument("--no-proxy", action="store_true")
    parser.add_argument("--no-vision", action="store_true", help="跳过 vision，仅 DOM 描述")
    parser.add_argument("--merge", action="store_true", help="与已有 supplemental_cases.json 按 URL 合并")
    parser.add_argument("--rebuild-index", action="store_true")
    parser.add_argument("--export-only", help="仅从已有 run 目录导出 supplemental，不重新爬取")
    return parser.parse_args()


def export_only_from_run(run_id: str, merge: bool, rebuild_index: bool) -> int:
    run_dir = SITE_CRAWL_ROOT / run_id
    site_map_path = run_dir / "site_map.json"
    api_catalog_path = run_dir / "api_catalog.json"
    if not site_map_path.exists():
        print(f"未找到 {site_map_path}")
        return 1
    route_map = {item["route_key"]: item for item in json.loads(site_map_path.read_text(encoding="utf-8"))}
    api_hits = {}
    if api_catalog_path.exists():
        for item in json.loads(api_catalog_path.read_text(encoding="utf-8")):
            api_hits[f"{item.get('method')} {item.get('path')}"] = item
    export_supplemental(route_map, api_hits, run_id, merge=merge)
    write_corpus_markdown(route_map, run_id)
    if rebuild_index:
        rebuild_rag_index()
    print(f"已从 {run_id} 导出 supplemental: {SUPPLEMENTAL_PATH}")
    return 0


def main() -> int:
    configure_output()
    load_llm_env()
    args = parse_args()
    email_account = args.email_account or args.account
    headless = True if args.headless else False

    if args.export_only:
        return export_only_from_run(args.export_only, args.merge, args.rebuild_index)

    result = crawl_site(
        account=args.account,
        passwd=args.passwd,
        email_account=email_account,
        email_passwd=args.email_passwd,
        run_id=args.run_id,
        max_pages=args.max_pages,
        max_depth=args.max_depth,
        headless=headless,
        use_proxy=not args.no_proxy,
        use_vision=not args.no_vision,
    )

    export_supplemental(result["route_map"], result["api_hits"], args.run_id, merge=args.merge)
    corpus_path = write_corpus_markdown(result["route_map"], args.run_id)

    print(
        f"爬取完成: pages={result['manifest']['pages_total']} "
        f"routes={result['manifest']['routes_total']} apis={result['manifest']['apis_total']}"
    )
    print(f"输出目录: {result['run_dir']}")
    print(f"supplemental: {SUPPLEMENTAL_PATH}")
    print(f"corpus: {corpus_path}")

    if args.rebuild_index:
        print("重建 RAG 索引...")
        rebuild_rag_index()
        print("RAG 索引重建完成")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
