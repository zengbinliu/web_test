import json
import os
import re
import subprocess
import sys
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from flask import Flask, jsonify, request

MCP_PROTOCOL_VERSION = "2025-11-25"
SUPPORTED_PROTOCOL_VERSIONS = (
    MCP_PROTOCOL_VERSION,
    "2025-06-18",
)
SERVER_NAME = os.getenv("MCP_SERVER_NAME", "flask-mcp-server")
SERVER_VERSION = os.getenv("MCP_SERVER_VERSION", "0.1.0")
DEFAULT_ASKREOLINK_SCRIPT = r"D:\reolink_knowledge\ask_reolink_testcase_kb.py"
DEFAULT_REOLINK_KB_ROOT = r"D:\reolink_knowledge"
DEFAULT_ASKCAMOVUE_SCRIPT = r"C:\Users\Reolink\.cursor\ask_camovue_kb.py"
DEFAULT_ALLOWED_ORIGIN_PREFIXES = (
    "http://127.0.0.1",
    "http://localhost",
    "https://127.0.0.1",
    "https://localhost",
    "file://",
    "vscode-file://",
    "cursor://",
    "null",
)

# update_reolink_kb：正文涉及「批量续费」时须在 correction 中显式说明国家组一致
_BATCH_RENEWAL_HINT_RE = re.compile(r"批量\s*续费")
_RENEWAL_COUNTRY_GROUP_DOC_RE = re.compile(
    r"(?:国家组[^\n。；;]{0,160}?(?:一致|相同|统一|同属))"
    r"|(?:(?:一致|相同|统一|同属)[^\n。；;]{0,160}?国家组)"
    r"|(?:同一\s*国家组)"
)


def ensure_batch_renewal_country_group_consistency(*, summary: str, correction: str) -> None:
    if not (
        _BATCH_RENEWAL_HINT_RE.search(summary)
        or _BATCH_RENEWAL_HINT_RE.search(correction)
    ):
        return
    if _RENEWAL_COUNTRY_GROUP_DOC_RE.search(correction):
        return
    raise ValueError(
        "涉及「批量续费」时，更正说明（correction）须明确写出：批量续费所选记录须为同一国家组"
        "（正文中需同时出现「国家组」与「一致/相同/统一/同属」等一致性表述，或使用「同一国家组」）。"
    )


app = Flask(__name__)

ToolHandler = Callable[[Dict[str, Any]], Any]
SESSIONS: Dict[str, str] = {}
TOOLS: Dict[str, "ToolSpec"] = {}


class JsonRpcRequestError(Exception):
    def __init__(
        self,
        code: int,
        message: str,
        *,
        status: int = 400,
        data: Any = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.data = data


@dataclass(frozen=True)
class ToolSpec:
    name: str
    title: str
    description: str
    input_schema: Dict[str, Any]
    handler: ToolHandler

    def as_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "inputSchema": self.input_schema,
        }


def register_tool(
    *,
    name: str,
    title: str,
    description: str,
    input_schema: Dict[str, Any],
) -> Callable[[ToolHandler], ToolHandler]:
    def decorator(func: ToolHandler) -> ToolHandler:
        TOOLS[name] = ToolSpec(
            name=name,
            title=title,
            description=description,
            input_schema=input_schema,
            handler=func,
        )
        return func

    return decorator


def get_allowed_origin_prefixes():
    configured = os.getenv("MCP_ALLOWED_ORIGINS", "").strip()
    if configured == "*":
        return ("*",)
    if configured:
        return tuple(
            item.strip()
            for item in configured.split(",")
            if item.strip()
        )
    return DEFAULT_ALLOWED_ORIGIN_PREFIXES


def origin_is_allowed(origin: Optional[str]) -> bool:
    if not origin:
        return True
    allowed_prefixes = get_allowed_origin_prefixes()
    if "*" in allowed_prefixes:
        return True
    return any(origin.startswith(prefix) for prefix in allowed_prefixes)


def build_response_headers(
    *,
    session_id: Optional[str] = None,
    protocol_version: Optional[str] = None,
) -> Dict[str, str]:
    headers = {
        "Cache-Control": "no-store",
        "MCP-Protocol-Version": protocol_version or MCP_PROTOCOL_VERSION,
    }
    if session_id:
        headers["MCP-Session-Id"] = session_id
    return headers


def apply_response_headers(
    response,
    *,
    session_id: Optional[str] = None,
    protocol_version: Optional[str] = None,
):
    for key, value in build_response_headers(
        session_id=session_id,
        protocol_version=protocol_version,
    ).items():
        response.headers[key] = value
    return response


def jsonrpc_result(
    request_id: Any,
    result: Dict[str, Any],
    *,
    status: int = 200,
    session_id: Optional[str] = None,
    protocol_version: Optional[str] = None,
):
    response = jsonify({"jsonrpc": "2.0", "id": request_id, "result": result})
    response.status_code = status
    return apply_response_headers(
        response,
        session_id=session_id,
        protocol_version=protocol_version,
    )


def jsonrpc_error(
    request_id: Any,
    code: int,
    message: str,
    *,
    status: int = 400,
    data: Any = None,
    session_id: Optional[str] = None,
    protocol_version: Optional[str] = None,
):
    payload = {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {
            "code": code,
            "message": message,
        },
    }
    if data is not None:
        payload["error"]["data"] = data
    response = jsonify(payload)
    response.status_code = status
    return apply_response_headers(
        response,
        session_id=session_id,
        protocol_version=protocol_version,
    )


def accepted_response(
    *,
    session_id: Optional[str] = None,
    protocol_version: Optional[str] = None,
):
    response = app.response_class("", status=202)
    return apply_response_headers(
        response,
        session_id=session_id,
        protocol_version=protocol_version,
    )


def notification_or_result(
    body: Dict[str, Any],
    result: Dict[str, Any],
    *,
    session_id: Optional[str] = None,
    protocol_version: Optional[str] = None,
):
    if "id" not in body:
        return accepted_response(
            session_id=session_id,
            protocol_version=protocol_version,
        )
    return jsonrpc_result(
        body["id"],
        result,
        session_id=session_id,
        protocol_version=protocol_version,
    )


def ensure_object(value: Any, field_name: str) -> Dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise JsonRpcRequestError(
            -32602,
            "Invalid params: '{0}' must be an object.".format(field_name),
        )
    return value


def tool_text_result(value: Any, *, is_error: bool = False) -> Dict[str, Any]:
    if isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, ensure_ascii=False, indent=2)
    return {
        "content": [
            {
                "type": "text",
                "text": text,
            }
        ],
        "isError": is_error,
    }


def read_required_string(arguments: Dict[str, Any], key: str) -> str:
    value = arguments.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError("'{0}' must be a non-empty string.".format(key))
    return value.strip()


def read_required_number(arguments: Dict[str, Any], key: str) -> float:
    value = arguments.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("'{0}' must be a number.".format(key))
    return float(value)


def negotiate_protocol_version(requested_version: Any) -> str:
    if (
        isinstance(requested_version, str)
        and requested_version in SUPPORTED_PROTOCOL_VERSIONS
    ):
        return requested_version
    return MCP_PROTOCOL_VERSION


def create_session(protocol_version: str) -> str:
    session_id = uuid.uuid4().hex
    SESSIONS[session_id] = protocol_version
    return session_id


def require_session_protocol(session_id: Optional[str]) -> str:
    if not session_id:
        raise JsonRpcRequestError(
            -32001,
            "Missing MCP-Session-Id header.",
            status=400,
        )

    protocol_version = SESSIONS.get(session_id)
    if protocol_version is None:
        raise JsonRpcRequestError(
            -32002,
            "Unknown or expired MCP session.",
            status=404,
        )
    return protocol_version


def validate_protocol_header(
    header_value: Optional[str],
    session_protocol_version: str,
) -> str:
    if not header_value:
        return session_protocol_version

    versions = [item.strip() for item in header_value.split(",") if item.strip()]
    if not versions:
        raise JsonRpcRequestError(
            -32602,
            "Invalid MCP-Protocol-Version header.",
            status=400,
        )

    if session_protocol_version in versions:
        return session_protocol_version

    raise JsonRpcRequestError(
        -32602,
        "Unsupported MCP-Protocol-Version header.",
        status=400,
        data={
            "supported": [session_protocol_version],
            "received": header_value,
        },
    )


def is_jsonrpc_response_message(body: Dict[str, Any]) -> bool:
    return (
        body.get("jsonrpc") == "2.0"
        and "method" not in body
        and ("result" in body or "error" in body)
    )


# @register_tool(
#     name="echo",
#     title="Echo Message",
#     description="Return the incoming message as-is.",
#     input_schema={
#         "type": "object",
#         "properties": {
#             "message": {
#                 "type": "string",
#                 "description": "Any text that should be echoed back.",
#             }
#         },
#         "required": ["message"],
#         "additionalProperties": False,
#     },
# )
# def echo_tool(arguments: Dict[str, Any]) -> Dict[str, Any]:
#     message = read_required_string(arguments, "message")
#     return {"message": message}


# @register_tool(
#     name="add_numbers",
#     title="Add Numbers",
#     description="Add two numbers and return the sum.",
#     input_schema={
#         "type": "object",
#         "properties": {
#             "a": {"type": "number", "description": "The first number."},
#             "b": {"type": "number", "description": "The second number."},
#         },
#         "required": ["a", "b"],
#         "additionalProperties": False,
#     },
# )
# def add_numbers_tool(arguments: Dict[str, Any]) -> Dict[str, Any]:
#     a = read_required_number(arguments, "a")
#     b = read_required_number(arguments, "b")
#     return {
#         "a": a,
#         "b": b,
#         "sum": a + b,
#     }


# @register_tool(
#     name="server_time",
#     title="Server Time",
#     description="Return the current UTC time of the server.",
#     input_schema={
#         "type": "object",
#         "properties": {},
#         "additionalProperties": False,
#     },
# )
# def server_time_tool(arguments: Dict[str, Any]) -> Dict[str, Any]:
#     _ = arguments
#     return {"utc": datetime.now(timezone.utc).isoformat()}


def askreolink_script_path() -> str:
    return os.environ.get("ASKREOLINK_SCRIPT", DEFAULT_ASKREOLINK_SCRIPT).strip()


def askreolink_python_executable() -> str:
    configured = os.environ.get("ASKREOLINK_PYTHON", "").strip()
    if configured:
        return configured
    return sys.executable


def askreolink_timeout_seconds() -> int:
    raw = os.environ.get("ASKREOLINK_TIMEOUT", "120").strip()
    try:
        value = int(raw)
    except ValueError:
        return 120
    return max(1, min(value, 600))


def askcamovue_script_path() -> str:
    return os.environ.get("ASKCAMOVUE_SCRIPT", DEFAULT_ASKCAMOVUE_SCRIPT).strip()


def askcamovue_python_executable() -> str:
    configured = os.environ.get("ASKCAMOVUE_PYTHON", "").strip()
    if configured:
        return configured
    return sys.executable


def askcamovue_timeout_seconds() -> int:
    raw = os.environ.get("ASKCAMOVUE_TIMEOUT", "120").strip()
    try:
        value = int(raw)
    except ValueError:
        return 120
    return max(1, min(value, 600))


def reolink_kb_root_dir() -> str:
    configured = os.environ.get("REOLINK_KB_ROOT", "").strip()
    if configured:
        return configured
    script = askreolink_script_path()
    parent = os.path.dirname(os.path.abspath(script))
    return parent if parent else DEFAULT_REOLINK_KB_ROOT


def update_reolink_script_path() -> str:
    configured = os.environ.get("REOLINK_KB_UPDATE_SCRIPT", "").strip()
    if configured:
        return configured
    return os.path.join(reolink_kb_root_dir(), "update_reolink_testcase_kb.py")


def reolink_kb_patches_path() -> str:
    configured = os.environ.get("REOLINK_KB_PATCHES_PATH", "").strip()
    if configured:
        return configured
    return os.path.join(reolink_kb_root_dir(), "kb_logic_patches.jsonl")


def update_reolink_timeout_seconds() -> int:
    raw = os.environ.get("REOLINK_KB_UPDATE_TIMEOUT", "120").strip()
    try:
        value = int(raw)
    except ValueError:
        return 120
    return max(1, min(value, 600))


_TOPIC_KEY_SEP_RE = re.compile(r"[\s/\\,，、|._\-]+")
_SUMMARY_TAIL_RE = re.compile(r"[吗呢吧呀么?？。!！\s]+$")


def normalize_patch_topic_key(text: str) -> str:
    """Collapse separators so module paths group consistently for deduplication."""
    raw = str(text or "").strip().lower()
    if not raw:
        return ""
    parts = [p for p in _TOPIC_KEY_SEP_RE.split(raw) if p]
    return "|".join(parts)


def compute_patch_topic_key(
    *,
    summary: str,
    module_hint: str,
    topic_key_arg: str,
) -> str:
    if topic_key_arg.strip():
        return normalize_patch_topic_key(topic_key_arg)
    if module_hint.strip():
        return normalize_patch_topic_key(module_hint)
    return normalize_patch_topic_key(summary)


def stored_patch_topic_key_from_row(row: Dict[str, Any]) -> str:
    explicit = row.get("topic_key")
    if isinstance(explicit, str) and explicit.strip():
        return normalize_patch_topic_key(explicit)
    mh = row.get("module_hint", "")
    if isinstance(mh, str) and mh.strip():
        return normalize_patch_topic_key(mh)
    return normalize_patch_topic_key(str(row.get("summary", "") or ""))


def normalize_summary_stem(text: str) -> str:
    """标题去重：去掉句尾语气词与空白，便于识别同一标题的重复提交。"""
    s = str(text or "").strip().lower()
    s = _SUMMARY_TAIL_RE.sub("", s)
    s = re.sub(r"\s+", "", s)
    return s


def patch_record_fingerprint(summary: str, correction: str, module_hint: str) -> str:
    """正文级重复：摘要+更正+模块完全一致时视为重复。"""
    return "::".join(
        [
            normalize_patch_topic_key(summary),
            normalize_patch_topic_key(correction),
            normalize_patch_topic_key(module_hint),
        ]
    )


def patch_row_should_be_replaced(
    row: Dict[str, Any],
    *,
    new_summary: str,
    new_correction: str,
    new_module_hint: str,
    new_topic_key: str,
) -> bool:
    """
    删除旧行的条件（满足任一即可）：
    1）与本次 topic_key 冲突（同域归并）；
    2）与本次摘要+更正+模块完全一致（重复条目）；
    3）标题茎相同且 module_hint 归一化相同（视为同一标题下的重复/修订）。
    """
    old_summary = str(row.get("summary", "") or "")
    old_correction = str(row.get("correction", "") or "")
    old_module = str(row.get("module_hint", "") or "")

    if stored_patch_topic_key_from_row(row) == new_topic_key:
        return True

    if patch_record_fingerprint(old_summary, old_correction, old_module) == patch_record_fingerprint(
        new_summary,
        new_correction,
        new_module_hint,
    ):
        return True

    stem_new = normalize_summary_stem(new_summary)
    stem_old = normalize_summary_stem(old_summary)
    if stem_new and stem_old == stem_new:
        om = normalize_patch_topic_key(old_module)
        nm = normalize_patch_topic_key(new_module_hint)
        if nm and nm == om:
            return True
        if not nm and not om:
            return True

    return False


def load_kb_patches_jsonl(path: str) -> List[Dict[str, Any]]:
    if not os.path.isfile(path):
        return []
    rows: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def atomic_write_kb_patches_jsonl(path: str, records: List[Dict[str, Any]]) -> None:
    target = os.path.abspath(path)
    patches_dir = os.path.dirname(target)
    if patches_dir and not os.path.isdir(patches_dir):
        os.makedirs(patches_dir, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=patches_dir or None,
        prefix="kb_logic_patches.",
        suffix=".tmp",
        text=True,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            for row in records:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        os.replace(tmp_path, target)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def read_optional_string(arguments: Dict[str, Any], key: str) -> str:
    value = arguments.get(key)
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError("'{0}' must be a string.".format(key))
    return value.strip()


@register_tool(
    name="askreolink",
    title="Reolink 用例知识库（askreolink）",
    description=(
        "在本机执行 Reolink 禅道测试用例知识库检索脚本，用于查询业务逻辑与用例依据。"
        " 检索范围包含禅道导出用例、补充知识以及 kb_logic_patches.jsonl（MCP update_reolink_kb 写入的逻辑补丁）。"
        " 等价于在终端运行：python <脚本路径> <问题> [--top N] [--module 关键字] [--brief|--full]。"
        " 脚本默认路径为 D:\\reolink_knowledge\\ask_reolink_testcase_kb.py，"
        " 可通过环境变量 ASKREOLINK_SCRIPT / ASKREOLINK_PYTHON / ASKREOLINK_TIMEOUT 覆盖；"
        " 补丁文件路径可与 MCP 一致，使用 REOLINK_KB_PATCHES_PATH。"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "要向知识库检索的问题或关键词（对应脚本的 question 参数）。",
            },
            "top": {
                "type": "integer",
                "minimum": 1,
                "maximum": 50,
                "default": 5,
                "description": "返回前 N 条命中结果，对应脚本的 --top。",
            },
            "module": {
                "type": "string",
                "description": "仅在模块路径包含该关键字的用例中搜索，对应脚本的 --module。",
            },
            "brief": {
                "type": "boolean",
                "default": False,
                "description": "为 true 时对应脚本的 --brief。",
            },
            "full": {
                "type": "boolean",
                "default": False,
                "description": "为 true 时对应脚本的 --full。",
            },
        },
        "required": ["query"],
        "additionalProperties": False,
    },
)
def askreolink_tool(arguments: Dict[str, Any]) -> Dict[str, Any]:
    query = read_required_string(arguments, "query")
    top = arguments.get("top", 5)
    if top is None:
        top = 5
    if isinstance(top, bool) or not isinstance(top, int):
        raise ValueError("'top' must be an integer between 1 and 50.")
    if top < 1 or top > 50:
        raise ValueError("'top' must be an integer between 1 and 50.")

    module = arguments.get("module", "")
    if module is None:
        module = ""
    if not isinstance(module, str):
        raise ValueError("'module' must be a string.")

    brief = arguments.get("brief", False)
    full = arguments.get("full", False)
    if not isinstance(brief, bool):
        raise ValueError("'brief' must be a boolean.")
    if not isinstance(full, bool):
        raise ValueError("'full' must be a boolean.")

    script_path = askreolink_script_path()
    if not os.path.isfile(script_path):
        raise ValueError(
            "知识库脚本不存在：{0}。请安装知识库或设置环境变量 ASKREOLINK_SCRIPT 指向 ask_reolink_testcase_kb.py。".format(
                script_path
            )
        )

    python_exe = askreolink_python_executable()
    cmd = [python_exe, script_path, query, "--top", str(top)]
    if module.strip():
        cmd.extend(["--module", module.strip()])
    if brief:
        cmd.append("--brief")
    if full:
        cmd.append("--full")

    try:
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=askreolink_timeout_seconds(),
            cwd=os.path.dirname(script_path) or None,
        )
    except subprocess.TimeoutExpired:
        raise ValueError(
            "知识库查询超时（{0}s）。可通过环境变量 ASKREOLINK_TIMEOUT 调整上限（最大 600）。".format(
                askreolink_timeout_seconds()
            )
        )
    except OSError as exc:
        raise ValueError("无法启动知识库脚本：{0}".format(exc))

    return {
        "script": script_path,
        "command": cmd,
        "exit_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


@register_tool(
    name="askcamovue",
    title="Camovue 本地知识库（askcamovue）",
    description=(
        "在本机执行 Camovue 云服务套餐本地知识库检索脚本，用于查询套餐规则、续费与共享等业务问答。"
        " 等价于在终端运行：python <脚本路径> <问题> [--top N] [--full]。"
        " 脚本默认路径为 C:\\Users\\Reolink\\.cursor\\ask_camovue_kb.py，"
        " 可通过环境变量 ASKCAMOVUE_SCRIPT / ASKCAMOVUE_PYTHON / ASKCAMOVUE_TIMEOUT 覆盖。"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "要向 Camovue 本地知识库检索的问题或关键词。",
            },
            "top": {
                "type": "integer",
                "minimum": 1,
                "maximum": 50,
                "default": 3,
                "description": "返回前 N 个命中主题，对应脚本的 --top（脚本默认 3）。",
            },
            "full": {
                "type": "boolean",
                "default": False,
                "description": "为 true 时显示完整补充说明，对应脚本的 --full。",
            },
        },
        "required": ["query"],
        "additionalProperties": False,
    },
)
def askcamovue_tool(arguments: Dict[str, Any]) -> Dict[str, Any]:
    query = read_required_string(arguments, "query")
    top = arguments.get("top", 3)
    if top is None:
        top = 3
    if isinstance(top, bool) or not isinstance(top, int):
        raise ValueError("'top' must be an integer between 1 and 50.")
    if top < 1 or top > 50:
        raise ValueError("'top' must be an integer between 1 and 50.")

    full = arguments.get("full", False)
    if not isinstance(full, bool):
        raise ValueError("'full' must be a boolean.")

    script_path = askcamovue_script_path()
    if not os.path.isfile(script_path):
        raise ValueError(
            "Camovue 知识库脚本不存在：{0}。请安装知识库或设置环境变量 ASKCAMOVUE_SCRIPT 指向 ask_camovue_kb.py。".format(
                script_path
            )
        )

    python_exe = askcamovue_python_executable()
    cmd = [python_exe, script_path, query, "--top", str(top)]
    if full:
        cmd.append("--full")

    try:
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=askcamovue_timeout_seconds(),
            cwd=os.path.dirname(script_path) or None,
        )
    except subprocess.TimeoutExpired:
        raise ValueError(
            "Camovue 知识库查询超时（{0}s）。可通过环境变量 ASKCAMOVUE_TIMEOUT 调整上限（最大 600）。".format(
                askcamovue_timeout_seconds()
            )
        )
    except OSError as exc:
        raise ValueError("无法启动 Camovue 知识库脚本：{0}".format(exc))

    return {
        "script": script_path,
        "command": cmd,
        "exit_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


@register_tool(
    name="update_reolink_kb",
    title="更新 Reolink 知识库逻辑",
    description=(
        "提交对 Reolink 用例知识库的业务逻辑更正或补充说明，供团队通过 MCP 统一写入。"
        " kb_logic_patches.jsonl 无需单独建索引：ask_reolink_testcase_kb.py 每次查询都会重新加载该文件并与禅道用例一同检索。"
        " 若存在更新脚本（默认与检索脚本同目录下的 update_reolink_testcase_kb.py，"
        " 或由环境变量 REOLINK_KB_UPDATE_SCRIPT 指定），则执行 python <脚本> 并通过标准输入写入 UTF-8 JSON，"
        " JSON 字段包含：summary、correction、module_hint（可选）、author（可选）、submitted_at（UTC ISO）。"
        " 若脚本不存在，则把一条 JSON 记录写入 kb_logic_patches.jsonl（路径可由 REOLINK_KB_PATCHES_PATH"
        " 覆盖）。写入前会移除：与 topic_key 冲突的旧补丁、与本次正文完全重复的条目、"
        " 以及与本次「同一标题茎 + 同一 module_hint」的旧条目（视为重复修订）。"
        " 业务约束：若摘要或更正说明中出现「批量续费」，则 correction 必须同时写明所选记录须属同一国家组"
        "（须含「国家组」及一致性用语，或「同一国家组」），否则提交会被拒绝。"
        " 相关环境变量：REOLINK_KB_ROOT、REOLINK_KB_UPDATE_SCRIPT、REOLINK_KB_PATCHES_PATH、"
        "ASKREOLINK_PYTHON、REOLINK_KB_UPDATE_TIMEOUT（秒，最大 600）。"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": "更正标题或一句话摘要，便于检索与审计。",
            },
            "correction": {
                "type": "string",
                "description": (
                    "完整的更正说明、规则或逻辑描述（将写入知识库或补丁文件）。"
                    " 若摘要或本字段涉及「批量续费」，须在本字段中明确：批量续费仅允许同一国家组内的记录"
                    "（出现「国家组」及一致/相同/统一等表述，或使用「同一国家组」）。"
                ),
            },
            "module_hint": {
                "type": "string",
                "description": "可选，模块路径或功能域关键字，便于归类。",
            },
            "author": {
                "type": "string",
                "description": "可选，提交人标识（账号或姓名）。",
            },
            "topic_key": {
                "type": "string",
                "description": (
                    "可选，冲突归并键：同一 topic_key 仅保留本条（写入前删除同键旧记录）；"
                    " 另会自动删除完全重复的正文、以及同标题茎且同 module_hint 的旧记录。"
                    " 不传 topic_key 时依次使用 normalize(module_hint)、normalize(summary)。"
                    " 若多条旧补丁 module_hint 写法不同但语义相同，请显式传同一 topic_key。"
                ),
            },
        },
        "required": ["summary", "correction"],
        "additionalProperties": False,
    },
)
def update_reolink_kb_tool(arguments: Dict[str, Any]) -> Dict[str, Any]:
    summary = read_required_string(arguments, "summary")
    correction = read_required_string(arguments, "correction")
    ensure_batch_renewal_country_group_consistency(summary=summary, correction=correction)
    module_hint = read_optional_string(arguments, "module_hint")
    author = read_optional_string(arguments, "author")
    topic_key_arg = read_optional_string(arguments, "topic_key")

    topic_key_canonical = compute_patch_topic_key(
        summary=summary,
        module_hint=module_hint,
        topic_key_arg=topic_key_arg,
    )
    if not topic_key_canonical:
        raise ValueError(
            "无法计算 topic_key：请填写非空的 summary，或提供 module_hint / topic_key。"
        )

    stdin_payload: Dict[str, Any] = {
        "summary": summary,
        "correction": correction,
        "module_hint": module_hint,
        "author": author,
        "topic_key": topic_key_canonical,
        "submitted_at": datetime.now(timezone.utc).isoformat(),
    }

    script_path = update_reolink_script_path()
    kb_root = reolink_kb_root_dir()
    if os.path.isfile(script_path):
        python_exe = askreolink_python_executable()
        cmd = [python_exe, script_path]
        stdin_text = json.dumps(stdin_payload, ensure_ascii=False)
        try:
            completed = subprocess.run(
                cmd,
                input=stdin_text,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=update_reolink_timeout_seconds(),
                cwd=kb_root or None,
            )
        except subprocess.TimeoutExpired:
            raise ValueError(
                "知识库更新脚本执行超时（{0}s）。可通过环境变量 REOLINK_KB_UPDATE_TIMEOUT 调整（最大 600）。".format(
                    update_reolink_timeout_seconds()
                )
            )
        except OSError as exc:
            raise ValueError("无法启动知识库更新脚本：{0}".format(exc))

        return {
            "mode": "script",
            "script": script_path,
            "kb_root": kb_root,
            "command": cmd,
            "exit_code": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "topic_key": topic_key_canonical,
        }

    if not os.path.isdir(kb_root):
        raise ValueError(
            "知识库根目录不存在：{0}。请设置 REOLINK_KB_ROOT，或安装检索脚本所在目录，"
            "或提供可执行的 REOLINK_KB_UPDATE_SCRIPT。".format(kb_root)
        )

    patches_path = reolink_kb_patches_path()

    existing = load_kb_patches_jsonl(patches_path)
    kept = [
        row
        for row in existing
        if not patch_row_should_be_replaced(
            row,
            new_summary=summary,
            new_correction=correction,
            new_module_hint=module_hint,
            new_topic_key=topic_key_canonical,
        )
    ]
    removed_conflicting_rows = len(existing) - len(kept)

    record = dict(stdin_payload)
    merged_records = kept + [record]

    try:
        atomic_write_kb_patches_jsonl(patches_path, merged_records)
    except OSError as exc:
        raise ValueError("无法写入补丁文件 {0}：{1}".format(patches_path, exc))

    return {
        "mode": "patch_file",
        "kb_root": kb_root,
        "patches_path": patches_path,
        "topic_key": topic_key_canonical,
        "removed_conflicting_rows": removed_conflicting_rows,
        "record": record,
    }


def dispatch_request(
    body: Dict[str, Any],
    *,
    session_id: Optional[str] = None,
    protocol_version: str = MCP_PROTOCOL_VERSION,
):
    if body.get("jsonrpc") != "2.0":
        raise JsonRpcRequestError(
            -32600,
            "Invalid Request: 'jsonrpc' must be '2.0'.",
        )

    method = body.get("method")
    if not isinstance(method, str) or not method.strip():
        raise JsonRpcRequestError(
            -32600,
            "Invalid Request: 'method' must be a non-empty string.",
        )

    params = ensure_object(body.get("params"), "params")

    if method == "initialize":
        negotiated_protocol_version = negotiate_protocol_version(
            params.get("protocolVersion")
        )
        new_session_id = create_session(negotiated_protocol_version)
        result = {
            "protocolVersion": negotiated_protocol_version,
            "capabilities": {
                "tools": {"listChanged": False},
                "resources": {"listChanged": False},
                "prompts": {"listChanged": False},
            },
            "serverInfo": {
                "name": SERVER_NAME,
                "version": SERVER_VERSION,
            },
            "instructions": (
                "Use 'tools/list' to inspect tools, then call them with "
                "'tools/call'."
            ),
        }
        return notification_or_result(
            body,
            result,
            session_id=new_session_id,
            protocol_version=negotiated_protocol_version,
        )

    if method in {"notifications/initialized", "notifications/cancelled"}:
        return accepted_response(
            session_id=session_id,
            protocol_version=protocol_version,
        )

    if method == "ping":
        return notification_or_result(
            body,
            {},
            session_id=session_id,
            protocol_version=protocol_version,
        )

    if method == "tools/list":
        result = {"tools": [tool.as_dict() for tool in TOOLS.values()]}
        return notification_or_result(
            body,
            result,
            session_id=session_id,
            protocol_version=protocol_version,
        )

    if method == "resources/list":
        return notification_or_result(
            body,
            {"resources": []},
            session_id=session_id,
            protocol_version=protocol_version,
        )

    if method == "prompts/list":
        return notification_or_result(
            body,
            {"prompts": []},
            session_id=session_id,
            protocol_version=protocol_version,
        )

    if method == "tools/call":
        tool_name = params.get("name")
        if not isinstance(tool_name, str) or not tool_name.strip():
            raise JsonRpcRequestError(
                -32602,
                "Invalid params: 'name' must be a non-empty string.",
            )

        arguments = ensure_object(params.get("arguments"), "arguments")
        tool = TOOLS.get(tool_name)
        if tool is None:
            return notification_or_result(
                body,
                tool_text_result(
                    "Tool '{0}' was not found.".format(tool_name),
                    is_error=True,
                ),
                session_id=session_id,
                protocol_version=protocol_version,
            )

        try:
            value = tool.handler(arguments)
        except ValueError as exc:
            return notification_or_result(
                body,
                tool_text_result(str(exc), is_error=True),
                session_id=session_id,
                protocol_version=protocol_version,
            )
        except Exception:
            app.logger.exception("Tool execution failed: %s", tool_name)
            return notification_or_result(
                body,
                tool_text_result(
                    "Tool '{0}' failed on the server.".format(tool_name),
                    is_error=True,
                ),
                session_id=session_id,
                protocol_version=protocol_version,
            )

        return notification_or_result(
            body,
            tool_text_result(value),
            session_id=session_id,
            protocol_version=protocol_version,
        )

    raise JsonRpcRequestError(
        -32601,
        "Method '{0}' not found.".format(method),
        status=404,
    )


@app.get("/")
def index():
    return jsonify(
        {
            "name": SERVER_NAME,
            "version": SERVER_VERSION,
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "supportedProtocolVersions": list(SUPPORTED_PROTOCOL_VERSIONS),
            "message": "Flask MCP server is running.",
            "cursorConfigPath": ".cursor/mcp.json",
            "endpoints": {
                "/healthz": "Health check endpoint",
                "/mcp": "POST JSON-RPC endpoint for MCP",
            },
        }
    )


@app.get("/healthz")
def healthz():
    return jsonify({"status": "ok"})


@app.route("/mcp", methods=["GET", "POST", "DELETE"])
def mcp_endpoint():
    origin = request.headers.get("Origin")
    if not origin_is_allowed(origin):
        return jsonrpc_error(
            None,
            -32099,
            "Origin '{0}' is not allowed.".format(origin),
            status=403,
        )

    if request.method == "GET":
        response = jsonify(
            {
                "message": (
                    "This MCP endpoint only supports POST requests and "
                    "session cleanup via DELETE. SSE is not enabled."
                )
            }
        )
        response.status_code = 405
        response.headers["Allow"] = "POST, DELETE"
        return apply_response_headers(response)

    session_id = request.headers.get("MCP-Session-Id")
    protocol_version = MCP_PROTOCOL_VERSION

    if request.method == "DELETE":
        try:
            protocol_version = require_session_protocol(session_id)
        except JsonRpcRequestError as exc:
            return jsonrpc_error(
                None,
                exc.code,
                exc.message,
                status=exc.status,
                data=exc.data,
            )

        SESSIONS.pop(session_id, None)
        response = app.response_class("", status=204)
        return apply_response_headers(response, protocol_version=protocol_version)

    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonrpc_error(
            None,
            -32700,
            "Parse error: request body must be valid JSON.",
            status=400,
        )

    if is_jsonrpc_response_message(body):
        try:
            protocol_version = require_session_protocol(session_id)
            protocol_version = validate_protocol_header(
                request.headers.get("MCP-Protocol-Version"),
                protocol_version,
            )
        except JsonRpcRequestError as exc:
            return jsonrpc_error(
                body.get("id"),
                exc.code,
                exc.message,
                status=exc.status,
                data=exc.data,
            )
        return accepted_response(
            session_id=session_id,
            protocol_version=protocol_version,
        )

    try:
        if body.get("method") != "initialize":
            protocol_version = require_session_protocol(session_id)
            protocol_version = validate_protocol_header(
                request.headers.get("MCP-Protocol-Version"),
                protocol_version,
            )

        return dispatch_request(
            body,
            session_id=session_id,
            protocol_version=protocol_version,
        )
    except JsonRpcRequestError as exc:
        return jsonrpc_error(
            body.get("id"),
            exc.code,
            exc.message,
            status=exc.status,
            data=exc.data,
            session_id=session_id if session_id in SESSIONS else None,
            protocol_version=protocol_version,
        )
    except Exception:
        app.logger.exception("Unhandled MCP request error")
        return jsonrpc_error(
            body.get("id"),
            -32603,
            "Internal error.",
            status=500,
            session_id=session_id if session_id in SESSIONS else None,
            protocol_version=protocol_version,
        )


if __name__ == "__main__":
    # host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "9999"))
    debug = os.getenv("DEBUG", "").lower() in {"1", "true", "yes", "on"}
    app.run(host="0.0.0.0", port=port, debug=debug)
