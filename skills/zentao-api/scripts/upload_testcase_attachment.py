#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
将本地文件作为附件上传到禅道指定测试用例（REST，不经过 MCP）。

依赖：Python 3.8+，标准库即可。

用法（PowerShell 示例）：
  $env:ZENTAO_URL = "https://pms.reolink.com.cn"
  $env:ZENTAO_ACCOUNT = "你的账号"
  $env:ZENTAO_PASSWORD = "你的密码"
  python upload_testcase_attachment.py 390666 "C:\\path\\to\\image.png"

说明：
  - 优先调用 api.php/v2/files（表单字段 file、objectType、objectID），与禅道官方接口说明一致。
  - 若 v2 返回非成功，会再尝试 api.php/v1/files（字段 files、uid）仅供兼容旧实例。
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# Windows 控制台默认编码可能导致中文错误信息乱码
if sys.platform == "win32":
    try:
        import io as _io

        sys.stdout = _io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True
        )
        sys.stderr = _io.TextIOWrapper(
            sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True
        )
    except Exception:
        pass


def post_json(url: str, payload: dict, timeout: int = 60) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code}: {body}") from e
    except URLError as e:
        raise RuntimeError(f"网络错误: {e.reason}") from e
    try:
        return json.loads(body) if body.strip() else {}
    except json.JSONDecodeError:
        raise RuntimeError(f"响应非 JSON: {body[:500]}")


def get_token(base: str, account: str, password: str) -> str:
    url = f"{base.rstrip('/')}/api.php/v1/tokens"
    out = post_json(url, {"account": account, "password": password})
    token = out.get("token")
    if not token:
        raise RuntimeError(f"取 token 失败，响应: {out}")
    return str(token)


def build_multipart(fields: dict[str, str], file_field: str, file_path: Path) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    crlf = b"\r\n"
    chunks: list[bytes] = []

    for name, value in fields.items():
        chunks.append(f"--{boundary}".encode())
        chunks.append(f'Content-Disposition: form-data; name="{name}"'.encode() + crlf + crlf)
        chunks.append(value.encode("utf-8") + crlf)

    filename = file_path.name
    mime, _ = mimetypes.guess_type(str(file_path))
    if not mime:
        mime = "application/octet-stream"
    raw = file_path.read_bytes()
    chunks.append(f"--{boundary}".encode())
    chunks.append(
        f'Content-Disposition: form-data; name="{file_field}"; filename="{filename}"'.encode()
        + crlf
        + f"Content-Type: {mime}".encode()
        + crlf
        + crlf
    )
    chunks.append(raw + crlf)
    chunks.append(f"--{boundary}--".encode() + crlf)
    body = b"".join(chunks)
    content_type = f"multipart/form-data; boundary={boundary}"
    return body, content_type


def post_multipart(url: str, token: str, fields: dict[str, str], file_field: str, file_path: Path) -> tuple[int, str]:
    body, content_type = build_multipart(fields, file_field, file_path)
    req = Request(url, data=body, method="POST")
    req.add_header("Content-Type", content_type)
    req.add_header("Token", token)
    try:
        with urlopen(req, timeout=120) as resp:
            text = resp.read().decode("utf-8", errors="replace")
            return resp.status, text
    except HTTPError as e:
        text = e.read().decode("utf-8", errors="replace")
        return e.code, text
    except URLError as e:
        raise RuntimeError(f"网络错误: {e.reason}") from e


def main() -> int:
    parser = argparse.ArgumentParser(description="上传附件到禅道测试用例")
    parser.add_argument("case_id", type=int, help="测试用例 ID，例如 390666")
    parser.add_argument("file", type=Path, help="本地附件路径")
    args = parser.parse_args()

    base = os.environ.get("ZENTAO_URL", "https://pms.reolink.com.cn").rstrip("/")
    account = os.environ.get("ZENTAO_ACCOUNT", "").strip()
    password = os.environ.get("ZENTAO_PASSWORD", "")

    if not account or not password:
        print(
            "失败原因：未设置环境变量 ZENTAO_ACCOUNT / ZENTAO_PASSWORD（可选 ZENTAO_URL）。\n"
            "请在当前终端先设置后再运行本脚本，不要将密码写入仓库或技能文件。",
            file=sys.stderr,
        )
        return 2

    fp = args.file.expanduser().resolve()
    if not fp.is_file():
        print(f"失败原因：文件不存在: {fp}", file=sys.stderr)
        return 3

    try:
        token = get_token(base, account, password)
    except Exception as e:
        print(f"失败原因：登录取 token 失败 — {e}", file=sys.stderr)
        return 4

    # 官方文档：POST /api.php/v2/files，表单 file + objectType + objectID
    v2_url = f"{base}/api.php/v2/files"
    code, text = post_multipart(
        v2_url,
        token,
        {"objectType": "testcase", "objectID": str(args.case_id)},
        "file",
        fp,
    )
    print(f"[v2/files] HTTP {code}\n{text}")

    ok = False
    if code == 200:
        try:
            j = json.loads(text)
            if j.get("status") == "success" or j.get("id"):
                ok = True
        except json.JSONDecodeError:
            pass

    if ok:
        print("上传完成（v2/files）。")
        return 0

    # 兼容尝试 v1（技能文档中的写法）
    uid = uuid.uuid4().hex
    v1_url = f"{base}/api.php/v1/files"
    code1, text1 = post_multipart(v1_url, token, {"uid": uid}, "files", fp)
    print(f"[v1/files] HTTP {code1}\n{text1}")

    if code1 == 200:
        try:
            j1 = json.loads(text1)
            if not j1.get("error"):
                print("上传完成（v1/files）；若页面上仍未显示，请在技能中补充「v1 需配合用例编辑关联 uid」说明。")
                return 0
        except json.JSONDecodeError:
            print("v1 响应非 JSON，视为未确认成功。", file=sys.stderr)

    print(
        "\n可能原因汇总：\n"
        "1) 实例仅支持 v2 或仅支持 v1，字段名不一致（file vs files）。\n"
        "2) Token 无「用例附件」权限或测试用例 ID 不存在/无访问权。\n"
        "3) 文件过大或服务器限制 multipart 大小。\n"
        "4) 公司网络或 HTTPS 拦截。\n"
        "请将实际 HTTP 状态码与响应体贴到 ~/.cursor/skills/zentao-api/references/docs-files.md 的「排错」小节以便后续查阅。",
        file=sys.stderr,
    )
    return 5


if __name__ == "__main__":
    raise SystemExit(main())
