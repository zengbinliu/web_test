# -*- coding: utf-8 -*-
"""调用 LLM 推理新的元素选择器（Agently TriggerFlow：finder → verifier → 有限重试）。"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List

from agently import Agently, TriggerFlow, TriggerFlowRuntimeData

from page_ele.ui_healing.config import HealingConfig, get_healing_config
from page_ele.ui_healing.element_def import LOCATOR_PRIORITY_HINT, infer_locator_type
from page_ele.ui_healing.llm_config import get_llm_status
from utils.logger import get_logger

logger = get_logger(__name__)

_MAX_SELECTOR_RETRIES = 2
_YAML_DIALECT_HINT = (
    "只返回 YAML 方言选择器（不要 page.get_by_* / Playwright JS API），例如："
    "role=button[name='Log in']、text=Log in、label=Email、placeholder=Enter email、"
    "testid=pay-button、CSS 或 xpath=..."
)
_VERIFIER_RULES = """请根据目标元素语义和 DOM 片段，审核一条候选 YAML 方言选择器。

以 DOM 片段和目标元素语义为判定依据。确认选择器使用受支持的 YAML 方言，且 locator_type 与选择器语法一致。例如，`placeholder=Password` 必须对应匹配的 `placeholder` 属性，`role=button[...]` 必须对应按钮类型元素。

硬性唯一性：选择器在提供的 DOM 中必须只命中目标那一个节点。若同名 placeholder/label/text/role 在登录与注册等区域各出现一次（例如 `#password` 与 `#sign-up-password` 都带 placeholder=Password），则该语义选择器不可用，enable 必须为 false，并建议改用唯一 id/CSS。

当选择器语法正确、唯一命中目标元素、且与已有 DOM 证据一致时，将 enable 设为 true。不得仅因无法实际运行 Playwright 或 DOM 片段不完整而判定为 false。

仅在存在直接证据表明选择器语法错误、使用不受支持的方言、与声明的 locator_type 冲突、指向其他语义元素、命中多个节点，或与提供的 DOM 明确矛盾时，才将 enable 设为 false。请在 reason 中说明具体判定证据。"""


def _configure_agently(cfg: HealingConfig) -> None:
    """按 HealingConfig 注入 Agently model_pool / model_profiles（不含明文硬编码）。"""
    if not cfg.api_key:
        raise RuntimeError(
            "未配置 LLM API Key。请在 page_ele/ui_healing/llm.env 中设置 "
            "REOLINK_RAG_LLM_API_KEY 或 CLOUD_HEALING_API_KEY。"
        )
    if not cfg.api_base:
        raise RuntimeError(
            "未配置 LLM API Base。请在 llm.env 中设置 REOLINK_RAG_LLM_API_BASE "
            "或 CLOUD_HEALING_API_BASE。"
        )

    finder = cfg.finder_model
    verifier = cfg.verifier_model
    Agently.set_settings(
        "model_pool",
        {
            "finder": finder,
            "verifier": verifier,
        },
    )
    Agently.set_settings(
        "model_profiles",
        {
            finder: {
                "provider": "OpenAICompatible",
                "base_url": cfg.api_base,
                "api_key": cfg.api_key,
                "model": finder,
                "request_options": {"temperature": 0.1},
            },
            verifier: {
                "provider": "OpenAICompatible",
                "base_url": cfg.api_base,
                "api_key": cfg.api_key,
                "model": verifier,
                "request_options": {"temperature": 0},
            },
        },
    )


def _build_user_prompt(payload: Dict[str, Any]) -> str:
    """把失效元素上下文拼成 user prompt。"""
    return (
        "请为以下失效元素推荐新的 Playwright YAML 方言选择器。\n"
        f"元素键: {payload.get('element_key')}\n"
        f"元素语义: {payload.get('element_semantic')}\n"
        f"旧选择器: {payload.get('old_selector')}\n"
        f"旧定位类型: {payload.get('locator_type')}\n"
        f"页面 URL: {payload.get('page_url')}\n"
        f"页面标题: {payload.get('page_title')}\n"
        f"父级 iframe 链: {payload.get('parent_keys')}\n"
        f"失败信息: {payload.get('error_message')}\n\n"
        "DOM 片段:\n"
        f"{payload.get('dom_snippet', '')}\n\n"
        f"{_YAML_DIALECT_HINT}\n"
        "选择器必须唯一命中目标元素；若 DOM 中同文案出现多次，改用唯一 id/CSS。\n"
        "返回置信度最高的一条选择器。\n"
    )


def _state_dict(data: TriggerFlowRuntimeData) -> Dict[str, Any]:
    """读取 runtime state 为 dict。"""
    state = data.get_state()
    return state if isinstance(state, dict) else {}


def _is_enabled(check: Any) -> bool:
    """verifier 的 enable 是否为可用（兼容 bool / 0/1）。"""
    if not isinstance(check, dict):
        return False
    enable = check.get("enable")
    return enable is True or enable == 1 or enable == "1"


def _is_disabled(check: Any) -> bool:
    if not isinstance(check, dict):
        return False
    enable = check.get("enable")
    return enable is False or enable == 0 or enable == "0"


def _need_retry(data: TriggerFlowRuntimeData) -> bool:
    """审核未通过且仍有重试次数时继续 finder。"""
    state = _state_dict(data)
    check = state.get("check_new_selector") or {}
    retry_count = int(state.get("selector_retry_count") or 0)
    return _is_disabled(check) and retry_count <= _MAX_SELECTOR_RETRIES


def _candidates_from_state(state: Dict[str, Any]) -> List[dict]:
    """从最终 state 抽出网关可用的 candidates 列表。"""
    check = state.get("check_new_selector") or {}
    found = state.get("get_new_selector") or {}
    if not _is_enabled(check):
        return []
    selector = str(found.get("selector") or "").strip()
    if not selector:
        return []
    locator_type = str(found.get("locator_type") or "").strip() or infer_locator_type(selector)
    score = found.get("score")
    try:
        confidence = float(score) / 100.0 if score is not None else 0.0
    except (TypeError, ValueError):
        confidence = 0.0
    return [
        {
            "selector": selector,
            "locator_type": locator_type,
            "confidence": confidence,
            "reason": f"agently score={score}",
        }
    ]


def build_flow() -> TriggerFlow:
    """构建 finder → verifier → 有限重试 的 TriggerFlow。"""
    flow = TriggerFlow(name="get_new_ui")
    gpt = Agently.create_agent("triage")

    async def get_payload(data: TriggerFlowRuntimeData):
        """规范化输入并初始化重试计数。"""
        text = str(data.input).strip()
        await data.async_set_state("user_prompt", text)
        await data.async_set_state("selector_retry_count", 0)
        await data.async_put_into_stream({"stage": "get_payload", "ok": True})
        return text

    async def get_new_selector(data: TriggerFlowRuntimeData):
        """用 finder 模型推荐 YAML 方言选择器。"""
        prompt = _state_dict(data).get("user_prompt") or str(data.input)
        gpt.activate_model("finder")
        result = await (
            gpt.role("你是 Playwright UI 自动化测试专家。")
            .info(
                "根据元素语义、旧选择器、页面 URL 与 DOM 片段，给出可稳定且唯一定位目标元素的新选择器。"
            )
            .instruct(
                f"推荐优先级（必须遵守）：{LOCATOR_PRIORITY_HINT}\n{_YAML_DIALECT_HINT}"
            )
            .input(prompt)
            .output(
                {
                    "selector": (
                        str,
                        "YAML 方言选择器，如 role=button[name='Log in']",
                        True,
                    ),
                    "locator_type": (
                        str,
                        "role|text|label|placeholder|alt_text|title|test_id|css|xpath",
                        True,
                    ),
                    "score": (int, "置信度，0-100"),
                }
            )
            .async_start()
        )
        logger.debug("get_new_selector result=%s", result)
        await data.async_set_state("get_new_selector", result)
        await data.async_put_into_stream({"stage": "get_new_selector", "data": result})
        return result

    async def check_new_selector(data: TriggerFlowRuntimeData):
        """用 verifier 审核候选选择器；失败则累加重试计数。"""
        state = _state_dict(data)
        prompt = state.get("user_prompt") or ""
        candidate = state.get("get_new_selector") or {}
        verify_input = (
            f"{prompt}\n\n"
            f"候选选择器: {candidate.get('selector')}\n"
            f"定位类型: {candidate.get('locator_type')}\n"
            f"置信度: {candidate.get('score')}\n"
            "请判断该选择器是否能正确定位目标元素。"
        )
        gpt.activate_model("verifier")
        result = await (
            gpt.role("你是 Playwright UI 审计专家。")
            .info(
                "根据元素语义、旧选择器、页面 URL、DOM 片段以及新给出的选择器，判断新选择器是否可用。"
            )
            .instruct(_VERIFIER_RULES)
            .input(verify_input)
            .output(
                {
                    "enable": (bool, "是否可用：True 可用，False 不可用"),
                    "reason": (str, "简短说明判定所依据的 DOM 或语义证据", True),
                }
            )
            .async_start()
        )
        logger.debug("check_new_selector result=%s", result)
        await data.async_set_state("check_new_selector", result)
        if _is_disabled(result):
            retry_count = int(state.get("selector_retry_count") or 0) + 1
            await data.async_set_state("selector_retry_count", retry_count)
        await data.async_put_into_stream({"stage": "check_new_selector", "data": result})
        return result

    async def find_and_check_new_selector(data: TriggerFlowRuntimeData):
        while True:
            await get_new_selector(data)
            result = await check_new_selector(data)
            if not _need_retry(data):
                return result

    async def emit_candidates(data: TriggerFlowRuntimeData):
        """把审核通过的选择器写成 candidates，并 set_result 供 async_start 直接返回。"""
        candidates = _candidates_from_state(_state_dict(data))
        await data.async_set_state("candidates", candidates)
        await data.async_put_into_stream({"stage": "emit_candidates", "data": candidates})
        data.set_result(candidates)
        logger.info("自愈 LLM 候选数=%s", len(candidates))
        return candidates

    # 所有分支最终都要走到 emit_candidates，否则 set_result 不会执行，
    # async_start 只会返回 close snapshot，而不是 candidates 列表。
    (
        flow.to(get_payload)
        .to(find_and_check_new_selector)
        .to(emit_candidates)
        .end()
    )
    return flow


async def _suggest_locator_candidates_async(payload: Dict[str, Any]) -> List[dict]:
    """异步跑 build_flow，返回 candidates。"""
    cfg = get_healing_config()
    _configure_agently(cfg)
    prompt = _build_user_prompt(payload)
    logger.info(
        "调用 Agently 自愈 flow: key=%s finder=%s verifier=%s",
        payload.get("element_key"),
        cfg.finder_model,
        cfg.verifier_model,
    )
    flow = build_flow()
    result = await flow.async_start(prompt, timeout=float(cfg.api_timeout_s))
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        if isinstance(result.get("candidates"), list):
            return result["candidates"]
        return _candidates_from_state(result)
    return []


def suggest_locator_candidates(payload: Dict[str, Any]) -> List[dict]:
    """同步入口：跑 Agently build_flow，返回候选列表供 gateway 校验。"""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_suggest_locator_candidates_async(payload))

    # 已在事件循环中（少见）：放到独立线程跑新 loop，避免嵌套 asyncio.run
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(_suggest_locator_candidates_async(payload))).result()


def test_llm_connection() -> Dict[str, Any]:
    """用固定样例探测 LLM / Agently flow 是否可用。"""
    from page_ele.ui_healing.llm_config import PLACEHOLDER_API_KEYS

    status = get_llm_status()
    cfg = get_healing_config()
    api_key = (cfg.api_key or "").strip()
    if not api_key or api_key.lower() in PLACEHOLDER_API_KEYS or not cfg.api_base:
        return {
            "ok": False,
            "stage": "config",
            "status": status,
            "error": "LLM 未配置或不可用（需要 api_key + api_base）",
        }

    payload = {
        "element_key": "login_button",
        "element_semantic": "登录提交按钮",
        "old_selector": ".login .login-button span",
        "locator_type": "css",
        "page_url": "https://cloud.reolink.review/login",
        "page_title": "Login",
        "parent_keys": [],
        "error_message": "Timeout 30000ms",
        "dom_snippet": '<button type="submit" class="login-button">Log in</button>',
    }
    try:
        candidates = suggest_locator_candidates(payload)
        return {
            "ok": True,
            "stage": "invoke",
            "status": status,
            "candidates_count": len(candidates),
            "first_candidate": candidates[0] if candidates else None,
        }
    except Exception as exc:
        return {"ok": False, "stage": "invoke", "status": status, "error": str(exc)}
