from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional


class RequestValidationError(ValueError):
    pass


def _require_text(payload: Any, field: str, max_length: int) -> str:
    if not isinstance(payload, dict):
        raise RequestValidationError("请求体必须是 JSON 对象")

    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise RequestValidationError(f"{field} 不能为空")
    if len(value) > max_length:
        raise RequestValidationError(f"{field} 不能超过 {max_length} 个字符")
    return value.strip()


@dataclass(frozen=True)
class QueryRequest:
    natural_language: str

    @classmethod
    def from_payload(cls, payload: Any) -> "QueryRequest":
        return cls(_require_text(payload, "natural_language", 4000))


@dataclass(frozen=True)
class ExecuteRequest:
    sql: str
    confirm: bool = False
    confirmation_token: Optional[str] = None

    @classmethod
    def from_payload(cls, payload: Any) -> "ExecuteRequest":
        sql = _require_text(payload, "sql", 100_000)
        confirm = payload.get("confirm", False)
        if not isinstance(confirm, bool):
            raise RequestValidationError("confirm 必须是布尔值")
        confirmation_token = payload.get("confirmation_token")
        if confirmation_token is not None:
            if not isinstance(confirmation_token, str) or len(confirmation_token) > 2048:
                raise RequestValidationError("confirmation_token 格式无效")
        return cls(sql=sql, confirm=confirm, confirmation_token=confirmation_token)


@dataclass(frozen=True)
class APIResponse:
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None
    requires_confirmation: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
