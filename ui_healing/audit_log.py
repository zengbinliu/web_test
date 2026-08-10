# -*- coding: utf-8 -*-
"""自愈事件审计日志。"""

import json
from datetime import datetime
from typing import Any, Dict

from utils.path_extra import rel
from utils.logger import get_logger

logger = get_logger(__name__)


def append_audit_record(record: Dict[str, Any]) -> None:
    """追加一条 JSONL 审计；缺 timestamp 时自动补上。"""
    record = dict(record)
    record.setdefault("timestamp", datetime.now().isoformat(timespec="seconds"))
    audit_dir = rel("data/healing_audit")
    audit_dir.mkdir(parents=True, exist_ok=True)
    file_path = audit_dir / f"healing_{datetime.now():%Y%m%d}.jsonl"
    with open(file_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    logger.info(
        "元素自愈审计: %s/%s %s -> %s",
        record.get("yaml"),
        record.get("key"),
        record.get("old"),
        record.get("new"),
    )
