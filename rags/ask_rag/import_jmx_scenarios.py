from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parent
DEFAULT_INPUT = pathlib.Path(r"C:\Users\Reolink\Downloads\接口自动化场景")
DEFAULT_OUTPUT = ROOT / "data" / "supplemental_cases.json"
REPORT_PATH = ROOT / "data" / "jmx_import_report.json"
CORPUS_PATH = ROOT / "corpus" / "api-automation-index.md"
TESTCASES_PATH = ROOT / "data" / "testcases.jsonl"

SCENE_CASE_ID_START = 992_000_001
API_CASE_ID_START = 992_100_001
INDEX_CASE_ID_START = 992_200_001

PUNCT_RE = re.compile(r"[\s\t\r\n,.;:!?，。；：！？、/\\|_=+()\[\]{}<>《》“”\"'`-]+")
CASE_ID_RE = re.compile(r"\b(\d{5,6})\b")
SENSITIVE_ARG_RE = re.compile(
    r"(password|passwd|token|secret|email|client_id|api_key|credential|auth_code)",
    re.I,
)

SETUP_KEYWORDS = (
    "token",
    "心跳",
    "检查服务",
    "存储token",
    "获取后台",
    "2fa",
    "验证码",
    "自定义服务",
    "登录",
    "oauth2",
    "authorization",
    "getverifycode",
    "mfa",
    "seesion_code",
    "session_code",
)

DOMAIN_RULES: list[tuple[str, str]] = [
    ("支付", "支付"),
    ("paypal", "支付"),
    ("adyen", "支付"),
    ("google", "支付"),
    ("cb", "支付"),
    ("p卡", "支付"),
    ("windcave", "支付"),
    ("邮件", "邮件"),
    ("library", "library"),
    ("sim", "SIM"),
    ("4g", "SIM"),
    ("锁卡", "SIM"),
    ("设备", "设备"),
    ("录像", "设备"),
    ("视频", "设备"),
    ("加密", "设备"),
    ("ai", "设备"),
    ("注册", "账户"),
    ("登录", "账户"),
    ("密码", "账户"),
    ("退款", "退款"),
    ("续费", "套餐"),
    ("套餐", "套餐"),
    ("coupon", "优惠"),
    ("优惠", "优惠"),
    ("pd", "优惠"),
    ("补充包", "套餐"),
    ("合并", "套餐"),
    ("流量", "套餐"),
    ("云套餐", "套餐"),
    ("列表", "查询"),
    ("查询", "查询"),
    ("分页", "查询"),
]

HOST_HINTS = {
    "apis.reolink.review": "apis.reolink.review",
    "cloud.reolink.review": "cloud.reolink.review",
    "my.reolink.review": "my.reolink.review",
    "reolink.review": "reolink.review",
}


def configure_output() -> None:
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def normalize(text: Any) -> str:
    return PUNCT_RE.sub("", str(text or "")).lower()


def clean_line(text: Any) -> str:
    return " ".join(str(text or "").split())


def infer_domain(path: str, explicit_domain: str) -> str:
    if explicit_domain:
        domain = explicit_domain.strip()
        for hint, host in HOST_HINTS.items():
            if hint in domain:
                return host
        if domain.startswith("${"):
            return domain
        return domain
    if path.startswith("http://") or path.startswith("https://"):
        return ""
    if "/management/endpoints" in path or path.startswith("/v1.0/"):
        return "apis.reolink.review"
    if path.startswith("/v2/"):
        return "apis.reolink.review"
    if "${ui_exc}" in path:
        return "${ui_exc}"
    return "apis.reolink.review"


def classify_domain_tag(name: str) -> str:
    lowered = name.lower()
    for keyword, tag in DOMAIN_RULES:
        if keyword in lowered:
            return tag
    return "其他"


def is_setup_sampler(testname: str, path: str) -> bool:
    text = f"{testname} {path}".lower()
    return any(keyword in text for keyword in SETUP_KEYWORDS)


def extract_string_prop(parent: ET.Element, name: str) -> str:
    for child in parent.iter("stringProp"):
        if child.get("name") == name:
            return clean_line(child.text or "")
    return ""


def extract_assertions(sampler: ET.Element, parent_map: dict[ET.Element, ET.Element]) -> list[str]:
    assertions: list[str] = []
    current = sampler
    while True:
        parent = parent_map.get(current)
        if parent is None:
            break
        for sibling in list(parent):
            if sibling is sampler:
                continue
            if sibling.tag == "hashTree":
                for node in sibling.iter():
                    if node.tag == "ResponseAssertion":
                        testname = node.get("testname", "ResponseAssertion")
                        parts = [testname]
                        for prop in node.iter("stringProp"):
                            value = clean_line(prop.text or "")
                            if value:
                                parts.append(value)
                        assertions.append(" | ".join(parts))
                    elif node.tag == "JSONPathAssertion":
                        testname = node.get("testname", "JSONPathAssertion")
                        json_path = extract_string_prop(node, "JSON_PATH")
                        expected = extract_string_prop(node, "EXPECTED_VALUE")
                        assertions.append(f"{testname}: {json_path} = {expected}".strip())
                break
        current = parent
        if parent.tag != "hashTree":
            break
    return assertions[:3]


def extract_json_post_vars(sampler: ET.Element, parent_map: dict[ET.Element, ET.Element]) -> list[str]:
    vars_out: list[str] = []
    current = sampler
    while True:
        parent = parent_map.get(current)
        if parent is None:
            break
        for sibling in list(parent):
            if sibling is sampler:
                continue
            if sibling.tag == "hashTree":
                for node in sibling.iter("JSONPostProcessor"):
                    ref = node.get("testname") or extract_string_prop(node, "JSONPostProcessor.referenceNames")
                    if ref:
                        vars_out.append(ref)
                break
        current = parent
        if parent.tag != "hashTree":
            break
    return vars_out[:5]


def extract_arguments(tree: ET.Element) -> list[str]:
    names: list[str] = []
    for args in tree.iter("Arguments"):
        for arg in args.iter("elementProp"):
            if arg.get("elementType") != "Argument":
                continue
            name = extract_string_prop(arg, "Argument.name")
            if not name:
                continue
            if SENSITIVE_ARG_RE.search(name):
                names.append(f"{name}=<脱敏>")
            else:
                names.append(name)
    return names[:30]


def parse_jmx_file(path: pathlib.Path) -> dict[str, Any]:
    tree = ET.parse(path)
    root = tree.getroot()
    parent_map = {child: parent for parent in root.iter() for child in parent}

    plan_name = ""
    for node in root.iter("TestPlan"):
        plan_name = node.get("testname", "") or plan_name

    samplers: list[dict[str, Any]] = []
    for sampler in root.iter("HTTPSamplerProxy"):
        if sampler.get("enabled", "true") == "false":
            continue
        testname = sampler.get("testname", "")
        method = extract_string_prop(sampler, "HTTPSampler.method") or "GET"
        req_path = extract_string_prop(sampler, "HTTPSampler.path")
        domain = extract_string_prop(sampler, "HTTPSampler.domain")
        protocol = extract_string_prop(sampler, "HTTPSampler.protocol")
        host = infer_domain(req_path, domain)
        full_path = req_path
        if host and not req_path.startswith("http"):
            full_path = f"{protocol or 'https'}://{host}{req_path}" if host else req_path
        assertions = extract_assertions(sampler, parent_map)
        post_vars = extract_json_post_vars(sampler, parent_map)
        samplers.append(
            {
                "testname": testname,
                "method": method.upper(),
                "path": req_path,
                "host": host,
                "full_path": full_path,
                "is_setup": is_setup_sampler(testname, req_path),
                "assertions": assertions,
                "post_vars": post_vars,
            }
        )

    return {
        "plan_name": plan_name or path.stem,
        "scene_name": path.stem,
        "relative_path": str(path),
        "arguments": extract_arguments(root),
        "samplers": samplers,
    }


def load_testcase_index() -> dict[int, dict[str, Any]]:
    index: dict[int, dict[str, Any]] = {}
    if not TESTCASES_PATH.exists():
        return index
    for line in TESTCASES_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        index[int(row["case_id"])] = row
    return index


def build_title_index(cases: dict[int, dict[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
    rows: list[tuple[str, dict[str, Any]]] = []
    for case in cases.values():
        rows.append((normalize(case.get("title", "")), case))
    return rows


def extract_script_ids(stem: str) -> list[int]:
    return [int(item) for item in CASE_ID_RE.findall(stem)]


def fuzzy_match_zentao(scene_name: str, title_index: list[tuple[str, dict[str, Any]]]) -> dict[str, Any] | None:
    scene_norm = normalize(scene_name)
    if not scene_norm:
        return None
    best: tuple[float, dict[str, Any]] | None = None
    for title_norm, case in title_index:
        if not title_norm:
            continue
        if scene_norm in title_norm or title_norm in scene_norm:
            score = 0.95
        else:
            score = SequenceMatcher(None, scene_norm, title_norm).ratio()
        if score >= 0.72 and (best is None or score > best[0]):
            best = (score, case)
    return best[1] if best else None


def resolve_links(scene_name: str, testcase_index: dict[int, dict[str, Any]], title_index: list[tuple[str, dict[str, Any]]]) -> dict[str, Any]:
    script_ids = extract_script_ids(scene_name)
    matched_cases: list[dict[str, Any]] = []
    unmatched_ids: list[int] = []

    for case_id in script_ids:
        case = testcase_index.get(case_id)
        if case:
            matched_cases.append(case)
        else:
            unmatched_ids.append(case_id)

    if not matched_cases:
        fuzzy = fuzzy_match_zentao(scene_name, title_index)
        if fuzzy:
            matched_cases.append(fuzzy)

    return {
        "script_ids": script_ids,
        "matched_cases": matched_cases,
        "unmatched_ids": unmatched_ids,
    }


def format_link_info(link_info: dict[str, Any]) -> str:
    parts: list[str] = []
    for case in link_info["matched_cases"]:
        parts.append(
            "关联禅道用例: %s %s (%s)"
            % (
                case.get("case_id"),
                clean_line(case.get("title", "")),
                clean_line(case.get("module_path_text", "")),
            )
        )
    for case_id in link_info["unmatched_ids"]:
        parts.append("脚本内ID(未入KB): %s" % case_id)
    return "; ".join(parts)


def zentao_link(case: dict[str, Any]) -> str:
    case_id = case.get("case_id")
    if case_id:
        return "https://pms.reolink.com.cn/index.php?m=testcase&f=view&caseID=%s" % case_id
    return ""


def compress_scene_steps(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    setup_lines: list[str] = []
    business_lines: list[str] = []
    assertion_lines: list[str] = []

    for idx, sampler in enumerate(parsed["samplers"], 1):
        path = sampler["path"] or sampler["full_path"]
        line = "%s. %s %s (%s)" % (idx, sampler["method"], path, sampler["testname"])
        if sampler["is_setup"]:
            setup_lines.append(line)
        else:
            business_lines.append(line)
        if sampler["assertions"]:
            assertion_lines.append("%s: %s" % (sampler["testname"], "; ".join(sampler["assertions"])))
        if sampler["post_vars"]:
            assertion_lines.append("%s 提取: %s" % (sampler["testname"], ", ".join(sampler["post_vars"])))

    arg_text = ", ".join(parsed["arguments"][:20]) if parsed["arguments"] else "无"
    steps = [
        {
            "index": 1,
            "desc": "场景概述",
            "expect": "接口总数=%s; 前置=%s; 业务=%s; 参数=%s"
            % (len(parsed["samplers"]), len(setup_lines), len(business_lines), arg_text),
        },
        {
            "index": 2,
            "desc": "前置接口序列",
            "expect": "\n".join(setup_lines[:40]) or "无独立前置接口",
        },
        {
            "index": 3,
            "desc": "业务接口序列",
            "expect": "\n".join(business_lines[:40]) or "见前置接口",
        },
        {
            "index": 4,
            "desc": "断言与变量",
            "expect": "\n".join(assertion_lines[:30]) or "默认校验响应成功",
        },
    ]
    return steps


def build_scene_case(
    case_id: int,
    parsed: dict[str, Any],
    input_root: pathlib.Path,
    link_info: dict[str, Any],
) -> dict[str, Any]:
    scene_name = parsed["scene_name"]
    domain_tag = classify_domain_tag(scene_name)
    rel_path = pathlib.Path(parsed["relative_path"])
    try:
        rel_display = str(rel_path.relative_to(input_root))
    except ValueError:
        rel_display = rel_path.name

    steps = compress_scene_steps(parsed)
    all_paths = [sampler["path"] or sampler["full_path"] for sampler in parsed["samplers"]]

    matched = link_info["matched_cases"]
    primary = matched[0] if matched else None
    precondition_parts = [
        "来源: JMeter 接口自动化场景",
        "脚本: %s" % rel_display,
        format_link_info(link_info),
    ]
    keywords_parts = [
        scene_name,
        "接口自动化",
        "jmx",
        domain_tag,
        " ".join(all_paths),
    ]
    if primary:
        keywords_parts.extend(
            [
                str(primary.get("case_id", "")),
                clean_line(primary.get("title", "")),
                clean_line(primary.get("module_path_text", "")),
            ]
        )

    return {
        "case_id": case_id,
        "title": "【接口自动化场景】%s" % scene_name,
        "link": "本地:接口自动化场景/%s" % rel_display.replace("\\", "/"),
        "module_path_text": "补充知识 / 接口自动化 / 组合场景 / %s" % domain_tag,
        "precondition": "\n".join(part for part in precondition_parts if part),
        "keywords": " ".join(part for part in keywords_parts if part),
        "steps": steps,
        "related_case_ids": [int(item["case_id"]) for item in matched],
        "script_ids": link_info["script_ids"],
        "scene_name": scene_name,
        "domain_tag": domain_tag,
        "jmx_path": rel_display,
    }


def api_key(method: str, path: str) -> str:
    return "%s %s" % (method.upper(), path or "/")


def path_prefix(path: str) -> str:
    if not path:
        return "/"
    if path.startswith("http"):
        return path.split("?", 1)[0]
    parts = [part for part in path.split("/") if part and not part.startswith("${")]
    if not parts:
        return "/"
    if parts[0] == "v1.0" and len(parts) > 1:
        return "/".join(parts[:2])
    if parts[0] == "v2" and len(parts) > 1:
        return "/".join(parts[:2])
    return parts[0]


def build_api_cases(api_map: dict[str, dict[str, Any]], testcase_index: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for idx, (key, info) in enumerate(sorted(api_map.items())):
        scene_names = sorted(info["scenes"])
        related_ids = sorted(info["related_case_ids"])
        zentao_lines = []
        for case_id in related_ids[:15]:
            case = testcase_index.get(case_id)
            if case:
                zentao_lines.append("%s %s" % (case_id, clean_line(case.get("title", ""))))

        steps = [
            {
                "index": 1,
                "desc": "接口定义",
                "expect": "METHOD=%s; PATH=%s; HOST=%s"
                % (info["method"], info["path"], info.get("host", "")),
            },
            {
                "index": 2,
                "desc": "引用场景",
                "expect": "\n".join(scene_names[:20]) or "无",
            },
            {
                "index": 3,
                "desc": "关联禅道用例",
                "expect": "\n".join(zentao_lines) or "无直接关联",
            },
        ]
        cases.append(
            {
                "case_id": API_CASE_ID_START + idx,
                "title": "【接口自动化-单接口】%s" % key,
                "link": "本地:接口自动化场景/api-index#%s" % normalize(key),
                "module_path_text": "补充知识 / 接口自动化 / 单接口 / %s" % path_prefix(info["path"]),
                "precondition": "来源: JMeter 接口自动化脚本聚合",
                "keywords": "%s 接口自动化 单接口 %s" % (key, " ".join(scene_names[:10])),
                "steps": steps,
            }
        )
    return cases


def build_index_cases(
    scene_cases: list[dict[str, Any]],
    api_cases: list[dict[str, Any]],
    testcase_index: dict[int, dict[str, Any]],
) -> list[dict[str, Any]]:
    domain_groups: dict[str, list[str]] = defaultdict(list)
    for case in scene_cases:
        domain_groups[case["domain_tag"]].append(case["scene_name"])

    index_cases: list[dict[str, Any]] = []
    overview_lines = []
    for domain in sorted(domain_groups.keys()):
        names = domain_groups[domain]
        overview_lines.append("%s (%s)" % (domain, len(names)))
        body = "\n".join("- %s" % name for name in sorted(names))
        index_cases.append(
            {
                "case_id": INDEX_CASE_ID_START + len(index_cases),
                "title": "【接口自动化索引】领域总览 / %s" % domain,
                "link": "本地:接口自动化场景/index#%s" % domain,
                "module_path_text": "补充知识 / 接口自动化 / 索引",
                "precondition": "接口自动化场景领域归类",
                "keywords": "接口自动化 索引 %s %s" % (domain, " ".join(names[:20])),
                "steps": [
                    {"index": 1, "desc": "场景数量", "expect": str(len(names))},
                    {"index": 2, "desc": "场景列表", "expect": body[:8000]},
                ],
            }
        )

    crosswalk_lines = []
    for case in scene_cases:
        if not case.get("related_case_ids"):
            continue
        for case_id in case["related_case_ids"]:
            zt = testcase_index.get(case_id, {})
            crosswalk_lines.append(
                "%s | %s | 禅道 %s %s"
                % (
                    case["scene_name"],
                    case["jmx_path"],
                    case_id,
                    clean_line(zt.get("title", "")),
                )
            )

    index_cases.insert(
        0,
        {
            "case_id": INDEX_CASE_ID_START,
            "title": "【接口自动化索引】全场景总览",
            "link": "本地:接口自动化场景/index",
            "module_path_text": "补充知识 / 接口自动化 / 索引",
            "precondition": "JMeter 接口自动化场景导入总览",
            "keywords": "接口自动化 索引 总览 jmx 场景 API",
            "steps": [
                {"index": 1, "desc": "场景总数", "expect": str(len(scene_cases))},
                {"index": 2, "desc": "单接口条目数", "expect": str(len(api_cases))},
                {"index": 3, "desc": "领域分布", "expect": ", ".join(overview_lines)},
            ],
        },
    )

    unmatched_lines = []
    for case in scene_cases:
        for script_id in case.get("script_ids", []):
            if script_id not in case.get("related_case_ids", []):
                unmatched_lines.append("%s | 脚本ID %s" % (case["scene_name"], script_id))

    index_cases.append(
        {
            "case_id": INDEX_CASE_ID_START + len(index_cases),
            "title": "【接口自动化索引】禅道串联交叉索引",
            "link": "本地:接口自动化场景/index#zentao",
            "module_path_text": "补充知识 / 接口自动化 / 索引",
            "precondition": "JMX 场景与禅道用例关联关系",
            "keywords": "接口自动化 禅道 串联 关联 case_id",
            "steps": [
                {
                    "index": 1,
                    "desc": "已关联条目",
                    "expect": "\n".join(crosswalk_lines[:200]) or "暂无",
                },
                {
                    "index": 2,
                    "desc": "未入KB脚本ID",
                    "expect": "\n".join(unmatched_lines[:200]) or "无",
                },
            ],
        },
    )
    return index_cases


def write_corpus_markdown(
    scene_cases: list[dict[str, Any]],
    api_cases: list[dict[str, Any]],
    report: dict[str, Any],
) -> None:
    lines = [
        "# 接口自动化场景知识索引",
        "",
        "- 生成时间: %s" % datetime.now().isoformat(timespec="seconds"),
        "- 场景数: %s" % len(scene_cases),
        "- 单接口数: %s" % len(api_cases),
        "- 解析失败: %s" % len(report.get("parse_errors", [])),
        "",
        "## 领域分布",
        "",
    ]
    domain_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for case in scene_cases:
        domain_groups[case["domain_tag"]].append(case)
    for domain in sorted(domain_groups.keys()):
        lines.append("### %s (%s)" % (domain, len(domain_groups[domain])))
        lines.append("")
        for case in sorted(domain_groups[domain], key=lambda x: x["scene_name"]):
            rel = case.get("jmx_path", "")
            rel_ids = case.get("related_case_ids") or []
            rel_text = ("; 禅道 " + ",".join(str(item) for item in rel_ids)) if rel_ids else ""
            lines.append("- `%s` — %s%s" % (rel, case["scene_name"], rel_text))
        lines.append("")

    lines.extend(["## 单接口 Top 列表", ""])
    for case in api_cases[:40]:
        expect = ""
        if case.get("steps"):
            expect = case["steps"][1].get("expect", "")
        first_scene = expect.split("\n", 1)[0] if expect else ""
        lines.append("- %s — 示例场景: %s" % (case["title"].replace("【接口自动化-单接口】", ""), first_scene))
    lines.append("")

    CORPUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    CORPUS_PATH.write_text("\n".join(lines), encoding="utf-8")


def merge_supplemental(existing: list[dict[str, Any]], incoming: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged = {int(item["case_id"]): item for item in existing if item.get("case_id") is not None}
    for item in incoming:
        merged[int(item["case_id"])] = item
    return [merged[key] for key in sorted(merged.keys())]


def import_jmx_scenarios(
    input_dir: pathlib.Path,
    output_path: pathlib.Path,
    merge: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    jmx_files = sorted(input_dir.rglob("*.jmx"))
    testcase_index = load_testcase_index()
    title_index = build_title_index(testcase_index)

    scene_cases: list[dict[str, Any]] = []
    api_map: dict[str, dict[str, Any]] = {}
    parse_errors: list[dict[str, str]] = []

    for offset, jmx_path in enumerate(jmx_files):
        try:
            parsed = parse_jmx_file(jmx_path)
        except Exception as exc:
            parse_errors.append({"file": str(jmx_path), "error": str(exc)})
            continue

        link_info = resolve_links(parsed["scene_name"], testcase_index, title_index)
        scene_case = build_scene_case(SCENE_CASE_ID_START + offset, parsed, input_dir, link_info)
        scene_cases.append(scene_case)

        for sampler in parsed["samplers"]:
            path = sampler["path"] or sampler["full_path"]
            if not path:
                continue
            key = api_key(sampler["method"], path)
            entry = api_map.setdefault(
                key,
                {
                    "method": sampler["method"],
                    "path": path,
                    "host": sampler.get("host", ""),
                    "scenes": set(),
                    "related_case_ids": set(),
                },
            )
            entry["scenes"].add(parsed["scene_name"])
            for case_id in scene_case.get("related_case_ids", []):
                entry["related_case_ids"].add(case_id)

    api_cases = build_api_cases(api_map, testcase_index)
    index_cases = build_index_cases(scene_cases, api_cases, testcase_index)
    incoming_cases = scene_cases + api_cases + index_cases

    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "input_dir": str(input_dir),
        "jmx_total": len(jmx_files),
        "scene_total": len(scene_cases),
        "api_total": len(api_cases),
        "index_total": len(index_cases),
        "supplemental_total": len(incoming_cases),
        "parse_errors": parse_errors,
        "domain_distribution": dict(
            sorted(
                {tag: sum(1 for case in scene_cases if case["domain_tag"] == tag) for tag in {c["domain_tag"] for c in scene_cases}}.items(),
                key=lambda item: -item[1],
            )
        ),
        "linked_zentao_total": sum(1 for case in scene_cases if case.get("related_case_ids")),
    }

    if dry_run:
        return report

    existing: list[dict[str, Any]] = []
    if merge and output_path.exists():
        payload = json.loads(output_path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            existing = payload

    final_cases = merge_supplemental(existing, incoming_cases) if merge else incoming_cases
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(final_cases, ensure_ascii=False, indent=2), encoding="utf-8")
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    write_corpus_markdown(scene_cases, api_cases, report)
    return report


def main() -> int:
    configure_output()
    parser = argparse.ArgumentParser(description="将 JMeter JMX 接口自动化场景导入 supplemental 知识库。")
    parser.add_argument("--input", type=pathlib.Path, default=DEFAULT_INPUT, help="JMX 场景目录")
    parser.add_argument("--output", type=pathlib.Path, default=DEFAULT_OUTPUT, help="supplemental_cases.json 输出路径")
    parser.add_argument("--merge", action="store_true", help="与已有 supplemental_cases.json 合并")
    parser.add_argument("--dry-run", action="store_true", help="仅统计，不写文件")
    args = parser.parse_args()

    if not args.input.exists():
        print("输入目录不存在: %s" % args.input, file=sys.stderr)
        return 1

    report = import_jmx_scenarios(args.input, args.output, merge=args.merge, dry_run=args.dry_run)
    print(
        "JMX 导入完成: jmx=%s scenes=%s apis=%s index=%s supplemental=%s errors=%s"
        % (
            report["jmx_total"],
            report["scene_total"],
            report["api_total"],
            report["index_total"],
            report["supplemental_total"],
            len(report["parse_errors"]),
        )
    )
    if not args.dry_run:
        print("输出: %s" % args.output)
        print("报告: %s" % REPORT_PATH)
        print("语料: %s" % CORPUS_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
