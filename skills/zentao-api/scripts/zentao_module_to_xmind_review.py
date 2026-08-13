# -*- coding: utf-8 -*-
"""
按禅道模块导出「用例评审」XMind（Zen 格式）：
根模块 -> 子模块 -> 用例 -> 步骤/预期 -> 备注/截图。

环境变量：
  ZENTAO_URL（默认 https://pms.reolink.com.cn）
  ZENTAO_ACCOUNT、ZENTAO_PASSWORD

示例：
  python zentao_module_to_xmind_review.py 387 21933
  python zentao_module_to_xmind_review.py 387 21933 --output "C:\\Users\\Reolink\\Desktop\\product387_module21933_用例评审_20260610.xmind"
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import re
import sys
import tempfile
import uuid
import zipfile
from pathlib import Path
from typing import Any

import requests

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def clean_text(v: Any) -> str:
    if v is None:
        return ""
    s = str(v)
    s = html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def api_token(base: str, account: str, password: str) -> str:
    r = requests.post(
        f"{base}/api.php/v1/tokens",
        json={"account": account, "password": password},
        timeout=60,
    )
    r.raise_for_status()
    token = (r.json() or {}).get("token")
    if not token:
        raise RuntimeError("取 token 失败")
    return str(token)


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
        payload = r.json() or {}
        chunk = payload.get("testcases") or payload.get("cases") or []
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


def get_case_detail(base: str, token: str, case_id: int) -> dict:
    r = requests.get(
        f"{base}/api.php/v1/testcases/{case_id}",
        headers={"Token": token},
        timeout=60,
    )
    r.raise_for_status()
    return r.json() or {}


def get_modules(base: str, token: str, product: int) -> list[dict]:
    r = requests.get(
        f"{base}/api.php/v1/modules",
        headers={"Token": token},
        params={"type": "case", "id": product},
        timeout=60,
    )
    r.raise_for_status()
    payload = r.json() or {}
    modules = payload.get("modules") or payload.get("data") or payload
    if isinstance(modules, dict):
        modules = list(modules.values())
    return modules if isinstance(modules, list) else []


def parse_module_tree(modules: list[dict]) -> tuple[dict[int, dict], dict[int, list[int]]]:
    mod_map: dict[int, dict] = {}
    children: dict[int, list[int]] = {}
    stack = [x for x in modules if isinstance(x, dict)]
    while stack:
        m = stack.pop()
        try:
            mid = int(m.get("id") or 0)
        except Exception:
            continue
        if mid <= 0:
            continue
        try:
            parent = int(m.get("parent") or 0)
        except Exception:
            parent = 0
        name = clean_text(m.get("name") or m.get("title") or f"模块{mid}") or f"模块{mid}"
        mod_map[mid] = {"id": mid, "parent": parent, "name": name}
        children.setdefault(parent, []).append(mid)
        for kid in m.get("children") or []:
            if isinstance(kid, dict):
                stack.append(kid)
    return mod_map, children


def collect_descendants(root: int, children: dict[int, list[int]]) -> set[int]:
    out: set[int] = set()
    stack = [root]
    while stack:
        cur = stack.pop()
        if cur in out:
            continue
        out.add(cur)
        stack.extend(children.get(cur, []))
    return out


def normalize_files(raw: Any) -> list[dict]:
    if isinstance(raw, dict):
        values = list(raw.values())
    elif isinstance(raw, list):
        values = raw
    else:
        return []
    out: list[dict] = []
    for x in values:
        if isinstance(x, dict):
            out.append(x)
    return out


def download_case_file(base: str, token: str, file_id: int, out_path: Path) -> bool:
    url = f"{base}/api.php/v1/files/{file_id}"
    r = requests.get(url, headers={"Token": token}, timeout=120)
    if r.status_code != 200:
        return False
    ctype = (r.headers.get("Content-Type") or "").lower()
    body = r.content
    if "application/json" in ctype:
        try:
            j = r.json()
        except Exception:
            return False
        real_url = (
            (j.get("url") if isinstance(j, dict) else "")
            or (j.get("data", {}) or {}).get("url")
            or ""
        )
        if not real_url:
            return False
        rr = requests.get(real_url, headers={"Token": token}, timeout=120)
        if rr.status_code != 200:
            return False
        body = rr.content
    out_path.write_bytes(body)
    return True


def step_nodes(step_list: list[dict]) -> list[dict]:
    items: dict[int, dict] = {}
    roots: list[int] = []
    for st in step_list:
        sid = int(st.get("id") or 0)
        if sid <= 0:
            continue
        parent = int(st.get("parent") or 0)
        desc = clean_text(st.get("step") or st.get("desc"))
        expect = clean_text(st.get("expect"))
        title = f"{clean_text(st.get('name') or sid)} {desc}".strip()
        title = title if title else f"步骤 {sid}"
        items[sid] = {"id": sid, "parent": parent, "title": title, "expect": expect, "children": []}
    for sid, item in items.items():
        parent = item["parent"]
        if parent in items:
            items[parent]["children"].append(sid)
        else:
            roots.append(sid)

    def build_node(sid: int) -> dict:
        s = items[sid]
        topic = {"id": _new_id(), "title": s["title"]}
        attached: list[dict] = []
        if s["expect"]:
            attached.append({"id": _new_id(), "title": f"预期：{s['expect']}"})
        for cid in sorted(s["children"], key=lambda x: str(items[x]["title"])):
            attached.append(build_node(cid))
        if attached:
            topic["children"] = {"attached": attached}
        return topic

    return [build_node(x) for x in roots]


def build_xmind_content(
    root_name: str,
    grouped_cases: dict[int, list[dict]],
    module_name: dict[int, str],
) -> list[dict]:
    root_topic = {"id": _new_id(), "title": f"用例评审-{root_name}"}
    module_topics: list[dict] = []
    for mid in sorted(grouped_cases.keys(), key=lambda x: module_name.get(x, f"模块{x}")):
        case_topics: list[dict] = []
        for c in sorted(grouped_cases[mid], key=lambda x: clean_text(x.get("title", ""))):
            cid = int(c.get("id") or c.get("caseID") or 0)
            title = clean_text(c.get("title") or f"用例{cid}")
            case_topic = {"id": _new_id(), "title": f"{title} #{cid}"}

            children: list[dict] = []
            steps = c.get("steps") or []
            if isinstance(steps, list):
                children.extend(step_nodes(steps))

            note_lines = [
                f"前置：{clean_text(c.get('precondition') or '无')}",
                f"优先级：P{clean_text(c.get('pri') or '-')}",
                f"类型：{clean_text(c.get('type') or '-')}",
                f"阶段：{clean_text(c.get('stage') or '-')}",
                f"状态：{clean_text(c.get('status') or '-')}",
                f"链接：https://pms.reolink.com.cn/index.php?m=testcase&f=view&caseID={cid}",
            ]
            children.append({"id": _new_id(), "title": "备注", "notes": {"plain": {"content": "\n".join(note_lines)}}})

            images = c.get("_images") or []
            if images:
                img_nodes = []
                for x in images:
                    title = x.get("name") or x.get("resource")
                    src = x.get("resource") or ""
                    node = {"id": _new_id(), "title": title}
                    if src:
                        node["image"] = {"src": f"xap:resources/{src}"}
                    img_nodes.append(node)
                children.append({"id": _new_id(), "title": "p:截图", "children": {"attached": img_nodes}})

            if children:
                case_topic["children"] = {"attached": children}
            case_topics.append(case_topic)

        mod_title = f"m:{module_name.get(mid, f'模块{mid}')}"
        module_topics.append({"id": _new_id(), "title": mod_title, "children": {"attached": case_topics}})

    root_topic["children"] = {"attached": module_topics}
    sheet = {"id": _new_id(), "title": "用例评审", "rootTopic": root_topic}
    return [sheet]


def default_output(product: int, module: int) -> Path:
    d = dt.datetime.now().strftime("%Y%m%d")
    return Path.home() / "Desktop" / f"product{product}_module{module}_用例评审_{d}.xmind"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("product", type=int)
    ap.add_argument("module", type=int)
    ap.add_argument("--output", default="")
    args = ap.parse_args()

    base = os.environ.get("ZENTAO_URL", "https://pms.reolink.com.cn").rstrip("/")
    account = os.environ.get("ZENTAO_ACCOUNT", "").strip()
    password = os.environ.get("ZENTAO_PASSWORD", "")
    if not account or not password:
        print("请设置 ZENTAO_ACCOUNT 和 ZENTAO_PASSWORD", file=sys.stderr)
        return 2

    output = Path(args.output) if args.output else default_output(args.product, args.module)
    output.parent.mkdir(parents=True, exist_ok=True)

    token = api_token(base, account, password)
    modules = get_modules(base, token, args.product)
    mod_map, children = parse_module_tree(modules)
    descendants = collect_descendants(args.module, children) if args.module in mod_map else set()
    root_name = mod_map.get(args.module, {}).get("name", f"模块{args.module}")

    case_summaries = list_cases_module(base, token, args.product, args.module)
    print(f"列表拉取完成：{len(case_summaries)} 条")

    grouped: dict[int, list[dict]] = {}
    tmp = Path(tempfile.mkdtemp(prefix="zentao_xmind_"))
    resources_dir = tmp / "resources"
    resources_dir.mkdir(parents=True, exist_ok=True)
    download_ok = 0
    download_fail = 0

    total = len(case_summaries)
    for i, c in enumerate(case_summaries, start=1):
        cid = int(c.get("caseID") or c.get("id") or 0)
        if cid <= 0:
            continue
        detail = get_case_detail(base, token, cid)
        detail_module = int(detail.get("module") or c.get("module") or 0)
        if descendants and detail_module not in descendants:
            continue
        print(f"[{i}/{total}] 用例 {cid}")

        images: list[dict] = []
        for f in normalize_files(detail.get("files")):
            fid = int(f.get("id") or 0)
            if fid <= 0:
                continue
            name = clean_text(f.get("title") or f.get("name") or f"file_{fid}.bin")
            safe_name = re.sub(r"[^\w.\-]+", "_", name)
            if not safe_name:
                safe_name = f"file_{fid}.bin"
            out_name = f"case{cid}_{fid}_{safe_name}"
            out_path = resources_dir / out_name
            if download_case_file(base, token, fid, out_path):
                images.append({"name": name, "resource": out_name})
                download_ok += 1
            else:
                download_fail += 1

        detail["_images"] = images
        grouped.setdefault(detail_module, []).append(detail)

    module_name = {k: v["name"] for k, v in mod_map.items()}
    content = build_xmind_content(root_name, grouped, module_name)

    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("content.json", json.dumps(content, ensure_ascii=False))
        zf.writestr(
            "metadata.json",
            json.dumps(
                {
                    "dataStructureVersion": "2",
                    "creator": {"name": "CursorAgent", "version": "1.0"},
                    "layoutEngineVersion": "3",
                },
                ensure_ascii=False,
            ),
        )
        zf.writestr("manifest.json", json.dumps({"file-entries": {}}, ensure_ascii=False))
        for p in sorted(resources_dir.glob("*")):
            zf.write(p, arcname=f"resources/{p.name}")

    n_cases = sum(len(x) for x in grouped.values())
    print(f"导出完成：{output}")
    print(f"模块数：{len(grouped)}，用例数：{n_cases}")
    print(f"附件下载：成功 {download_ok}，失败 {download_fail}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
