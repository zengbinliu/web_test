from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import sys
from collections import Counter
from typing import Any

from rag_core import RAGIndex, build_or_load_index, format_context_blocks, hybrid_search_cases
from rag_llm import generate_rag_answer, llm_available, synthesize_extractive_answer


ROOT = pathlib.Path(__file__).resolve().parent
RAG_INDEX: RAGIndex | None = None
KB_PATH = ROOT / "data" / "testcases.jsonl"
MANIFEST_PATH = ROOT / "data" / "manifest.json"
SUPPLEMENTAL_CASES_PATH = ROOT / "data" / "supplemental_cases.json"


def kb_logic_patches_path() -> pathlib.Path:
    configured = os.environ.get("REOLINK_KB_PATCHES_PATH", "").strip()
    if configured:
        return pathlib.Path(configured)
    return ROOT / "kb_logic_patches.jsonl"
PUNCT_RE = re.compile(r"[\s\t\r\n,.;:!?，。；：！？、/\\|_=+()\[\]{}<>《》“”\"'`-]+")
CJK_RE = re.compile(r"[\u4e00-\u9fff]")
PACKAGE_TYPE_RE = re.compile(r"(?:[A-Za-z0-9\u4e00-\u9fff\-]+套餐(?:-[A-Za-z0-9\u4e00-\u9fff]+)?|补充包)")
PACKAGE_TYPE_CANDIDATES = [
    "云套餐-仅带图",
    "付费云套餐",
    "免费云套餐",
    "云促续套餐",
    "云存储套餐",
    "付费流量套餐",
    "免费流量套餐",
    "4G流量套餐",
    "付费合并套餐",
    "免费合并套餐",
    "云套餐",
    "流量套餐",
    "合并套餐",
    "补充包",
    "免费套餐",
    "普通套餐",
    "legacy套餐",
    "Legacy套餐",
    "定制套餐",
]
PACKAGE_TYPE_STOP_TERMS = {
    "套餐",
    "当前套餐",
    "该套餐",
    "此套餐",
    "所有套餐",
    "不同套餐",
    "相同套餐",
    "对应套餐",
    "可切换套餐",
    "推荐套餐",
    "购买套餐",
    "购买新套餐",
    "切换套餐",
    "套餐类型",
    "套餐选择",
    "套餐页面",
    "套餐列表",
    "套餐详情",
    "套餐展示",
    "套餐导出",
    "套餐导入",
    "套餐领取",
    "套餐管理",
    "套餐组",
    "云套餐组",
    "已有套餐",
    "一个套餐",
    "多个套餐",
    "某套餐",
    "某个套餐",
}
PACKAGE_TYPE_STOP_TERMS_NORM: set[str] | None = None
SWITCH_ACTION_TERMS = ("切换", "切到", "切成", "切换到", "切换为", "切换成", "切回", "转到", "转成")
SWITCH_POSITIVE_TERMS = ("正常切换", "切换成功", "可切换", "仅可选择", "仅能选择", "仍为激活", "可选择支持该设备的套餐")
SWITCH_NEGATIVE_TERMS = ("不能切换", "不可切换", "无法切换", "不显示", "不展示", "不可选择")


def configure_output() -> None:
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def normalize(text: Any) -> str:
    return PUNCT_RE.sub("", str(text or "")).lower()


def get_package_type_stop_terms_norm() -> set[str]:
    global PACKAGE_TYPE_STOP_TERMS_NORM
    if PACKAGE_TYPE_STOP_TERMS_NORM is None:
        PACKAGE_TYPE_STOP_TERMS_NORM = {normalize(item) for item in PACKAGE_TYPE_STOP_TERMS}
    return PACKAGE_TYPE_STOP_TERMS_NORM


def unique_keep_order(items: list[str]) -> list[str]:
    seen = set()
    output = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            output.append(item)
    return output


def split_terms(text: str) -> list[str]:
    parts = [part.strip() for part in PUNCT_RE.split(text or "") if part.strip()]
    compact = normalize(text)
    if compact:
        parts.append(compact)
        if CJK_RE.search(compact) and len(compact) <= 40:
            for size in (2, 3, 4):
                if len(compact) >= size:
                    for idx in range(len(compact) - size + 1):
                        parts.append(compact[idx : idx + size])
    return unique_keep_order(parts)


def display_terms(text: str) -> list[str]:
    parts = [part.strip() for part in PUNCT_RE.split(text or "") if part.strip()]
    if parts:
        return unique_keep_order(parts)
    stripped = text.strip()
    return [stripped] if stripped else []


def clean_package_type(term: str) -> str | None:
    term = str(term or "").strip().strip("，。；：,.;:()（）[]【】<>《》")
    if not term:
        return None
    if "补充包" in term:
        return "补充包"
    if not term.endswith("套餐"):
        return None

    norm = normalize(term)
    if norm in get_package_type_stop_terms_norm():
        return None

    bad_contains = (
        "页面",
        "金额",
        "列表",
        "详情",
        "展示",
        "选择",
        "管理",
        "导出",
        "导入",
        "领取",
        "购买页",
        "首页",
        "按钮",
        "订单",
        "邮件",
        "链接",
        "切换为",
        "进入",
        "查看",
        "删除",
        "取消",
        "创建",
        "修改",
        "设置",
    )
    if any(part in term for part in bad_contains):
        return None

    return term


def extract_package_types(text: str) -> list[str]:
    candidates = []
    for raw in PACKAGE_TYPE_RE.findall(text or ""):
        cleaned = clean_package_type(raw)
        if cleaned:
            candidates.append(cleaned)
    return unique_keep_order(candidates)


def find_package_mentions(text: str) -> list[tuple[int, str]]:
    ordered: list[tuple[int, str]] = []
    occupied: set[int] = set()
    for candidate in sorted(PACKAGE_TYPE_CANDIDATES, key=len, reverse=True):
        normalized = "legacy套餐" if candidate == "Legacy套餐" else candidate
        start = 0
        while True:
            idx = text.find(candidate, start)
            if idx < 0:
                break
            end = idx + len(candidate)
            if not any(pos in occupied for pos in range(idx, end)):
                ordered.append((idx, normalized))
                for pos in range(idx, end):
                    occupied.add(pos)
            start = idx + 1
    ordered.sort(key=lambda item: item[0])

    result: list[tuple[int, str]] = []
    seen = set()
    for idx, name in ordered:
        if name not in seen:
            seen.add(name)
            result.append((idx, name))
    return result


def parse_switch_entities(question: str) -> tuple[str, str] | None:
    q = question.strip().strip("？?。")
    if not any(term in q for term in SWITCH_ACTION_TERMS):
        return None
    mentions = find_package_mentions(q)
    if len(mentions) < 2:
        return None
    source = mentions[0][1]
    target = mentions[1][1]
    if not source or not target:
        return None
    return source, target


def is_switch_question(question: str) -> bool:
    return parse_switch_entities(question) is not None


def is_package_type_question(question: str) -> bool:
    q = question.strip()
    if not q or ("套餐" not in q and "补充包" not in q):
        return False
    if "限制" in q:
        return False
    return any(
        phrase in q
        for phrase in (
            "有几种套餐类型",
            "多少种套餐类型",
            "哪几种套餐类型",
            "有哪些套餐类型",
            "有哪几种套餐",
            "有多少种套餐",
        )
    ) or ("类型" in q and any(word in q for word in ("几种", "多少种", "哪几种", "有哪些")))


def is_effective_question(question: str) -> bool:
    q = question.strip()
    return any(
        phrase in q
        for phrase in (
            "什么时候生效",
            "何时生效",
            "多久生效",
            "什么时候开始生效",
            "何时开始生效",
            "生效时间",
        )
    ) or ("生效" in q and "什么时候" in q)


def is_limitation_question(question: str) -> bool:
    q = question.strip()
    if is_switch_question(q):
        return False
    return any(word in q for word in ("限制", "限制条件", "有什么限制", "有哪些限制", "不能", "不可", "仅能", "只能", "上限", "最多"))


def parse_compare_entities(question: str) -> tuple[str, str] | None:
    q = question.strip().strip("？?。")
    patterns = (
        r"(.+?)[和与](.+?)(?:有|的)?区别是什么",
        r"(.+?)[和与](.+?)有什么区别",
        r"(.+?)[和与](.+?)有哪些区别",
        r"(.+?)[和与](.+?)区别",
    )
    for pattern in patterns:
        match = re.search(pattern, q)
        if match:
            left = match.group(1).strip(" ，。；：,.;:")
            right = match.group(2).strip(" ，。；：,.;:")
            if left and right:
                return left, right
    return None


def intent_terms(question: str) -> list[str]:
    terms: list[str] = []
    switch_entities = parse_switch_entities(question)
    if switch_entities:
        source, target = switch_entities
        terms.extend([source, target, "切换", "切换到", "切换为", "切换成", "正常切换", "可切换", "不显示", "不可选择"])
    if is_effective_question(question):
        terms.extend(["生效", "到期后", "立即生效", "下个周期", "有效期", "购买新套餐"])
    if is_limitation_question(question):
        terms.extend(["限制", "仅能", "只能", "不可", "不能", "不展示", "最多", "格式不正确", "不能为空"])
    compare_entities = parse_compare_entities(question)
    if compare_entities:
        terms.extend(list(compare_entities))
    return unique_keep_order(terms)


def load_manifest() -> dict[str, Any]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def load_case_rows(path: pathlib.Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    if path.suffix.lower() == ".jsonl":
        rows = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
        return rows

    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("cases", "items", "rows"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def prepare_case(case: dict[str, Any]) -> dict[str, Any]:
    case = dict(case)
    case["source_type"] = case.get("source_type") or "testcase"
    title = case.get("title", "")
    module_path = case.get("module_path_text", "")
    precondition = case.get("precondition", "")
    keywords = case.get("keywords", "")
    step_descs = [step.get("desc", "") for step in case.get("steps", [])]
    step_expects = [step.get("expect", "") for step in case.get("steps", [])]
    bag_text = "\n".join([title, module_path, precondition, keywords] + step_descs + step_expects)
    case["_search"] = {
        "case_id": str(case.get("case_id", "")),
        "title_norm": normalize(title),
        "module_norm": normalize(module_path),
        "precondition_norm": normalize(precondition),
        "keywords_norm": normalize(keywords),
        "step_desc_norms": [normalize(item) for item in step_descs],
        "step_expect_norms": [normalize(item) for item in step_expects],
        "bag_norm": normalize(bag_text),
    }
    return case


def patch_record_to_case(row: dict[str, Any], idx: int) -> dict[str, Any]:
    summary = str(row.get("summary", "")).strip() or "知识库补丁"
    correction = str(row.get("correction", "")).strip()
    module_hint = str(row.get("module_hint", "")).strip()
    author = str(row.get("author", "")).strip()
    submitted = str(row.get("submitted_at", "")).strip()
    case_id = 993000000 + idx
    module_suffix = module_hint if module_hint else "通用"
    precondition_parts = []
    if submitted:
        precondition_parts.append("提交时间（UTC）：%s" % submitted)
    if author:
        precondition_parts.append("提交人：%s" % author)
    precondition = (
        "\n".join(precondition_parts)
        if precondition_parts
        else "来源于 MCP 写入的 kb_logic_patches.jsonl。"
    )
    title = "【知识补丁】%s" % summary
    keywords = " ".join(
        unique_keep_order([summary, correction[:400], module_hint, author, "补丁", "MCP", "逻辑更正"])
    )
    return {
        "case_id": case_id,
        "title": title,
        "link": "本地补丁：kb_logic_patches.jsonl",
        "module_path_text": "补充知识 / MCP逻辑补丁 / %s" % module_suffix,
        "precondition": precondition,
        "keywords": keywords,
        "steps": [
            {
                "index": 1,
                "name": "1",
                "type": "step",
                "desc": summary,
                "expect": correction,
            }
        ],
        "source_type": "patch",
    }


def load_patch_cases() -> list[dict[str, Any]]:
    path = kb_logic_patches_path()
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return [patch_record_to_case(row, idx) for idx, row in enumerate(rows)]


def load_cases() -> list[dict[str, Any]]:
    cases = []
    for path, source_type in (
        (KB_PATH, "testcase"),
        (SUPPLEMENTAL_CASES_PATH, "supplemental"),
    ):
        for row in load_case_rows(path):
            case = dict(row)
            case.setdefault("source_type", source_type)
            cases.append(prepare_case(case))
    for case in load_patch_cases():
        cases.append(prepare_case(case))
    return cases


def is_supplemental_case(case: dict[str, Any]) -> bool:
    return case.get("source_type") == "supplemental"


def is_kb_patch_case(case: dict[str, Any]) -> bool:
    return case.get("source_type") == "patch"


def matched_entry_label(case: dict[str, Any]) -> str:
    if is_kb_patch_case(case):
        return "命中补丁"
    if is_supplemental_case(case):
        return "命中知识"
    return "命中用例"


def reference_entry_label(case: dict[str, Any]) -> str:
    if is_kb_patch_case(case):
        return "依据补丁"
    if is_supplemental_case(case):
        return "依据知识"
    return "依据用例"


def score_case(case: dict[str, Any], question: str, module_filter: str = "") -> tuple[int, list[str]]:
    search = case["_search"]
    question = question.strip()
    question_norm = normalize(question)
    if not question_norm:
        return 0, []

    module_filter_norm = normalize(module_filter)
    if module_filter_norm and module_filter_norm not in search["module_norm"]:
        return 0, []

    visible_terms = {normalize(item): item for item in display_terms(question)}
    boosted_terms = intent_terms(question)
    switch_entities = parse_switch_entities(question)

    score = 0
    hits: list[str] = []

    if question == search["case_id"] or question_norm == search["case_id"]:
        score += 1000
        hits.append(f"case:{search['case_id']}")

    if question_norm in search["title_norm"]:
        score += 120
        hits.append("标题")
    if question_norm in search["module_norm"]:
        score += 70
        hits.append("模块")
    if question_norm in search["precondition_norm"]:
        score += 50
        hits.append("前置条件")
    if question_norm in search["keywords_norm"]:
        score += 40
        hits.append("关键词")
    if question_norm in search["bag_norm"]:
        score += 25

    step_desc_hits = sum(1 for item in search["step_desc_norms"] if question_norm in item)
    step_expect_hits = sum(1 for item in search["step_expect_norms"] if question_norm in item)
    if step_desc_hits:
        score += min(60, step_desc_hits * 18)
        hits.append("步骤")
    if step_expect_hits:
        score += min(60, step_expect_hits * 20)
        hits.append("预期")

    if switch_entities:
        source, target = switch_entities
        source_norm = normalize(source)
        target_norm = normalize(target)
        title_norm = search["title_norm"]
        if source_norm in title_norm:
            score += 22
        if target_norm in title_norm:
            score += 22
        if source_norm in title_norm and target_norm in title_norm and "切换" in title_norm:
            score += 160
            hits.append(f"{source}->{target}")

        switch_line_hits = 0
        positive_hits = 0
        negative_hits = 0
        for line_norm in [*search["step_desc_norms"], *search["step_expect_norms"]]:
            if source_norm in line_norm and target_norm in line_norm and any(term in line_norm for term in SWITCH_ACTION_TERMS):
                switch_line_hits += 1
            if source_norm in line_norm and target_norm in line_norm and any(term in line_norm for term in SWITCH_POSITIVE_TERMS):
                positive_hits += 1
            if source_norm in line_norm and target_norm in line_norm and any(term in line_norm for term in SWITCH_NEGATIVE_TERMS):
                negative_hits += 1
        if switch_line_hits:
            score += 180 + min(120, switch_line_hits * 35)
            hits.append(f"{source}->{target}")
        if positive_hits:
            score += min(90, positive_hits * 35)
        if negative_hits:
            score += min(90, negative_hits * 35)

    for term in boosted_terms:
        term_norm = normalize(term)
        if len(term_norm) < 2:
            continue
        if term_norm in search["title_norm"]:
            score += 18
        if term_norm in search["module_norm"]:
            score += 10
        if term_norm in search["precondition_norm"]:
            score += 8
        desc_count = sum(1 for item in search["step_desc_norms"] if term_norm in item)
        expect_count = sum(1 for item in search["step_expect_norms"] if term_norm in item)
        if desc_count:
            score += min(18, desc_count * 5)
        if expect_count:
            score += min(24, expect_count * 6)

    for term in split_terms(question):
        term_norm = normalize(term)
        if len(term_norm) < 2:
            continue
        matched = False
        if term_norm in search["title_norm"]:
            score += 12
            matched = True
        if term_norm in search["module_norm"]:
            score += 7
            matched = True
        if term_norm in search["precondition_norm"]:
            score += 5
            matched = True
        if term_norm in search["keywords_norm"]:
            score += 5
            matched = True

        desc_count = sum(1 for item in search["step_desc_norms"] if term_norm in item)
        expect_count = sum(1 for item in search["step_expect_norms"] if term_norm in item)
        if desc_count:
            score += min(12, desc_count * 3)
            matched = True
        if expect_count:
            score += min(12, expect_count * 3)
            matched = True

        if matched and term_norm in visible_terms:
            hits.append(term)

    return score, unique_keep_order(hits)


def get_rag_index(cases: list[dict[str, Any]], rebuild: bool = False) -> RAGIndex:
    global RAG_INDEX
    if RAG_INDEX is not None and not rebuild:
        return RAG_INDEX
    RAG_INDEX = build_or_load_index(cases, rebuild=rebuild)
    return RAG_INDEX


def search_cases(
    cases: list[dict[str, Any]],
    question: str,
    top_n: int,
    module_filter: str = "",
) -> list[dict[str, Any]]:
    results = []
    for case in cases:
        score, hits = score_case(case, question, module_filter=module_filter)
        if score > 0:
            results.append({"case": case, "score": score, "hits": hits})
    results.sort(
        key=lambda item: (
            -item["score"],
            item["case"].get("module_path_text", ""),
            item["case"].get("case_id", 0),
        )
    )
    return results[:top_n]


def search_cases_with_mode(
    cases: list[dict[str, Any]],
    question: str,
    top_n: int,
    module_filter: str = "",
    *,
    use_rag: bool = True,
    rebuild_index: bool = False,
) -> list[dict[str, Any]]:
    if not use_rag:
        return search_cases(cases, question, top_n=top_n, module_filter=module_filter)
    index = get_rag_index(cases, rebuild=rebuild_index)
    return hybrid_search_cases(
        cases,
        question,
        top_n=top_n,
        module_filter=module_filter,
        index=index,
        keyword_search=search_cases,
    )


def summarize_logic(results: list[dict[str, Any]]) -> list[str]:
    if not results:
        return []

    sample_cases = [item["case"] for item in results[:5]]
    module_counts = Counter(case.get("module_path_text", "") for case in sample_cases if case.get("module_path_text"))
    precondition_counts = Counter()
    step_counts = Counter()
    expect_counts = Counter()

    for case in sample_cases:
        if case.get("precondition"):
            for line in case["precondition"].splitlines():
                if line.strip():
                    precondition_counts[line.strip()] += 1
        for step in case.get("steps", []):
            for line in str(step.get("desc", "")).splitlines():
                if line.strip():
                    step_counts[line.strip()] += 1
            for line in str(step.get("expect", "")).splitlines():
                if line.strip():
                    expect_counts[line.strip()] += 1

    lines = ["归纳逻辑:"]
    if module_counts:
        top_modules = [f"{text} ({count})" for text, count in module_counts.most_common(2)]
        lines.append("- 高频模块: %s" % " | ".join(top_modules))
    if precondition_counts:
        top_preconditions = [text for text, _count in precondition_counts.most_common(2)]
        lines.append("- 常见前置条件: %s" % " | ".join(top_preconditions))
    if step_counts:
        top_steps = [text for text, _count in step_counts.most_common(3)]
        lines.append("- 常见步骤: %s" % " | ".join(top_steps))
    if expect_counts:
        top_expects = [text for text, _count in expect_counts.most_common(3)]
        lines.append("- 常见预期: %s" % " | ".join(top_expects))
    return lines


def iter_case_lines(case: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    if case.get("precondition"):
        lines.extend([line.strip() for line in str(case["precondition"]).splitlines() if line.strip()])
    for step in case.get("steps", []):
        for field in ("desc", "expect"):
            text = str(step.get(field, "") or "")
            for line in text.splitlines():
                line = line.strip()
                if line:
                    lines.append(line)
    return lines


def compress_text(text: str, limit: int = 90) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def select_evidence_lines(question: str, results: list[dict[str, Any]], limit: int = 20) -> list[str]:
    query_terms = [normalize(item) for item in display_terms(question) + intent_terms(question) if normalize(item)]
    seen = set()
    picked: list[str] = []
    for item in results[:8]:
        for line in iter_case_lines(item["case"]):
            line_norm = normalize(line)
            if not line_norm or line_norm in seen:
                continue
            if query_terms and not any(term in line_norm for term in query_terms if len(term) >= 2):
                continue
            seen.add(line_norm)
            picked.append(line)
            if len(picked) >= limit:
                return picked
    return picked


def build_package_type_answer(question: str, results: list[dict[str, Any]]) -> list[str]:
    if not is_package_type_question(question):
        return []

    texts = []
    for item in results[:10]:
        case = item["case"]
        texts.extend([case.get("title", ""), case.get("precondition", "")])
        for step in case.get("steps", []):
            texts.extend([step.get("desc", ""), step.get("expect", "")])

    joined_text = "\n".join(texts)
    candidates = []
    for item in PACKAGE_TYPE_CANDIDATES:
        if item in joined_text:
            normalized = "legacy套餐" if item == "Legacy套餐" else item
            candidates.append(normalized)

    if not candidates:
        for text in texts:
            candidates.extend(extract_package_types(text))

    candidates = unique_keep_order(candidates)
    if not candidates:
        return []

    return [
        "结论:",
        "- 从当前高相关用例看，套餐相关类型至少有 %s 种：%s。"
        % (len(candidates), "、".join(candidates)),
    ]


def build_effective_answer(question: str, results: list[dict[str, Any]]) -> list[str]:
    if not is_effective_question(question):
        return []

    evidence_lines = select_evidence_lines(question, results, limit=30)
    if not evidence_lines:
        return []

    if any("有效期同购买新套餐" in line for line in evidence_lines):
        has_addon = any("补充包仍关联订阅" in line for line in evidence_lines)
        answer = "结论:"
        detail = "- 从当前高相关用例看，在已过期套餐切换场景下，切换后按新购套餐生效，有效期与购买新套餐一致。"
        if has_addon:
            detail = detail[:-1] + "；若存在未过期且未用完的补充包，补充包仍关联订阅。"
        return [answer, detail]

    priority_phrases = ("立即生效", "当前套餐到期后", "到期后", "下个周期", "次日生效", "生效时间", "有效期")
    ranked = [line for line in evidence_lines if any(phrase in line for phrase in priority_phrases)]
    if ranked:
        return ["结论:", "- %s" % compress_text(ranked[0], 120)]

    return []


def build_limitation_answer(question: str, results: list[dict[str, Any]]) -> list[str]:
    if not is_limitation_question(question):
        return []

    evidence_lines = select_evidence_lines(question, results, limit=40)
    if not evidence_lines:
        return []

    points: list[str] = []
    if any("最多仅能续费" in line or "仅能续费" in line or "续费限制" in line for line in evidence_lines):
        points.append("常见限制之一是续费上限，部分场景会限制最多可续费周期数。")
    if any("不展示" in line or "不可见" in line or "不可用" in line or "不能购买" in line for line in evidence_lines):
        points.append("不可切换、不可见、不可用或被 disable 的套餐，通常不会在前台列表展示或无法购买。")
    if any("格式不正确" in line or "不能为空" in line or "置灰" in line for line in evidence_lines):
        points.append("后台导入/批量编辑时，限制字段还有格式、必填和置灰校验，填错会直接失败。")
    if any("一个账户同时仅能订阅一个且仅能订阅一次" in line for line in evidence_lines):
        points.append("部分免费套餐还存在“一个账户仅能订阅一次/一个”的使用限制，并会联动续费限制。")

    points = unique_keep_order(points)
    if not points:
        points = ["当前高相关用例显示，套餐限制主要集中在使用限制、续费限制和前台可见/可切换限制。"]

    return ["结论:"] + ["- %s" % point for point in points[:3]]


def short_module_path(case: dict[str, Any]) -> str:
    parts = [part.strip() for part in str(case.get("module_path_text", "")).split(" / ") if part.strip()]
    if len(parts) >= 2:
        return " / ".join(parts[-2:])
    return case.get("module_path_text", "")


def switch_direction(text_norm: str, source_norm: str, target_norm: str) -> int:
    if not text_norm or not any(term in text_norm for term in SWITCH_ACTION_TERMS):
        return 0
    source_pos = text_norm.find(source_norm)
    target_pos = text_norm.find(target_norm)
    if source_pos >= 0 and target_pos >= 0:
        if source_pos < target_pos:
            return 1
        if target_pos < source_pos:
            return -1
    return 0


def collect_switch_evidence(results: list[dict[str, Any]], source: str, target: str) -> list[dict[str, Any]]:
    source_norm = normalize(source)
    target_norm = normalize(target)
    evidences: list[dict[str, Any]] = []
    for item in results[:12]:
        case = item["case"]
        title_norm = normalize(case.get("title", ""))
        precondition_norm = normalize(case.get("precondition", ""))
        module_norm = normalize(case.get("module_path_text", ""))
        title_dir = switch_direction(title_norm, source_norm, target_norm)
        reverse_title_dir = switch_direction(title_norm, target_norm, source_norm)
        case_has_source = source_norm in title_norm or source_norm in precondition_norm or source_norm in module_norm
        case_has_target = target_norm in title_norm or target_norm in precondition_norm or target_norm in module_norm
        title_bonus = 20 if title_dir == 1 else 0
        for step in case.get("steps", []):
            desc = str(step.get("desc", "") or "")
            expect = str(step.get("expect", "") or "")
            desc_norm = normalize(desc)
            expect_norm = normalize(expect)
            combined_norm = desc_norm + " " + expect_norm
            line_dir = switch_direction(combined_norm, source_norm, target_norm)
            reverse_line_dir = switch_direction(combined_norm, target_norm, source_norm)
            line_has_switch = any(term in desc_norm or term in expect_norm for term in SWITCH_ACTION_TERMS)
            line_has_target = target_norm in desc_norm or target_norm in expect_norm
            directional_match = line_dir == 1 or (
                title_dir == 1 and reverse_line_dir != 1 and reverse_title_dir != 1 and line_has_switch and line_has_target
            )
            if directional_match:
                positive = any(term in expect_norm or term in desc_norm for term in SWITCH_POSITIVE_TERMS)
                negative = any(term in expect_norm or term in desc_norm for term in SWITCH_NEGATIVE_TERMS)
                if "不能切换" in title_norm or "不可切换" in title_norm:
                    negative = True
                if "正常切换" in title_norm or "切换成功" in title_norm:
                    positive = True
                polarity = "positive" if positive and not negative else "negative" if negative and not positive else "mixed"
                if line_dir == 1 and source_norm in desc_norm and target_norm in desc_norm:
                    evidence_text = desc
                elif line_dir == 1 and source_norm in expect_norm and target_norm in expect_norm:
                    evidence_text = expect
                elif title_dir == 1 and expect:
                    evidence_text = expect
                else:
                    evidence_text = desc or expect or case.get("title", "")
                score = item["score"] + title_bonus
                if positive:
                    score += 40
                if negative:
                    score += 40
                if "仅可选择支持该设备的套餐" in evidence_text or "仅能选择支持该设备的套餐" in evidence_text:
                    score += 25
                if "有效期同购买新套餐" in evidence_text:
                    score += 20
                if "补充包仍关联订阅" in evidence_text:
                    score += 18
                if "仍为激活" in evidence_text:
                    score += 18
                evidences.append(
                    {
                        "case": case,
                        "desc": desc,
                        "expect": expect,
                        "evidence": evidence_text,
                        "polarity": polarity,
                        "score": score,
                    }
                )
    evidences.sort(key=lambda item: (-item["score"], item["case"].get("case_id", 0)))
    return evidences


def build_switch_answer(question: str, results: list[dict[str, Any]]) -> list[str]:
    entities = parse_switch_entities(question)
    if not entities:
        return []

    source, target = entities
    evidences = collect_switch_evidence(results, source, target)
    if not evidences:
        return []

    positives = [item for item in evidences if item["polarity"] == "positive"]
    negatives = [item for item in evidences if item["polarity"] == "negative"]

    if positives and not negatives:
        best = positives[0]
        parts = [f"能。至少在 `{short_module_path(best['case'])}` 场景下，`{source}` 可以切换到 `{target}`"]
        evidence = best["evidence"]
        if "仅可选择支持该设备的套餐" in evidence or "仅能选择支持该设备的套餐" in evidence:
            parts.append("但通常仅能选择支持该设备的套餐")
        if "有效期同购买新套餐" in evidence:
            parts.append("在已过期场景下，切换后有效期按新购套餐计算")
        if "补充包仍关联订阅" in evidence:
            parts.append("若有未过期且未用完的补充包，补充包仍关联订阅")
        if "仍为激活" in evidence:
            parts.append("切换后 SIM 卡状态仍为激活")
        return ["结论:", "- %s。" % "；".join(parts)]

    if negatives and not positives:
        best = negatives[0]
        reason = best["case"].get("title", "") if "不能切换" in best["case"].get("title", "") or "不可切换" in best["case"].get("title", "") else best["evidence"] or best["desc"]
        return [
            "结论:",
            "- 不能。当前高相关用例显示，`%s` 不能切换到 `%s`；限制依据是：%s。"
            % (source, target, compress_text(reason, 80)),
        ]

    if positives and negatives:
        return [
            "结论:",
            "- 视条件而定。当前知识库里同时存在可切换和受限制场景，需要结合套餐状态、设备类型和是否支持该设备来判断。",
        ]

    return []


def build_compare_answer(question: str, results: list[dict[str, Any]]) -> list[str]:
    entities = parse_compare_entities(question)
    if not entities:
        return []

    left, right = entities
    texts = select_evidence_lines(question, results, limit=40)
    joined = "\n".join(texts)
    points: list[str] = []

    if left == "云套餐" and right == "流量套餐" or left == "流量套餐" and right == "云套餐":
        if "云套餐对应的items显示有：套餐、有效期" in joined and "流量套餐对应的items显示有：套餐、iccid、有效期" in joined:
            points.append("展示字段不同：云套餐通常展示“套餐、有效期”，流量套餐会额外展示 ICCID。")
        if "云-mydashboard" in joined and "流量套餐-mydashboard" in joined:
            points.append("续费/renew 跳转不同：云套餐跳到云 dashboard，流量套餐跳到流量套餐 dashboard。")
        if "取消云套餐" in joined and "取消4G流量套餐" in joined:
            points.append("账户删除等交互里，云套餐和 4G 流量套餐会分别校验、分别提示。")

    if not points:
        pair_lines = [line for line in texts if left in line and right in line]
        for line in pair_lines[:2]:
            points.append(compress_text(line, 110))

    points = unique_keep_order(points)
    if not points:
        return []

    return ["结论:"] + ["- %s" % point for point in points[:3]]


def build_direct_answer(
    question: str,
    results: list[dict[str, Any]],
) -> list[str]:
    if not results:
        return []
    for builder in (
        build_package_type_answer,
        build_effective_answer,
        build_limitation_answer,
        build_compare_answer,
        build_switch_answer,
    ):
        answer = builder(question, results)
        if answer:
            return answer
    return []


def format_case(item: dict[str, Any], rank: int, full: bool) -> str:
    case = item["case"]
    hits = item["hits"]
    steps = case.get("steps", [])
    show_steps = steps if full else steps[:4]

    lines = []
    lines.append("%s %s: [%s] %s" % (matched_entry_label(case), rank, case.get("case_id", ""), case.get("title", "")))
    lines.append("匹配分: %s" % item["score"])
    lines.append("模块: %s" % case.get("module_path_text", ""))
    if hits:
        lines.append("命中词: %s" % " / ".join(hits[:12]))
    if case.get("precondition"):
        lines.append("前置条件:")
        for line in case["precondition"].splitlines():
            lines.append("- %s" % line)
    lines.append("逻辑摘录:")
    if show_steps:
        for step in show_steps:
            lines.append("%s. %s" % (step.get("name", step.get("index", "")), step.get("desc", "")))
            if step.get("expect"):
                for idx, line in enumerate(str(step["expect"]).splitlines(), 1):
                    prefix = "   预期: " if idx == 1 else "         "
                    lines.append(prefix + line)
    else:
        lines.append("- 无步骤数据")
    if not full and len(steps) > len(show_steps):
        lines.append("... 其余 %s 步可加 `--full` 查看" % (len(steps) - len(show_steps)))
    lines.append("链接: %s" % case.get("link", ""))
    return "\n".join(lines)


def pick_brief_evidence_info(case: dict[str, Any], question: str) -> tuple[int, str]:
    lines = iter_case_lines(case)
    if not lines:
        return 0, ""
    query_terms = [normalize(item) for item in display_terms(question) + intent_terms(question) if len(normalize(item)) >= 2]
    compare_entities = parse_compare_entities(question)
    switch_entities = parse_switch_entities(question)
    ranked = []
    for line in lines:
        line_norm = normalize(line)
        score = 0
        for term in query_terms:
            if term in line_norm:
                score += 2
        if any(word in line for word in ("预期", "有效期", "生效", "限制", "不可", "不能", "仅能", "只能")):
            score += 2
        if is_effective_question(question) and any(word in line for word in ("有效期", "生效", "购买新套餐", "到期", "立即")):
            score += 6
        if is_limitation_question(question) and any(word in line for word in ("限制", "不可", "不能", "仅能", "只能", "最多", "不能为空", "格式不正确")):
            score += 6
        if compare_entities and compare_entities[0] in line and compare_entities[1] in line:
            score += 8
        if switch_entities:
            source, target = switch_entities
            source_norm = normalize(source)
            target_norm = normalize(target)
            if source_norm in line_norm and target_norm in line_norm and any(term in line_norm for term in SWITCH_ACTION_TERMS):
                score += 12
            if source_norm in line_norm and target_norm in line_norm and any(term in line_norm for term in SWITCH_POSITIVE_TERMS + SWITCH_NEGATIVE_TERMS):
                score += 10
        if is_package_type_question(question):
            package_hits = sum(1 for item in PACKAGE_TYPE_CANDIDATES if item in line)
            score += package_hits * 3
        ranked.append((score, len(line), line))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return ranked[0][0], ranked[0][2]


def format_case_brief(item: dict[str, Any], rank: int, question: str) -> str:
    case = item["case"]
    _score, evidence = pick_brief_evidence_info(case, question)
    lines = ["%s %s: [%s] %s" % (reference_entry_label(case), rank, case.get("case_id", ""), case.get("title", ""))]
    if evidence:
        lines.append("- 证据: %s" % compress_text(evidence, 120))
    lines.append("- 模块: %s" % case.get("module_path_text", ""))
    lines.append("- 链接: %s" % case.get("link", ""))
    return "\n".join(lines)


def format_switch_evidence_brief(evidence_item: dict[str, Any], rank: int) -> str:
    case = evidence_item["case"]
    evidence = evidence_item.get("evidence") or evidence_item.get("expect") or evidence_item.get("desc") or case.get("title", "")
    lines = ["%s %s: [%s] %s" % (reference_entry_label(case), rank, case.get("case_id", ""), case.get("title", ""))]
    lines.append("- 证据: %s" % compress_text(evidence, 120))
    lines.append("- 模块: %s" % case.get("module_path_text", ""))
    lines.append("- 链接: %s" % case.get("link", ""))
    return "\n".join(lines)


def unique_switch_evidences_by_case(evidences: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    output = []
    for item in evidences:
        case_id = item["case"].get("case_id")
        if case_id in seen:
            continue
        seen.add(case_id)
        output.append(item)
    return output


def print_stats(cases: list[dict[str, Any]], manifest: dict[str, Any]) -> None:
    print("知识库路径: %s" % KB_PATH)
    print("RAG 索引路径: %s" % (ROOT / "data" / "rag"))
    print("逻辑补丁路径: %s" % kb_logic_patches_path())
    if SUPPLEMENTAL_CASES_PATH.exists():
        print("补充知识路径: %s" % SUPPLEMENTAL_CASES_PATH)
    print("同步时间: %s" % manifest.get("generated_at", ""))
    print(
        "统计: product=%s module=%s 用例总数=%s 模块数=%s"
        % (
            manifest.get("product_id", ""),
            manifest.get("module_id", ""),
            manifest.get("testcase_total", len(cases)),
            manifest.get("module_count", ""),
        )
    )
    supplemental_total = sum(1 for case in cases if is_supplemental_case(case))
    patch_total = sum(1 for case in cases if is_kb_patch_case(case))
    if supplemental_total:
        print("补充知识条数: %s" % supplemental_total)
    if patch_total:
        print("MCP 逻辑补丁条数: %s" % patch_total)
    if supplemental_total or patch_total:
        print("当前可检索总条数: %s" % len(cases))
    try:
        rag_index = get_rag_index(cases)
        if rag_index.ready:
            print(
                "RAG 索引: chunks=%s cases=%s generated_at=%s"
                % (
                    rag_index.manifest.get("chunk_total", len(rag_index.chunks)),
                    rag_index.manifest.get("case_total", ""),
                    rag_index.manifest.get("generated_at", ""),
                )
            )
        else:
            print("RAG 索引: 未构建（首次 RAG 查询会自动构建）")
    except Exception as exc:
        print("RAG 索引: 加载失败 (%s)" % exc)
    print("LLM 生成: %s" % ("已配置" if llm_available() else "未配置（使用抽取式 RAG）"))
    from rag_llm import cursor_api_status, llm_config, llm_env_path, llm_provider

    llm_env = llm_env_path()
    if llm_env.exists():
        print("LLM 配置文件: %s" % llm_env)
    config = llm_config()
    print("LLM Provider: %s" % llm_provider())
    if config.get("model"):
        print("LLM Model: %s" % config["model"])
    if llm_provider() == "cursor":
        cursor_status = cursor_api_status()
        if cursor_status.get("verified"):
            print(
                "Cursor API Key: 已验证 (%s / %s)"
                % (cursor_status.get("api_key_name", ""), cursor_status.get("user_email", ""))
            )
        elif cursor_status.get("configured"):
            print("Cursor API Key: 已写入但校验失败 (%s)" % cursor_status.get("error", ""))
    elif config.get("api_base"):
        print("LLM API Base: %s" % config["api_base"])
    module_counts = Counter(case.get("module_path_text", "") for case in cases if case.get("module_path_text"))
    print("高频模块:")
    for idx, (module_path, count) in enumerate(module_counts.most_common(8), 1):
        print("%s. %s (%s)" % (idx, module_path, count))


def show_case_by_id(cases_by_id: dict[int, dict[str, Any]], case_id: int, full: bool) -> int:
    case = cases_by_id.get(case_id)
    if case is None:
        print("未找到 case_id=%s 的用例。" % case_id)
        return 1
    print(format_case({"case": case, "score": 1000, "hits": ["case:%s" % case_id]}, 1, full=full))
    return 0


def print_brief_answer_lines(lines: list[str]) -> None:
    for line in lines:
        stripped = str(line).strip()
        if not stripped or stripped == "结论:":
            continue
        print(stripped)


def format_rag_generation(
    question: str,
    results: list[dict[str, Any]],
    *,
    use_llm: bool,
    direct_answer_lines: list[str],
) -> str:
    context_blocks = format_context_blocks(results, limit=min(5, len(results)))
    if use_llm and llm_available():
        try:
            return generate_rag_answer(question, context_blocks)
        except Exception as exc:
            return synthesize_extractive_answer(question, context_blocks, direct_answer_lines) + "\n（LLM 生成失败，已回退抽取式回答：%s）" % exc
    return synthesize_extractive_answer(question, context_blocks, direct_answer_lines)


def answer_question(
    cases: list[dict[str, Any]],
    question: str,
    top_n: int,
    full: bool,
    brief: bool = False,
    module_filter: str = "",
    use_rag: bool = True,
    retrieve_only: bool = False,
    use_llm: bool = True,
    rebuild_index: bool = False,
) -> int:
    results = search_cases_with_mode(
        cases,
        question,
        top_n=top_n,
        module_filter=module_filter,
        use_rag=use_rag,
        rebuild_index=rebuild_index,
    )
    if results:
        direct_answer_lines = build_direct_answer(question, results)
        rag_answer = ""
        if use_rag and not retrieve_only and not full:
            rag_answer = format_rag_generation(
                question,
                results,
                use_llm=use_llm,
                direct_answer_lines=direct_answer_lines,
            )
        if brief:
            if direct_answer_lines:
                print_brief_answer_lines(direct_answer_lines)
                return 0
            switch_entities = parse_switch_entities(question)
            if switch_entities:
                switch_evidences = unique_switch_evidences_by_case(
                    collect_switch_evidence(results, switch_entities[0], switch_entities[1])
                )
                if switch_evidences:
                    print(compress_text(switch_evidences[0].get("evidence") or switch_evidences[0]["case"].get("title", ""), 120))
                    return 0
            print("命中 %s 条相关用例。" % len(results))
            return 0

        print("问题/关键词: %s" % question)
        if module_filter:
            print("模块过滤: %s" % module_filter)
        if use_rag:
            mode = "RAG 混合检索"
            if retrieve_only:
                mode += "（仅检索）"
            elif use_llm and llm_available():
                from rag_llm import llm_provider

                if llm_provider() == "cursor":
                    mode += " + Cursor Cloud Agent 生成"
                else:
                    mode += " + LLM 生成"
            else:
                mode += " + 抽取式生成"
            print("检索模式: %s" % mode)
        print("展示前 %s 条命中结果。" % len(results))
        if rag_answer:
            print("")
            print("RAG 回答:")
            print(rag_answer)
        elif direct_answer_lines:
            print("")
            print("\n".join(direct_answer_lines))
        if (rag_answer or direct_answer_lines) and not full:
            print("")
            print("依据:")
            switch_entities = parse_switch_entities(question)
            if switch_entities:
                switch_evidences = unique_switch_evidences_by_case(
                    collect_switch_evidence(results, switch_entities[0], switch_entities[1])
                )
                brief_evidences = switch_evidences[: min(3, len(switch_evidences))]
                for idx, evidence_item in enumerate(brief_evidences, 1):
                    print("")
                    print(format_switch_evidence_brief(evidence_item, idx))
            else:
                ranked_brief_results = sorted(
                    results,
                    key=lambda item: (
                        -pick_brief_evidence_info(item["case"], question)[0],
                        -item["score"],
                        item["case"].get("case_id", 0),
                    ),
                )
                brief_results = ranked_brief_results[: min(3, len(ranked_brief_results))]
                for idx, item in enumerate(brief_results, 1):
                    print("")
                    print(format_case_brief(item, idx, question))
        else:
            summary_lines = summarize_logic(results)
            if summary_lines:
                print("")
                print("\n".join(summary_lines))
            for idx, item in enumerate(results, 1):
                print("")
                print(format_case(item, idx, full=full))
        return 0

    print("问题/关键词: %s" % question)
    if module_filter:
        print("模块过滤: %s" % module_filter)
    print("未命中相关用例。")
    print("建议改问法，例如：")
    print("- 切换套餐")
    print("- 登录提醒邮件 相同B段IP")
    print("- 后台 机型组 删除成员")
    print("- 4725")
    return 1


def interactive_loop(
    cases: list[dict[str, Any]],
    cases_by_id: dict[int, dict[str, Any]],
    manifest: dict[str, Any],
    top_n: int,
    full: bool,
    brief: bool,
    module_filter: str,
    use_rag: bool,
    retrieve_only: bool,
    use_llm: bool,
) -> int:
    print("Reolink 测试用例知识库已加载。输入问题后回车，输入 help 查看帮助，输入 exit/quit/退出 结束。")
    while True:
        try:
            question = input("reolink-kb> ").strip()
        except EOFError:
            print("")
            return 0
        if not question:
            continue
        lowered = question.lower()
        if lowered in ("exit", "quit", "q", "退出"):
            return 0
        if lowered in ("help", "h", "帮助"):
            print("可直接输入关键词或问题，也支持：")
            print("- stats / 统计")
            print("- case 4725")
            print("- module 切换套餐")
            print("")
            continue
        if lowered in ("stats", "stat", "meta", "summary", "统计"):
            print_stats(cases, manifest)
            print("")
            continue
        if lowered.startswith("case "):
            raw = question.split(" ", 1)[1].strip()
            if raw.isdigit():
                show_case_by_id(cases_by_id, int(raw), full=full)
            else:
                print("case 命令后请跟数字 ID。")
            print("")
            continue
        if lowered.startswith("module "):
            module_query = question.split(" ", 1)[1].strip()
            answer_question(
                cases,
                module_query,
                top_n=top_n,
                full=full,
                brief=brief,
                module_filter=module_query,
                use_rag=use_rag,
                retrieve_only=retrieve_only,
                use_llm=use_llm,
            )
            print("")
            continue
        answer_question(
            cases,
            question,
            top_n=top_n,
            full=full,
            brief=brief,
            module_filter=module_filter,
            use_rag=use_rag,
            retrieve_only=retrieve_only,
            use_llm=use_llm,
        )
        print("")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="在本地终端查询 Reolink 禅道测试用例知识库。")
    parser.add_argument("question", nargs="*", help="要检索的关键词或问题")
    parser.add_argument("--interactive", action="store_true", help="进入交互模式")
    parser.add_argument("--case", type=int, help="按 case_id 直接查看单条用例")
    parser.add_argument("--module", default="", help="仅在模块路径包含指定关键字的用例里搜索")
    parser.add_argument("--stats", action="store_true", help="查看知识库统计信息")
    parser.add_argument("--top", type=int, default=5, help="返回前 N 条命中结果")
    parser.add_argument("--brief", action="store_true", help="仅输出简短结论，不展开依据")
    parser.add_argument("--full", action="store_true", help="展示完整步骤")
    parser.add_argument("--no-rag", action="store_true", help="关闭 RAG，仅使用原有关键词检索")
    parser.add_argument("--retrieve-only", action="store_true", help="仅做 RAG 检索，不生成 RAG 回答")
    parser.add_argument("--no-llm", action="store_true", help="即使已配置 LLM，也使用抽取式 RAG 回答")
    parser.add_argument("--rebuild-index", action="store_true", help="强制重建 RAG 向量索引")
    return parser


def main() -> int:
    configure_output()
    parser = build_parser()
    args = parser.parse_args()
    cases = load_cases()
    manifest = load_manifest()
    cases_by_id = {int(case["case_id"]): case for case in cases}

    if args.top < 1:
        args.top = 1

    if args.stats:
        print_stats(cases, manifest)
        return 0

    if args.case is not None:
        return show_case_by_id(cases_by_id, args.case, full=args.full)

    if args.rebuild_index and not args.stats and args.case is None:
        index = get_rag_index(cases, rebuild=True)
        print(
            "RAG 索引已重建: chunks=%s cases=%s generated_at=%s"
            % (
                index.manifest.get("chunk_total", len(index.chunks)),
                index.manifest.get("case_total", ""),
                index.manifest.get("generated_at", ""),
            )
        )
        if not args.question and not args.interactive:
            return 0

    if args.interactive:
        return interactive_loop(
            cases,
            cases_by_id=cases_by_id,
            manifest=manifest,
            top_n=args.top,
            full=args.full,
            brief=args.brief,
            module_filter=args.module,
            use_rag=not args.no_rag,
            retrieve_only=args.retrieve_only,
            use_llm=not args.no_llm,
        )

    question = " ".join(args.question).strip()
    if not question:
        parser.print_help()
        print("")
        print("示例：")
        print('python "%s" "切换套餐什么时候生效"' % str(pathlib.Path(__file__).resolve()))
        print('python "%s" --case 4725 --full' % str(pathlib.Path(__file__).resolve()))
        print('python "%s" --interactive' % str(pathlib.Path(__file__).resolve()))
        return 0

    return answer_question(
        cases,
        question,
        top_n=args.top,
        full=args.full,
        brief=args.brief,
        module_filter=args.module,
        use_rag=not args.no_rag,
        retrieve_only=args.retrieve_only,
        use_llm=not args.no_llm,
        rebuild_index=args.rebuild_index,
    )


if __name__ == "__main__":
    raise SystemExit(main())
