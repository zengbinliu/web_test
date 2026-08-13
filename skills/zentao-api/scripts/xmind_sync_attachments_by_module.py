# -*- coding: utf-8 -*-
"""
从 XMind（Zen 格式 content.json）提取带「样式图」的节点，与禅道某模块下用例标题做模糊匹配，
再通过网页 **file/ajaxUpload + imgFile**（与 upload_testcase_via_edit_form.py 一致）把 PNG 关联到对应用例。

环境变量（与 zentao-api 其他脚本一致）：
  ZENTAO_URL（默认 https://pms.reolink.com.cn）
  ZENTAO_ACCOUNT、ZENTAO_PASSWORD
  ZENTAO_WEB_COOKIE（整段 Cookie，与浏览器一致）
  可选 XMIND_PATH：.xmind 绝对路径；未设则在桌面 **/2026云服务/** 下按 glob 找 *_v2.xmind

用法：
  python xmind_sync_attachments_by_module.py 387 20810
  python xmind_sync_attachments_by_module.py 387 20810 --dry-run

说明：
  - 匹配采用 difflib + 章节号重叠加分，**非 100% 准确**；`--dry-run` 可先看映射表。
  - 已关联到用例且 **文件名与本次提取的 resources 哈希名一致** 的会跳过，避免重复上传。
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
import tempfile
import zipfile
from difflib import SequenceMatcher
from pathlib import Path

import requests

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def api_token(base: str, account: str, password: str) -> str:
    r = requests.post(
        f"{base}/api.php/v1/tokens",
        json={"account": account, "password": password},
        timeout=60,
    )
    r.raise_for_status()
    t = r.json().get("token")
    if not t:
        raise RuntimeError("取 token 失败")
    return str(t)


def list_cases_module(base: str, token: str, product: int, module: int) -> list[dict]:
    out: list[dict] = []
    page = 1
    while True:
        r = requests.get(
            f"{base}/api.php/v1/products/{product}/testcases",
            headers={"Token": token},
            params={"module": module, "limit": 100, "page": page},
            timeout=60,
        )
        r.raise_for_status()
        j = r.json()
        chunk = j.get("testcases") or j.get("cases") or []
        if isinstance(chunk, dict):
            chunk = list(chunk.values())
        if not chunk:
            break
        out.extend(chunk)
        if len(chunk) < 100:
            break
        page += 1
        if page > 80:
            break
    return out


def fetch_case_detail(base: str, token: str, case_id: int) -> dict:
    r = requests.get(
        f"{base}/api.php/v1/testcases/{case_id}",
        headers={"Token": token},
        timeout=60,
    )
    r.raise_for_status()
    return r.json()


def fetch_form_uid(sess: requests.Session, base: str, case_id: int) -> str | None:
    url = f"{base}/index.php?m=testcase&f=edit&caseID={case_id}&comment=false&from=testcase"
    r = sess.get(
        url,
        headers={
            "User-Agent": sess.headers.get("User-Agent", "Mozilla/5.0"),
            "Referer": f"{base}/index.php?m=testcase&f=view&caseID={case_id}",
        },
        timeout=60,
    )
    r.raise_for_status()
    for pat in (
        r'name="uid"\s+value="([^"]+)"',
        r'id="uid"\s+value="([^"]+)"',
    ):
        m = re.search(pat, r.text)
        if m:
            return m.group(1).strip()
    return None


def ajax_upload(
    sess: requests.Session, base: str, case_id: int, uid: str, png_path: Path
) -> tuple[bool, str]:
    mime = "image/png"
    fname = png_path.name
    url = (
        f"{base}/index.php?m=file&f=ajaxUpload"
        f"&uid={uid}&objectType=testcase&objectID={case_id}"
    )
    hdr = {
        "X-Requested-With": "XMLHttpRequest",
        "Referer": f"{base}/index.php?m=testcase&f=edit&caseID={case_id}",
    }
    with png_path.open("rb") as fh:
        r = sess.post(url, files={"imgFile": (fname, fh, mime)}, headers=hdr, timeout=120)
    if r.status_code != 200:
        return False, f"HTTP {r.status_code}"
    try:
        j = json.loads((r.text or "").strip())
    except json.JSONDecodeError:
        return False, (r.text or "")[:400]
    if j.get("error") == 0 or j.get("result") == "success":
        return True, json.dumps(j, ensure_ascii=False)[:300]
    return False, str(j)[:400]


def find_xmind_path() -> Path:
    explicit = os.environ.get("XMIND_PATH", "").strip()
    if explicit:
        p = Path(explicit)
        if p.is_file():
            return p
        raise FileNotFoundError(f"XMIND_PATH 无效: {explicit}")
    globs = [
        r"C:\Users\Reolink\Desktop\2026云服务\*_v2.xmind",
        r"C:\Users\Reolink\Desktop\**\*_v2.xmind",
    ]
    for g in globs:
        found = glob.glob(g, recursive=True)
        if found:
            return Path(found[0])
    raise FileNotFoundError("未找到 .xmind，请设置 XMIND_PATH")


def extract_image_nodes(xmind: Path) -> list[tuple[str, str]]:
    """返回 (思维导图路径文本, resources 内文件名)。"""
    zf = zipfile.ZipFile(xmind, "r")
    root = json.loads(zf.read("content.json").decode("utf-8"))
    if isinstance(root, list):
        sheet = root[0]
    else:
        sheet = root
    rt = sheet.get("rootTopic") or {}

    def walk(d: dict, ancestors: list[str]) -> list[tuple[str, str]]:
        t = d.get("title", "")
        if not isinstance(t, str):
            t = str(t) if t else ""
        chain = ancestors + [t]
        out: list[tuple[str, str]] = []
        img = d.get("image")
        if isinstance(img, dict):
            src = img.get("src") or ""
            if src.startswith("xap:resources/"):
                fn = src.split("/")[-1]
                path = " / ".join(x for x in chain if x)
                out.append((path, fn))
        ch = d.get("children") or {}
        for kid in ch.get("attached") or []:
            if isinstance(kid, dict):
                out.extend(walk(kid, chain))
        return out

    rows = walk(rt, [])
    zf.close()
    return rows


def norm_title(s: str) -> str:
    s = re.sub(r"【[^】]*】", " ", s)
    s = re.sub(r"[\s\-_/、，,]+", " ", s)
    return s.strip().lower()


def section_tokens(s: str) -> set[str]:
    """提取 1 / 1.1 / 1.2.3 等编号 token。"""
    return set(re.findall(r"\d+(?:\.\d+)+|\d+(?=[^\d.]|$)", s))


def match_score(case_title: str, xmind_path: str) -> float:
    a, b = norm_title(case_title), norm_title(xmind_path)
    if not a or not b:
        return 0.0
    base = SequenceMatcher(None, a, b).ratio()
    sa, sb = section_tokens(case_title), section_tokens(xmind_path)
    inter = len(sa & sb)
    bonus = min(0.35, inter * 0.12)
    return min(1.0, base + bonus)


def case_has_resource_file(detail: dict, resource_filename: str) -> bool:
    files = detail.get("files") or {}
    if isinstance(files, dict):
        for fi in files.values():
            if not isinstance(fi, dict):
                continue
            n = (fi.get("title") or fi.get("name") or "") or ""
            p = (fi.get("pathname") or "") or ""
            if resource_filename in n or resource_filename in p:
                return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("product", type=int)
    ap.add_argument("module", type=int)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--min-score", type=float, default=0.28)
    args = ap.parse_args()

    base = os.environ.get("ZENTAO_URL", "https://pms.reolink.com.cn").rstrip("/")
    account = os.environ.get("ZENTAO_ACCOUNT", "").strip()
    password = os.environ.get("ZENTAO_PASSWORD", "")
    cookie = os.environ.get("ZENTAO_WEB_COOKIE", "").strip()
    if not account or not password:
        print("请设置 ZENTAO_ACCOUNT、ZENTAO_PASSWORD", file=sys.stderr)
        return 2
    if not cookie:
        print("请设置 ZENTAO_WEB_COOKIE", file=sys.stderr)
        return 2

    xmind = find_xmind_path()
    print("XMind:", xmind)
    nodes = extract_image_nodes(xmind)
    print("带图节点数:", len(nodes))

    tok = api_token(base, account, password)
    cases = list_cases_module(base, tok, args.product, args.module)
    print("模块用例数:", len(cases))

    # 全局贪心：按 (用例, 导图图) 得分从高到低分配，每个用例至多一张、每张图仅用一次
    triples: list[tuple[float, int, str, str]] = []  # score, case_id, path, filename
    for c in cases:
        cid = int(c.get("caseID") or c.get("id") or 0)
        if not cid:
            continue
        title = (c.get("title") or "").strip()
        for path, fn in nodes:
            sc = match_score(title, path)
            if sc >= args.min_score:
                triples.append((sc, cid, path, fn))

    triples.sort(key=lambda x: -x[0])
    used_img: set[str] = set()
    used_case: set[int] = set()
    pairs: list[tuple[int, str, str, float]] = []
    for sc, cid, path, fn in triples:
        if cid in used_case or fn in used_img:
            continue
        pairs.append((cid, path, fn, sc))
        used_case.add(cid)
        used_img.add(fn)

    pairs.sort(key=lambda x: -x[3])
    print("\n=== 拟上传映射（按得分降序，共 %d 条）===" % len(pairs))
    for cid, path, fn, sc in pairs:
        print(f"  [{sc:.3f}] case {cid} <- {fn}")
        print(f"         导图: {path[:100]}...")

    if args.dry_run:
        print("\n--dry-run 结束，未上传。")
        return 0

    sess = requests.Session()
    sess.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120",
            "Cookie": cookie,
        }
    )

    tmp = Path(tempfile.mkdtemp(prefix="xmind_zt_"))
    ok, skip, fail = 0, 0, 0
    zf = zipfile.ZipFile(xmind, "r")

    for cid, path, fn, sc in pairs:
        detail = fetch_case_detail(base, tok, cid)
        if case_has_resource_file(detail, fn):
            print(f"跳过 {cid}（已含附件 {fn}）")
            skip += 1
            continue
        png_bytes = zf.read("resources/" + fn)
        out_png = tmp / f"case{cid}_{fn}"
        out_png.write_bytes(png_bytes)
        uid = fetch_form_uid(sess, base, cid)
        if not uid:
            print(f"失败 {cid}: 无 uid", file=sys.stderr)
            fail += 1
            continue
        good, msg = ajax_upload(sess, base, cid, uid, out_png)
        if good:
            d2 = fetch_case_detail(base, tok, cid)
            if case_has_resource_file(d2, fn) or len(d2.get("files") or {}) > len(
                detail.get("files") or {}
            ):
                print(f"成功 {cid} <- {fn} ({msg})")
                ok += 1
            else:
                print(f"疑失败 {cid}: API 未见附件 ({msg})", file=sys.stderr)
                fail += 1
        else:
            print(f"失败 {cid}: {msg}", file=sys.stderr)
            fail += 1

    zf.close()
    print("\n汇总: 成功", ok, "跳过", skip, "失败", fail, "临时目录", tmp)
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
