# -*- coding: utf-8 -*-
"""将自愈后的选择器持久化到 page_ele YAML。"""

import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Tuple, Union

import yaml

from page_ele import page_ele_path
from page_ele.ui_healing.element_def import ElementDef, format_selector_for_yaml
from utils.path_extra import rel
from utils.logger import get_logger

logger = get_logger(__name__)


def _backup_yaml(path: Path) -> Path:
    """写回前备份到 healing_audit/yaml_backups，便于 review/回滚。"""
    backup_dir = rel("data/healing_audit/yaml_backups")
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"{path.stem}_{stamp}{path.suffix}"
    shutil.copy2(path, backup_path)
    logger.info("已备份 page_ele YAML: %s -> %s", path, backup_path)
    return backup_path


def _quote_yaml_scalar(value: str) -> str:
    """按需给 YAML 标量加单引号，避免 : 等特殊字符破坏解析。"""
    if not value:
        return "''"
    needs_quote = (
        any(ch in value for ch in ":{}[]&*#?|-<>=!%@\\\"")
        or value.startswith(("'", '"'))
        or " " in value
        or "\n" in value
    )
    if needs_quote:
        return "'" + value.replace("'", "''") + "'"
    return value


def _structured_field_lines(element: ElementDef) -> List[str]:
    """结构化块的子行（selector / locator_type / semantic / scope）。"""
    indent = "  "
    lines = [
        f"{indent}selector: {_quote_yaml_scalar(element.selector)}\n",
        f"{indent}locator_type: {element.locator_type}\n",
    ]
    if element.semantic:
        lines.append(f"{indent}semantic: {_quote_yaml_scalar(element.semantic)}\n")
    if element.scope:
        lines.append(f"{indent}scope: {_quote_yaml_scalar(element.scope)}\n")
    return lines


def _patch_yaml_text(raw: str, key: str, element: ElementDef) -> str:
    """在原 YAML 文本中替换目标键，尽量保留其余内容。"""
    lines = raw.splitlines(keepends=True)
    key_pattern = re.compile(rf"^({re.escape(key)})\s*:\s*(.*)$")
    structured_start = re.compile(rf"^{re.escape(key)}\s*:\s*$")

    for idx, line in enumerate(lines):
        if structured_start.match(line.rstrip("\n")):
            end = idx + 1
            while end < len(lines) and (lines[end].startswith("  ") or lines[end].strip() == ""):
                end += 1
            lines[idx + 1 : end] = _structured_field_lines(element)
            return "".join(lines)

        if not key_pattern.match(line.rstrip("\n")):
            continue

        new_value = format_selector_for_yaml(element, as_structured=False)
        if isinstance(new_value, str):
            lines[idx] = f"{key}: {_quote_yaml_scalar(new_value)}\n"
        else:
            lines[idx] = f"{key}:\n"
            lines[idx + 1 : idx + 1] = _structured_field_lines(element)
        return "".join(lines)

    raise KeyError(f"YAML 文件中未找到键: {key}")


def save_page_yaml_key(
    yaml_parts: Tuple[Union[str, Path], ...],
    key: str,
    element: ElementDef,
) -> Path:
    """备份后原子写回 page_ele YAML 中的单个键。"""
    path = page_ele_path(*yaml_parts)
    _backup_yaml(path)
    patched = _patch_yaml_text(path.read_text(encoding="utf-8"), key, element)
    yaml.safe_load(patched)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(patched, encoding="utf-8")
    tmp.replace(path)
    logger.info("已持久化元素选择器: %s -> %s", path, key)
    return path


def update_pd_value(pd: dict, key: str, element: ElementDef) -> None:
    """同步更新运行时 _pd，避免本用例后续步骤仍用旧选择器。"""
    pd[key] = format_selector_for_yaml(element, as_structured=bool(element.semantic or element.scope))
