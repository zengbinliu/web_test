from __future__ import annotations

import argparse
import pathlib
import sys

from rag_core import RAGIndex, build_or_load_index

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from ask_reolink_testcase_kb import configure_output, load_cases  # noqa: E402


def build_index(rebuild: bool = False) -> RAGIndex:
    cases = load_cases()
    return build_or_load_index(cases, rebuild=rebuild)


def main() -> int:
    configure_output()
    parser = argparse.ArgumentParser(description="构建 Reolink 知识库 RAG 向量索引。")
    parser.add_argument("--rebuild", action="store_true", help="强制重建索引")
    args = parser.parse_args()

    index = build_index(rebuild=args.rebuild)
    manifest = index.manifest or {}
    print(
        "RAG 索引完成: chunks=%s cases=%s dim=%s generated_at=%s"
        % (
            manifest.get("chunk_total", len(index.chunks)),
            manifest.get("case_total", ""),
            manifest.get("dim", index.dim),
            manifest.get("generated_at", ""),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
