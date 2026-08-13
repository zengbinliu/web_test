# -*- coding: utf-8 -*-
"""
通过禅道网页接口上传用例附件，不经过 MCP。

流程（禅道 21+ 实测）：
  1) 从「编辑用例」页解析隐藏域 **uid**；
  2) 优先 **POST index.php?m=file&f=ajaxUpload&uid=…&objectType=testcase&objectID=…**，
     文件字段名为 **imgFile**（与源码 `file/control::ajaxUpload` 一致，直接写入 zt_file 并关联用例）；
  3) 若 ajaxUpload 失败，再回退为「用例编辑」整表 multipart（含 **files[]**）。

适用场景：REST `api.php/v1/files` / `v2/files` 不可用，但浏览器可上传附件。

环境变量：
  ZENTAO_URL（默认 https://pms.reolink.com.cn）
  ZENTAO_ACCOUNT、ZENTAO_PASSWORD（用于拉取 API 用例结构；若仅传 Cookie 也需保留以便读 API）
  可选 ZENTAO_WEB_COOKIE：从浏览器开发者工具复制完整 Cookie 请求头值；若设置则**不再**执行脚本内网页登录，
  可绕过「登录后立即要求改密」等拦截（须保证 Cookie 未过期且已正常打开过禅道）。

用法：
  python upload_testcase_via_edit_form.py 390666 "C:\\path\\to\\image.png"
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import string
import sys
from pathlib import Path

import requests


def md5_hex(s: str) -> str:
    return hashlib.md5(s.encode("utf-8")).hexdigest()


def fetch_form_uid(session: requests.Session, base: str, case_id: int) -> str | None:
    """从「编辑用例」页解析上传批次 uid（与页面内文件控件绑定，随机 uid 会导致附件不落库）。"""
    url = (
        f"{base}/index.php?m=testcase&f=edit&caseID={case_id}"
        f"&comment=false&from=testcase"
    )
    r = session.get(
        url,
        headers={
            "User-Agent": session.headers.get("User-Agent", "Mozilla/5.0"),
            "Referer": f"{base}/index.php?m=testcase&f=view&caseID={case_id}",
        },
        timeout=60,
    )
    r.raise_for_status()
    for pat in (
        r'name="uid"\s+value="([^"]+)"',
        r'id="uid"\s+value="([^"]+)"',
        r'name="uid"\s+[^>]*value="([^"]+)"',
    ):
        m = re.search(pat, r.text)
        if m:
            return m.group(1).strip()
    return None


def web_login(session: requests.Session, base: str, account: str, password: str) -> None:
    """禅道 21 + zin：需 POST .../user/f/login&zin=1 才会返回 JSON 并种登录 Cookie。"""
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"{base}/index.php?m=user&f=login",
        }
    )
    session.get(f"{base}/index.php?m=user&f=login", timeout=60)
    rand = session.get(f"{base}/index.php?m=user&f=refreshRandom", timeout=60).text.strip()
    enc = md5_hex(md5_hex(password) + rand)
    # 与前端一致：弱口令强度取 1（可按需改为 computePasswordStrength）
    strength = 1
    r = session.post(
        f"{base}/index.php?m=user&f=login&zin=1",
        data={
            "account": account,
            "password": enc,
            "passwordStrength": str(strength),
            "referer": "/",
            "verifyRand": rand,
            "keepLogin": "1",
            "captcha": "",
        },
        timeout=60,
    )
    try:
        j = r.json()
    except json.JSONDecodeError as e:
        raise RuntimeError(f"登录响应非 JSON（需带 zin=1）：{r.text[:500]}") from e
    if j.get("result") != "success":
        raise RuntimeError(f"登录失败: {j}")


def api_token(base: str, account: str, password: str) -> str:
    r = requests.post(
        f"{base}/api.php/v1/tokens",
        json={"account": account, "password": password},
        timeout=60,
    )
    r.raise_for_status()
    j = r.json()
    t = j.get("token")
    if not t:
        raise RuntimeError(f"取 API token 失败: {j}")
    return str(t)


def fetch_testcase_api(base: str, token: str, case_id: int) -> dict:
    r = requests.get(
        f"{base}/api.php/v1/testcases/{case_id}",
        headers={"Token": token},
        timeout=60,
    )
    r.raise_for_status()
    return r.json()


def step_type_for_form(api_type: str) -> str:
    if api_type == "group":
        return "group"
    # REST 文档中的 item / 网页中的 step 均按 step 提交
    return "step"


def try_ajax_upload_testcase_file(
    sess: requests.Session,
    base: str,
    case_id: int,
    uid: str,
    img: Path,
) -> tuple[bool, str]:
    """
    禅道 21+：用例附件实际上传走 module/file/control::ajaxUpload，
    表单文件字段名为 imgFile（非 testcase 编辑里的 files[]）。
    URL 带 objectType=testcase&objectID= 时可直接写入 zt_file 并关联用例。
    参考源码：ajaxUpload(..., string $field = 'imgFile', ...)。
    """
    mime = "image/png" if img.suffix.lower() == ".png" else "application/octet-stream"
    fname = img.name if all(ord(c) < 128 for c in img.name) else "attachment.png"
    url = (
        f"{base}/index.php?m=file&f=ajaxUpload"
        f"&uid={uid}&objectType=testcase&objectID={case_id}"
    )
    hdr = {
        "X-Requested-With": "XMLHttpRequest",
        "Referer": f"{base}/index.php?m=testcase&f=edit&caseID={case_id}",
    }
    with img.open("rb") as fh:
        r = sess.post(url, files={"imgFile": (fname, fh, mime)}, headers=hdr, timeout=120)
    if r.status_code != 200:
        return False, f"ajaxUpload HTTP {r.status_code}"
    txt = (r.text or "").strip()
    try:
        j = json.loads(txt)
    except json.JSONDecodeError:
        return False, f"ajaxUpload 响应非 JSON: {txt[:300]}"
    if j.get("error") == 0 or j.get("result") == "success":
        return True, txt[:500]
    return False, str(j)[:500]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("case_id", type=int)
    parser.add_argument("image", type=Path)
    args = parser.parse_args()

    base = os.environ.get("ZENTAO_URL", "https://pms.reolink.com.cn").rstrip("/")
    account = os.environ.get("ZENTAO_ACCOUNT", "").strip()
    password = os.environ.get("ZENTAO_PASSWORD", "")
    if not account or not password:
        print("请设置环境变量 ZENTAO_ACCOUNT、ZENTAO_PASSWORD", file=sys.stderr)
        return 2

    img = args.image.expanduser().resolve()
    if not img.is_file():
        print(f"文件不存在: {img}", file=sys.stderr)
        return 3

    sess = requests.Session()
    sess.headers.setdefault(
        "User-Agent",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120",
    )
    web_cookie = os.environ.get("ZENTAO_WEB_COOKIE", "").strip()
    if web_cookie:
        # 支持整段 Cookie 字符串（与浏览器 DevTools 中「Cookie」请求头一致）
        sess.headers["Cookie"] = web_cookie
    else:
        try:
            web_login(sess, base, account, password)
        except Exception as e:
            print(f"网页登录失败: {e}", file=sys.stderr)
            return 4

    try:
        tok = api_token(base, account, password)
        tc = fetch_testcase_api(base, tok, args.case_id)
    except Exception as e:
        print(f"拉取用例(API)失败: {e}", file=sys.stderr)
        return 5

    files_before = len(tc.get("files") or {})
    steps = tc.get("steps") or []
    if not steps:
        print("用例无步骤，无法安全组装编辑表单", file=sys.stderr)
        return 6

    uid = fetch_form_uid(sess, base, args.case_id)
    if not uid:
        uid = "".join(random.choices(string.hexdigits.lower(), k=14))
        print("警告：未能从编辑页解析 uid，已使用随机值，附件可能无法保存。", file=sys.stderr)

    # 禅道 21：附件优先走 ajaxUpload（imgFile），避免仅依赖「编辑保存」multipart 中的 files[]（常被忽略）
    ok_ajax, ajax_detail = try_ajax_upload_testcase_file(
        sess, base, args.case_id, uid, img
    )
    if ok_ajax:
        try:
            tc_ajax = fetch_testcase_api(base, tok, args.case_id)
            if len(tc_ajax.get("files") or {}) > files_before:
                print("已通过 file/ajaxUpload（imgFile）上传并关联到用例。")
                print(ajax_detail)
                return 0
        except Exception:
            pass
        print(
            f"提示：ajaxUpload 返回成功但 API 附件数未增加，将回退编辑表单 multipart。{ajax_detail[:200]}",
            file=sys.stderr,
        )
    else:
        print(
            f"提示：ajaxUpload 失败，将回退编辑表单 multipart。{ajax_detail}",
            file=sys.stderr,
        )

    boundary = "----WebKitFormBoundary" + "".join(random.choices(string.ascii_letters + string.digits, k=16))

    # multipart 字段顺序尽量贴近浏览器（部分网关对顺序敏感）
    fields: list[tuple[str, str]] = []
    fields.append(("title", tc.get("title") or ""))
    fields.append(("color", tc.get("color") or ""))
    fields.append(("scene", str(tc.get("scene") if tc.get("scene") is not None else 0)))
    fields.append(("precondition", tc.get("precondition") or ""))

    for i, st in enumerate(steps, start=1):
        desc = (st.get("desc") or st.get("step") or "").strip()
        exp = (st.get("expect") or "").strip()
        fields.append((f"steps[{i}]", desc))
        fields.append((f"expects[{i}]", exp))
        fields.append((f"stepType[{i}]", step_type_for_form(st.get("type") or "item")))

    # 与浏览器抓包一致：步骤之后先 files[]，再 comment…type，再空 scriptFile，再 script、stage[]…
    mid_fields: list[tuple[str, str]] = [
        ("comment", ""),
        ("uid", uid),
        ("product", str(tc.get("product") or "")),
        ("branch", str(tc.get("branch") if tc.get("branch") is not None else 0)),
        ("module", str(tc.get("module") or "")),
        ("story", "" if not tc.get("story") else str(tc.get("story"))),
        ("type", tc.get("type") or "feature"),
    ]
    stage = tc.get("stage") or "system"
    end_fields: list[tuple[str, str]] = [
        ("script", tc.get("script") or ""),
        ("stage[]", stage if isinstance(stage, str) else "system"),
        ("pri", str(tc.get("pri") or 3)),
        ("status", tc.get("status") or "normal"),
        ("keywords", tc.get("keywords") or ""),
    ]
    ver = tc.get("currentVersion") or tc.get("version")
    if ver is not None:
        end_fields.append(("version", str(ver)))

    # 组装 multipart
    crlf = b"\r\n"
    chunks: list[bytes] = []

    def add_field(name: str, value: str) -> None:
        chunks.append(f"--{boundary}".encode())
        chunks.append(
            f'Content-Disposition: form-data; name="{name}"'.encode("utf-8") + crlf + crlf
        )
        chunks.append(value.encode("utf-8") + crlf)

    for name, value in fields:
        add_field(name, value)

    fname = img.name if all(ord(c) < 128 for c in img.name) else "attachment.png"
    raw = img.read_bytes()
    mime = "image/png" if img.suffix.lower() == ".png" else "application/octet-stream"
    chunks.append(f"--{boundary}".encode())
    disp = (
        f'Content-Disposition: form-data; name="files[]"; filename="{fname}"'.encode("utf-8")
        + crlf
        + f"Content-Type: {mime}".encode("utf-8")
        + crlf
        + crlf
    )
    chunks.append(disp)
    chunks.append(raw + crlf)

    for name, value in mid_fields:
        add_field(name, value)

    # 空 scriptFile（紧接在 type 之后）
    chunks.append(f"--{boundary}".encode())
    chunks.append(
        b'Content-Disposition: form-data; name="scriptFile"; filename=""'
        + crlf
        + b"Content-Type: application/octet-stream"
        + crlf
        + crlf
        + crlf
    )

    for name, value in end_fields:
        add_field(name, value)

    chunks.append(f"--{boundary}--".encode() + crlf)

    body = b"".join(chunks)
    view_ver = tc.get("currentVersion")
    if view_ver is None:
        view_ver = tc.get("version")
    if view_ver is None:
        view_ver = 0
    # 与浏览器抓包一致（含 zin=1）；误报「改密页」时勿随意去掉 zin
    url = (
        f"{base}/index.php?m=testcase&f=edit&caseID={args.case_id}"
        f"&comment=false&executionID=&from=testcase&zin=1"
    )
    headers = {
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "*/*",
        "Origin": base,
        "Referer": (
            f"{base}/index.php?m=testcase&f=view&caseID={args.case_id}"
            f"&version={view_ver}&from=testcase"
        ),
    }
    r = sess.post(url, data=body, headers=headers, timeout=120)
    txt = r.text
    print("HTTP", r.status_code)
    print(txt[:1500])

    if r.status_code != 200:
        print("上传/保存失败：HTTP 非 200", file=sys.stderr)
        return 7

    # 禅道可能强制跳转「修改密码」页（仅根据 config 中的 rawMethod 判断，避免误匹配 JS 字符串）
    if '"rawMethod":"changepassword"' in txt:
        print(
            "失败：响应为「修改密码」页（rawMethod=changepassword），用例未保存。\n"
            "处理：① 在浏览器登录并完成改密/安全提示后再试；或 ② 设置环境变量 ZENTAO_WEB_COOKIE "
            "为浏览器已登录状态下复制的 Cookie 请求头，再运行本脚本（不经过脚本内登录）。",
            file=sys.stderr,
        )
        return 10

    # 成功时多为 JSON 或 zin 片段；若仍含明显登录超时则失败
    if "登录已超时" in txt or '"load":"login"' in txt:
        print("失败：会话在用例保存时失效，请重试。", file=sys.stderr)
        return 8

    if "result" in txt and "false" in txt[:200]:
        try:
            j = json.loads(txt)
            if j.get("result") is False:
                print(f"失败：{j.get('message', j)}", file=sys.stderr)
                return 9
        except json.JSONDecodeError:
            pass

    # 用 API 核对附件数量
    try:
        tc2 = fetch_testcase_api(base, tok, args.case_id)
        nfiles = len(tc2.get("files") or {})
        print(f"当前用例附件条目数（API）: {nfiles}（提交前: {files_before}）")
        if nfiles <= files_before:
            print(
                "提示：API 侧附件数量未增加。常见原因：① ZENTAO_WEB_COOKIE 已过期，"
                "请在浏览器重新登录后整段复制更新 Cookie；② 禅道 zin 保存需与浏览器完全一致的交互链，"
                "可先在网页打开一次「编辑用例」再复制 Cookie 后重试。",
                file=sys.stderr,
            )
            return 11
    except Exception:
        pass

    print("已提交编辑请求；请在禅道页面核对附件是否出现。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
