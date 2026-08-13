from __future__ import annotations

import argparse
import csv
import html
import json
import math
import pathlib
import re
import sys
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
from urllib.parse import parse_qs, urlparse

import requests


DEFAULT_URL = (
    "https://pms.reolink.com.cn/index.php"
    "?m=testcase&f=browse&productID=42&branch=all&browseType=byModule&param=20331"
)
DEFAULT_OUT = pathlib.Path(r"D:\reolink_knowledge")
MCP_CONFIG = pathlib.Path.home() / ".cursor" / "mcp.json"
PAGE_SIZE = 1000
TIMEOUT = 60
RETRIES = 4
THREADS = threading.local()
BR_RE = re.compile(r"(?is)<\s*br\s*/?\s*>")
END_RE = re.compile(r"(?is)</\s*(p|div|li|tr|table|ul|ol|h[1-6])\s*>")
LI_RE = re.compile(r"(?is)<\s*li\b[^>]*>")
TAG_RE = re.compile(r"(?is)<[^>]+>")
SPACE_RE = re.compile(r"[ \t\r\f\v]+")


def conf_out() -> None:
    if sys.platform == "win32":
        for name in ("stdout", "stderr"):
            stream = getattr(sys, name, None)
            if stream:
                try:
                    stream.reconfigure(encoding="utf-8", errors="replace")
                except Exception:
                    pass


def log(msg: str) -> None:
    print(msg, flush=True)


def load_creds() -> tuple[str, str]:
    data = json.loads(MCP_CONFIG.read_text(encoding="utf-8"))
    for server in (data.get("mcpServers") or {}).values():
        headers = server.get("headers") or {}
        user = headers.get("x-zentao-username")
        pwd = headers.get("x-zentao-password")
        if user and pwd:
            return user, pwd
    raise RuntimeError(f"未在 {MCP_CONFIG} 找到禅道账号。")


def parse_target(url: str) -> dict[str, Any]:
    u = urlparse(url)
    q = parse_qs(u.query)
    product = ((q.get("productID") or q.get("product") or [""])[0]).strip()
    module = ((q.get("param") or q.get("module") or [""])[0]).strip()
    if not product or not module:
        raise RuntimeError("链接缺少 productID 或 param/module 参数。")
    return {
        "browse_url": url,
        "base_url": f"{u.scheme}://{u.netloc}",
        "product_id": int(product),
        "module_id": int(module),
        "branch": ((q.get("branch") or ["all"])[0]).strip() or "all",
        "browse_type": ((q.get("browseType") or [""])[0]).strip(),
    }


def login(base: str, user: str, pwd: str) -> tuple[str, requests.Session]:
    r = requests.post(f"{base}/api.php/v1/tokens", json={"account": user, "password": pwd}, timeout=TIMEOUT)
    r.raise_for_status()
    token = r.json().get("token")
    if not token:
        raise RuntimeError("登录成功但没有拿到 token。")
    s = requests.Session()
    s.headers.update({"Token": token, "Accept": "application/json"})
    return token, s


def api_get(session: requests.Session, url: str, params: dict[str, Any] | None = None) -> Any:
    last: Exception | None = None
    for i in range(RETRIES):
        try:
            r = session.get(url, params=params, timeout=TIMEOUT)
            r.raise_for_status()
            return r.json()
        except Exception as exc:
            last = exc
            if i + 1 < RETRIES:
                time.sleep(i + 1)
    raise RuntimeError(f"请求失败: {url} params={params!r} err={last}")


def worker_detail(base: str, token: str, case_id: int) -> dict[str, Any]:
    session = getattr(THREADS, "session", None)
    if session is None:
        session = requests.Session()
        session.headers.update({"Token": token, "Accept": "application/json"})
        THREADS.session = session
    return api_get(session, f"{base}/api.php/v1/testcases/{case_id}")


def flatten_modules(
    nodes: list[dict[str, Any]],
    out: dict[int, dict[str, Any]] | None = None,
    parent_ids: list[int] | None = None,
    parent_names: list[str] | None = None,
) -> dict[int, dict[str, Any]]:
    out = out or {}
    parent_ids = parent_ids or []
    parent_names = parent_names or []
    for node in nodes:
        mid = int(node["id"])
        name = str(node.get("name") or "").strip() or f"module-{mid}"
        ids = [*parent_ids, mid]
        names = [*parent_names, name]
        kids = node.get("children") or []
        out[mid] = {
            "id": mid,
            "name": name,
            "parent": int(node.get("parent") or 0),
            "path_ids": ids,
            "path_names": names,
            "path_text": " / ".join(names),
        }
        if kids:
            flatten_modules(kids, out=out, parent_ids=ids, parent_names=names)
    return out


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    text = BR_RE.sub("\n", text)
    text = END_RE.sub("\n", text)
    text = LI_RE.sub("- ", text)
    text = TAG_RE.sub("", text)
    text = html.unescape(text).replace("\r\n", "\n").replace("\r", "\n")
    lines = []
    for raw in text.split("\n"):
        line = SPACE_RE.sub(" ", raw).strip()
        if line:
            lines.append(line)
    return "\n".join(lines)


def case_id_of(item: dict[str, Any]) -> int:
    value = item.get("caseID", item.get("id"))
    if isinstance(value, str) and value.startswith("case_"):
        value = value.split("_", 1)[1]
    return int(value)


def norm_user(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return {"id": value.get("id"), "account": value.get("account"), "realname": value.get("realname")}
    return {"id": None, "account": str(value), "realname": ""}


def norm_case(detail: dict[str, Any], module_map: dict[int, dict[str, Any]], base: str) -> dict[str, Any]:
    cid = int(detail.get("id") or detail.get("caseID"))
    mid = int(detail.get("module") or 0)
    mod = module_map.get(mid) or {"id": mid, "name": f"module-{mid}", "path_ids": [mid], "path_names": [f"module-{mid}"], "path_text": f"module-{mid}"}
    steps = []
    for i, step in enumerate(detail.get("steps") or [], 1):
        steps.append(
            {
                "index": i,
                "name": str(step.get("name") or i),
                "type": str(step.get("type") or "step"),
                "desc": clean_text(step.get("desc") or step.get("step") or ""),
                "expect": clean_text(step.get("expect") or ""),
            }
        )
    files = []
    for item in detail.get("files") or []:
        if isinstance(item, dict):
            files.append({"id": item.get("id"), "title": item.get("title") or item.get("pathname") or item.get("name") or "", "size": item.get("size")})
        else:
            files.append({"id": None, "title": str(item), "size": None})
    return {
        "case_id": cid,
        "title": clean_text(detail.get("title") or ""),
        "link": f"{base}/index.php?m=testcase&f=view&caseID={cid}",
        "product": int(detail.get("product") or 0),
        "module_id": mid,
        "module_name": mod["name"],
        "module_path_ids": mod["path_ids"],
        "module_path_names": mod["path_names"],
        "module_path_text": mod["path_text"],
        "pri": detail.get("pri"),
        "type": detail.get("type"),
        "stage": detail.get("stage") or "",
        "status": detail.get("status") or "",
        "version": detail.get("version"),
        "current_version": detail.get("currentVersion"),
        "precondition": clean_text(detail.get("precondition") or ""),
        "keywords": clean_text(detail.get("keywords") or ""),
        "opened_by": norm_user(detail.get("openedBy")),
        "opened_date": detail.get("openedDate"),
        "last_edited_by": norm_user(detail.get("lastEditedBy")),
        "last_edited_date": detail.get("lastEditedDate"),
        "last_run_result": detail.get("lastRunResult"),
        "last_run_date": detail.get("lastRunDate"),
        "steps": steps,
        "files": files,
    }


def render_case(case: dict[str, Any]) -> str:
    lines = [
        f"## 用例 {case['case_id']} — {case['title']}",
        "",
        f"- 链接：`{case['link']}`",
        f"- 模块路径：`{case['module_path_text']}`",
        f"- 类型：`{case['type'] or ''}` / 优先级：`{case['pri']}` / 状态：`{case['status'] or ''}` / 版本：`{case['current_version'] or case['version'] or ''}`",
    ]
    if case.get("precondition"):
        lines += ["", "### 前置条件", ""]
        lines += [f"- {x}" for x in case["precondition"].splitlines()]
    lines += ["", "### 步骤与预期", ""]
    if case["steps"]:
        for step in case["steps"]:
            mark = f"- 步骤 {step['name']}"
            if step["type"] and step["type"] != "step":
                mark += f" [{step['type']}]"
            lines.append(f"{mark}: {step['desc'] or '(空)'}")
            if step["expect"]:
                first = True
                for exp in step["expect"].splitlines():
                    lines.append(("  - 预期: " if first else "    ") + exp)
                    first = False
    else:
        lines.append("- 无步骤数据")
    if case["files"]:
        lines += ["", "### 附件", ""]
        for item in case["files"]:
            extra = f" / {item['size']} bytes" if item.get("size") is not None else ""
            lines.append(f"- {item['title'] or '未命名附件'}{extra}")
    return "\n".join(lines + ["", "---", ""])


def write_json(path: pathlib.Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_jsonl(path: pathlib.Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def export(url: str, out_dir: pathlib.Path, workers: int) -> dict[str, Any]:
    target = parse_target(url)
    user, pwd = load_creds()
    out_dir.mkdir(parents=True, exist_ok=True)
    data_dir = out_dir / "data"
    corpus_dir = out_dir / "corpus"
    data_dir.mkdir(parents=True, exist_ok=True)
    corpus_dir.mkdir(parents=True, exist_ok=True)
    token, session = login(target["base_url"], user, pwd)
    log("[1/5] 读取模块树...")
    tree = api_get(session, f"{target['base_url']}/api.php/v1/modules", {"type": "case", "id": target["product_id"]}).get("modules") or []
    module_map = flatten_modules(tree)
    root = module_map.get(target["module_id"]) or {"path_text": str(target["module_id"])}
    log("[2/5] 拉取列表...")
    params = {"module": target["module_id"], "limit": PAGE_SIZE, "page": 1, "order": "id_asc"}
    if target["branch"] != "all":
        params["branch"] = target["branch"]
    first = api_get(session, f"{target['base_url']}/api.php/v1/products/{target['product_id']}/testcases", params)
    total = int(first.get("total") or 0)
    items = list(first.get("testcases") or [])
    pages = max(1, math.ceil(total / PAGE_SIZE))
    log(f"  共 {total} 条，{pages} 页")
    for page in range(2, pages + 1):
        params["page"] = page
        items.extend(api_get(session, f"{target['base_url']}/api.php/v1/products/{target['product_id']}/testcases", params).get("testcases") or [])
        log(f"  已拉取列表页 {page}/{pages}")
    seen, ids = set(), []
    for item in items:
        cid = case_id_of(item)
        if cid not in seen:
            seen.add(cid)
            ids.append(cid)
    log(f"[3/5] 并发拉取 {len(ids)} 条详情...")
    details = {}
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        mapping = {pool.submit(worker_detail, target["base_url"], token, cid): cid for cid in ids}
        for idx, future in enumerate(as_completed(mapping), 1):
            details[mapping[future]] = future.result()
            if idx == 1 or idx % 50 == 0 or idx == len(ids):
                log(f"  详情进度: {idx}/{len(ids)}")
    log("[4/5] 生成知识库文件...")
    cases = [norm_case(details[cid], module_map, target["base_url"]) for cid in ids]
    groups: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for case in cases:
        groups[int(case["module_id"])].append(case)
    module_rows = []
    for mid, group in sorted(groups.items(), key=lambda x: (module_map.get(x[0], {}).get("path_text", ""), x[0])):
        mod = module_map.get(mid) or {"path_text": f"module-{mid}", "name": f"module-{mid}"}
        file_name = f"module-{mid}.md"
        content = [f"# 模块 {mid}：{mod['name']}", "", f"- 模块路径：`{mod['path_text']}`", f"- 用例总数：`{len(group)}`", ""]
        for case in group:
            content.append(render_case(case).rstrip())
        (corpus_dir / file_name).write_text("\n".join(content).rstrip() + "\n", encoding="utf-8")
        module_rows.append({"module_id": mid, "testcase_count": len(group), "module_path_text": mod["path_text"], "corpus_file": f"corpus/{file_name}"})
    manifest = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "browse_url": target["browse_url"],
        "product_id": target["product_id"],
        "module_id": target["module_id"],
        "module_path_text": root["path_text"],
        "branch": target["branch"],
        "browse_type": target["browse_type"],
        "testcase_total": len(cases),
        "module_count": len(module_rows),
        "output_dir": str(out_dir),
    }
    write_json(data_dir / "manifest.json", manifest)
    write_json(data_dir / "module_tree.json", tree)
    write_json(data_dir / "module_map.json", module_map)
    write_jsonl(data_dir / "testcases.jsonl", cases)
    with (data_dir / "index.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["case_id", "title", "module_id", "module_path_text", "type", "pri", "status", "version", "corpus_file", "link"])
        file_by_module = {row["module_id"]: row["corpus_file"] for row in module_rows}
        for case in cases:
            w.writerow([case["case_id"], case["title"], case["module_id"], case["module_path_text"], case["type"], case["pri"], case["status"], case["current_version"] or case["version"], file_by_module.get(case["module_id"], ""), case["link"]])
    readme = [
        "# 禅道测试用例本地知识库", "",
        "## 来源与范围", "",
        f"- 浏览入口：[{target['browse_url']}]({target['browse_url']})",
        f"- 产品 ID：`{target['product_id']}`",
        f"- 根模块 ID：`{target['module_id']}`",
        f"- 根模块路径：`{root['path_text']}`",
        f"- 同步时间：`{manifest['generated_at']}`", "",
        "## 统计概览", "",
        f"- 用例总数：`{manifest['testcase_total']}`",
        f"- 实际模块数：`{manifest['module_count']}`",
        f"- 输出目录：`{manifest['output_dir']}`", "",
        "## 文件说明", "",
        "- `README.md`：说明文件。",
        "- `INDEX.md`：模块索引。",
        "- `data/index.csv`：逐条用例索引。",
        "- `data/testcases.jsonl`：完整结构化用例数据。",
        "- `data/module_tree.json` / `data/module_map.json`：模块树快照。",
        "- `corpus/module-*.md`：按实际模块分组的 Markdown 语料。",
        "- `export_zentao_module_kb.py`：导出脚本。", "",
    ]
    (out_dir / "README.md").write_text("\n".join(readme), encoding="utf-8")
    index = ["# 模块索引", "", f"- 浏览入口：`{target['browse_url']}`", f"- 根模块：`{root['path_text']}`", "", "| 模块 ID | 用例数 | 模块路径 | 知识库文件 |", "|--------|--------|----------|------------|"]
    for row in module_rows:
        index.append(f"| {row['module_id']} | {row['testcase_count']} | {row['module_path_text']} | {row['corpus_file']} |")
    (out_dir / "INDEX.md").write_text("\n".join(index) + "\n", encoding="utf-8")
    log("[5/5] 导出完成。")
    try:
        from build_rag_index import build_index

        log("[RAG] 构建向量索引...")
        build_index(rebuild=True)
        log("[RAG] 向量索引构建完成。")
    except Exception as exc:
        log("[RAG] 索引构建失败（可稍后手动运行 build_rag_index.py）：%s" % exc)
    return manifest


def main() -> int:
    conf_out()
    parser = argparse.ArgumentParser(description="从禅道模块浏览链接导出本地知识库。")
    parser.add_argument("browse_url", nargs="?", default=DEFAULT_URL)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUT))
    parser.add_argument("--workers", type=int, default=12)
    args = parser.parse_args()
    manifest = export(args.browse_url, pathlib.Path(args.output_dir), args.workers)
    log("完成: product={product_id} module={module_id} testcase_total={testcase_total} output={output_dir}".format(**manifest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
