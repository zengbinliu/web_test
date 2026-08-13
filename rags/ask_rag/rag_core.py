from __future__ import annotations

import hashlib
import json
import math
import pathlib
import re
import time
from typing import Any, Callable

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parent
RAG_DATA_DIR = ROOT / "data" / "rag"
RAG_VECTORS_PATH = RAG_DATA_DIR / "vectors.npy"
RAG_META_PATH = RAG_DATA_DIR / "chunks.jsonl"
RAG_MANIFEST_PATH = RAG_DATA_DIR / "manifest.json"

PUNCT_RE = re.compile(r"[\s\t\r\n,.;:!?，。；：！？、/\\|_=+()\[\]{}<>《》“”\"'`-]+")
CJK_RE = re.compile(r"[\u4e00-\u9fff]")
DEFAULT_DIM = 8192
DEFAULT_STEP_CHUNK_THRESHOLD = 4


def normalize(text: Any) -> str:
    return PUNCT_RE.sub("", str(text or "")).lower()


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


def tokenize_for_rag(text: str) -> list[str]:
    tokens = split_terms(text)
    compact = normalize(text)
    if compact and len(compact) > 2:
        for size in (2, 3):
            if len(compact) >= size:
                for idx in range(len(compact) - size + 1):
                    tokens.append(compact[idx : idx + size])
    return unique_keep_order(tokens)


def hash_token(token: str, dim: int) -> int:
    digest = hashlib.md5(token.encode("utf-8")).hexdigest()
    return int(digest, 16) % dim


def text_to_vector(text: str, dim: int = DEFAULT_DIM) -> np.ndarray:
    vec = np.zeros(dim, dtype=np.float32)
    tokens = tokenize_for_rag(text)
    if not tokens:
        return vec
    for token in tokens:
        vec[hash_token(token, dim)] += 1.0
    nonzero = vec > 0
    if not np.any(nonzero):
        return vec
    vec[nonzero] = 1.0 + np.log(vec[nonzero])
    norm = float(np.linalg.norm(vec))
    if norm > 0:
        vec /= norm
    return vec


def clean_line(text: Any) -> str:
    return " ".join(str(text or "").split())


def format_step_block(step: dict[str, Any]) -> str:
    lines = []
    desc = clean_line(step.get("desc", ""))
    expect = clean_line(step.get("expect", ""))
    if desc:
        lines.append("步骤: %s" % desc)
    if expect:
        lines.append("预期: %s" % expect)
    return "\n".join(lines)


def case_header(case: dict[str, Any]) -> str:
    lines = [
        "标题: %s" % clean_line(case.get("title", "")),
        "模块: %s" % clean_line(case.get("module_path_text", "")),
    ]
    precondition = clean_line(case.get("precondition", ""))
    keywords = clean_line(case.get("keywords", ""))
    if precondition:
        lines.append("前置条件: %s" % precondition)
    if keywords:
        lines.append("关键词: %s" % keywords)
    return "\n".join(lines)


def case_to_chunks(case: dict[str, Any], step_threshold: int = DEFAULT_STEP_CHUNK_THRESHOLD) -> list[dict[str, Any]]:
    steps = case.get("steps") or []
    header = case_header(case)
    case_id = int(case.get("case_id") or 0)
    source_type = str(case.get("source_type") or "testcase")
    chunks: list[dict[str, Any]] = []

    if len(steps) <= step_threshold:
        body_parts = [header]
        for step in steps:
            block = format_step_block(step)
            if block:
                body_parts.append(block)
        chunks.append(
            {
                "case_id": case_id,
                "chunk_id": "%s:0" % case_id,
                "chunk_type": "case",
                "source_type": source_type,
                "title": clean_line(case.get("title", "")),
                "module_path_text": clean_line(case.get("module_path_text", "")),
                "link": clean_line(case.get("link", "")),
                "text": "\n".join(body_parts).strip(),
            }
        )
        return chunks

    chunks.append(
        {
            "case_id": case_id,
            "chunk_id": "%s:summary" % case_id,
            "chunk_type": "summary",
            "source_type": source_type,
            "title": clean_line(case.get("title", "")),
            "module_path_text": clean_line(case.get("module_path_text", "")),
            "link": clean_line(case.get("link", "")),
            "text": header,
        }
    )
    for idx, step in enumerate(steps, 1):
        block = format_step_block(step)
        if not block:
            continue
        chunks.append(
            {
                "case_id": case_id,
                "chunk_id": "%s:%s" % (case_id, idx),
                "chunk_type": "step",
                "source_type": source_type,
                "title": clean_line(case.get("title", "")),
                "module_path_text": clean_line(case.get("module_path_text", "")),
                "link": clean_line(case.get("link", "")),
                "text": "%s\n%s" % (header, block),
            }
        )
    return chunks


def cases_to_chunks(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for case in cases:
        chunks.extend(case_to_chunks(case))
    return chunks


def write_jsonl(path: pathlib.Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_jsonl(path: pathlib.Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


class RAGIndex:
    def __init__(self, dim: int = DEFAULT_DIM) -> None:
        self.dim = dim
        self.chunks: list[dict[str, Any]] = []
        self.vectors: np.ndarray | None = None
        self.manifest: dict[str, Any] = {}

    @property
    def ready(self) -> bool:
        return self.vectors is not None and len(self.chunks) > 0

    def _encode_chunks(self) -> None:
        if not self.chunks:
            self.vectors = np.zeros((0, self.dim), dtype=np.float32)
            return
        batch_size = 512
        vector_rows = []
        for start in range(0, len(self.chunks), batch_size):
            batch = self.chunks[start : start + batch_size]
            vector_rows.append(
                np.vstack([text_to_vector(chunk["text"], self.dim) for chunk in batch]).astype(np.float32)
            )
        self.vectors = np.vstack(vector_rows) if len(vector_rows) > 1 else vector_rows[0]

    def build_from_chunks(
        self,
        chunks: list[dict[str, Any]],
        *,
        extra_manifest: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """用已切好的 chunk 构建向量索引（供非用例语料复用）。"""
        self.chunks = list(chunks)
        self._encode_chunks()
        case_ids = set()
        for chunk in self.chunks:
            raw = chunk.get("case_id")
            if raw is None or raw == "":
                continue
            try:
                case_ids.add(int(raw))
            except (TypeError, ValueError):
                continue
        self.manifest = {
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "chunk_total": len(self.chunks),
            "case_total": len(case_ids),
            "dim": self.dim,
        }
        if extra_manifest:
            self.manifest.update(extra_manifest)
        return self.manifest

    def build(self, cases: list[dict[str, Any]]) -> dict[str, Any]:
        return self.build_from_chunks(cases_to_chunks(cases))

    def save(self, data_dir: pathlib.Path | None = None) -> None:
        data_dir = data_dir or RAG_DATA_DIR
        data_dir.mkdir(parents=True, exist_ok=True)
        write_jsonl(data_dir / "chunks.jsonl", self.chunks)
        if self.vectors is None:
            np.save(data_dir / "vectors.npy", np.zeros((0, self.dim), dtype=np.float32))
        else:
            np.save(data_dir / "vectors.npy", self.vectors)
        (data_dir / "manifest.json").write_text(json.dumps(self.manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    def load(self, data_dir: pathlib.Path | None = None) -> bool:
        data_dir = data_dir or RAG_DATA_DIR
        vectors_path = data_dir / "vectors.npy"
        meta_path = data_dir / "chunks.jsonl"
        manifest_path = data_dir / "manifest.json"
        if not vectors_path.exists() or not meta_path.exists():
            return False
        self.chunks = read_jsonl(meta_path)
        self.vectors = np.load(vectors_path).astype(np.float32)
        if manifest_path.exists():
            self.manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        else:
            self.manifest = {"chunk_total": len(self.chunks), "dim": self.dim}
        self.dim = int(self.manifest.get("dim") or self.vectors.shape[1] if self.vectors.size else DEFAULT_DIM)
        return self.ready

    def search(
        self,
        question: str,
        top_k: int = 12,
        module_filter: str = "",
    ) -> list[dict[str, Any]]:
        if not self.ready or self.vectors is None or not question.strip():
            return []

        query_vec = text_to_vector(question, self.dim)
        if float(np.linalg.norm(query_vec)) <= 0:
            return []

        scores = self.vectors @ query_vec
        module_filter_norm = normalize(module_filter)
        ranked_indices = np.argsort(-scores)
        results: list[dict[str, Any]] = []
        for idx in ranked_indices:
            score = float(scores[idx])
            if score <= 0:
                break
            chunk = self.chunks[int(idx)]
            if module_filter_norm and module_filter_norm not in normalize(chunk.get("module_path_text", "")):
                continue
            item = dict(chunk)
            item["vector_score"] = score
            results.append(item)
            if len(results) >= top_k:
                break
        return results


def aggregate_vector_hits(
    vector_hits: list[dict[str, Any]],
    cases_by_id: dict[int, dict[str, Any]],
) -> dict[int, dict[str, Any]]:
    grouped: dict[int, dict[str, Any]] = {}
    for hit in vector_hits:
        case_id = int(hit.get("case_id") or 0)
        if case_id not in cases_by_id:
            continue
        current = grouped.get(case_id)
        if current is None or hit["vector_score"] > current["vector_score"]:
            grouped[case_id] = {
                "case": cases_by_id[case_id],
                "vector_score": float(hit["vector_score"]),
                "chunk_id": hit.get("chunk_id", ""),
                "chunk_text": hit.get("text", ""),
                "chunk_type": hit.get("chunk_type", ""),
            }
    return grouped


def merge_hybrid_results(
    keyword_results: list[dict[str, Any]],
    vector_groups: dict[int, dict[str, Any]],
    *,
    keyword_weight: float = 0.55,
    vector_weight: float = 0.45,
) -> list[dict[str, Any]]:
    merged: dict[int, dict[str, Any]] = {}

    max_keyword = max((item["score"] for item in keyword_results), default=0)
    for item in keyword_results:
        case_id = int(item["case"].get("case_id") or 0)
        keyword_norm = item["score"] / max_keyword if max_keyword > 0 else 0.0
        merged[case_id] = {
            "case": item["case"],
            "score": item["score"],
            "hits": item.get("hits", []),
            "keyword_score": item["score"],
            "keyword_norm": keyword_norm,
            "vector_score": 0.0,
            "vector_norm": 0.0,
            "hybrid_score": keyword_norm * keyword_weight,
            "chunk_id": "",
            "chunk_text": "",
            "chunk_type": "",
        }

    max_vector = max((item["vector_score"] for item in vector_groups.values()), default=0.0)
    for case_id, item in vector_groups.items():
        vector_norm = item["vector_score"] / max_vector if max_vector > 0 else 0.0
        hybrid_part = vector_norm * vector_weight
        if case_id in merged:
            merged[case_id]["vector_score"] = item["vector_score"]
            merged[case_id]["vector_norm"] = vector_norm
            merged[case_id]["hybrid_score"] = merged[case_id]["keyword_norm"] * keyword_weight + hybrid_part
            merged[case_id]["chunk_id"] = item.get("chunk_id", "")
            merged[case_id]["chunk_text"] = item.get("chunk_text", "")
            merged[case_id]["chunk_type"] = item.get("chunk_type", "")
        else:
            merged[case_id] = {
                "case": item["case"],
                "score": int(round(item["vector_score"] * 100)),
                "hits": ["vector"],
                "keyword_score": 0,
                "keyword_norm": 0.0,
                "vector_score": item["vector_score"],
                "vector_norm": vector_norm,
                "hybrid_score": hybrid_part,
                "chunk_id": item.get("chunk_id", ""),
                "chunk_text": item.get("chunk_text", ""),
                "chunk_type": item.get("chunk_type", ""),
            }

    results = list(merged.values())
    results.sort(
        key=lambda item: (
            -item["hybrid_score"],
            -item["keyword_score"],
            -item["vector_score"],
            item["case"].get("module_path_text", ""),
            item["case"].get("case_id", 0),
        )
    )
    return results


def hybrid_search_cases(
    cases: list[dict[str, Any]],
    question: str,
    *,
    top_n: int,
    module_filter: str = "",
    index: RAGIndex | None = None,
    keyword_search: Callable[..., list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    keyword_results = keyword_search(cases, question, top_n=max(top_n * 4, 20), module_filter=module_filter)
    if index is None or not index.ready:
        return keyword_results[:top_n]

    vector_hits = index.search(question, top_k=max(top_n * 3, 15), module_filter=module_filter)
    cases_by_id = {int(case["case_id"]): case for case in cases}
    vector_groups = aggregate_vector_hits(vector_hits, cases_by_id)
    merged = merge_hybrid_results(keyword_results, vector_groups)
    return merged[:top_n]


def build_or_load_index(
    cases: list[dict[str, Any]],
    *,
    rebuild: bool = False,
    data_dir: pathlib.Path | None = None,
) -> RAGIndex:
    index = RAGIndex()
    data_dir = data_dir or RAG_DATA_DIR
    if not rebuild and index.load(data_dir):
        return index
    index.build(cases)
    index.save(data_dir)
    return index


def format_context_blocks(results: list[dict[str, Any]], limit: int = 5) -> list[str]:
    blocks: list[str] = []
    for idx, item in enumerate(results[:limit], 1):
        case = item["case"]
        chunk_text = clean_line(item.get("chunk_text", ""))
        if not chunk_text:
            chunk_text = case_header(case)
            for step in (case.get("steps") or [])[:3]:
                block = format_step_block(step)
                if block:
                    chunk_text += "\n" + block
        blocks.append(
            "[依据 %s] case_id=%s\n标题: %s\n模块: %s\n内容:\n%s\n链接: %s"
            % (
                idx,
                case.get("case_id", ""),
                clean_line(case.get("title", "")),
                clean_line(case.get("module_path_text", "")),
                chunk_text,
                clean_line(case.get("link", "")),
            )
        )
    return blocks
