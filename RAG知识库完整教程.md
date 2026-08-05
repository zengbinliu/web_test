# RAG 知识库完整教程

> 面向测试开发工程师，从零开始学习 RAG 知识库的原理、脚本开发与核心概念。
>
> 整理日期：2026-08-05

---

## 目录

1. [RAG 是什么](#一rag-是什么)
2. [整体架构](#二rag-整体架构)
3. [核心概念](#三核心概念逐个讲)
4. [完整问答流程](#四完整问答流程)
5. [建库流程 Indexing](#五建库流程indexing-详解)
6. [检索策略进阶](#六检索策略进阶)
7. [Python 脚本开发 RAG](#七python-脚本开发-rag-知识库)
8. [Top-K 详解](#八top-k-详解)
9. [Top-K 与 Top-P 的区别](#九top-k-与-top-p-的区别)
10. [学习地图](#十测试开发工程师的学习地图)
11. [评估 RAG 质量](#十一评估-rag-好不好)
12. [常见问题与对策](#十二常见问题与对策)
13. [Reolink 知识库对照](#十三reolink-知识库对照)
14. [RAG 怎么调优](#十四rag-怎么调优)

---

## 一、RAG 是什么

### 1.1 一句话定义

**RAG（Retrieval-Augmented Generation，检索增强生成）** = 先从知识库里**检索**相关内容，再让大模型**基于这些内容**生成答案。

```
传统 LLM：问题 → 模型凭记忆回答（容易编造、知识过时）
RAG：     问题 → 查知识库 → 把查到的内容塞进 Prompt → 模型回答
```

### 1.2 为什么需要 RAG

| 纯 LLM 的问题 | RAG 怎么解决 |
|---------------|--------------|
| 不知道公司内部业务规则 | 检索禅道用例、需求文档 |
| 容易「幻觉」编造 | 要求「仅依据提供的片段回答」 |
| 训练数据过时 | 知识库可随时更新 |
| 无法引用来源 | 可返回 case_id、文档链接 |

**测试开发场景举例：**

- 「云套餐续费后流量怎么算？」→ 检索历史用例 + 业务规则 → 给出有据可查的答案
- 「这个接口的错误码有哪些？」→ 检索 API 文档片段 → 准确列举

---

## 二、RAG 整体架构

RAG 脚本本质上就是两条流水线：

### 离线 Indexing（建库）

```
原始文档 → 切分 Chunk → 向量化 Embedding → 向量索引
```

### 在线 Query（问答）

```
用户问题 → 检索 Top-K → 拼 Prompt → LLM 生成答案
```

| 阶段 | 脚本职责 | 典型产出 |
|------|----------|----------|
| **Indexing（建库）** | 读文档 → 切块 → 向量化 → 存索引 | `chunks.jsonl`、`vectors.npy` |
| **Query（问答）** | 问题向量化 → 检索 → 拼上下文 → 调 LLM | 终端输出 / API 响应 |

**架构图：**

```
┌─────────────────────────────────────────────────────────┐
│                    RAG 知识库                            │
├──────────────────────┬──────────────────────────────────┤
│   离线 Indexing       │         在线 Query                │
│                      │                                  │
│  原始文档             │  用户问题                         │
│    ↓                 │    ↓                             │
│  清洗/结构化          │  问题向量化                       │
│    ↓                 │    ↓                             │
│  切分 Chunk          │  检索 Top-K  ←── 向量索引          │
│    ↓                 │    ↓                             │
│  Embedding           │  拼 Prompt                        │
│    ↓                 │    ↓                             │
│  存入向量索引         │  LLM 生成 → 答案 + 引用            │
└──────────────────────┴──────────────────────────────────┘
```

---

## 三、核心概念逐个讲

### 3.1 文档（Document）

知识的原始形态：

- 禅道测试用例 JSON
- 需求文档 Markdown / Word
- API 文档、FAQ、邮件模板

### 3.2 切块（Chunk）

大模型和检索都不能一次处理整本书，所以要**切成小块**。

```
一篇 5000 字需求文档
    ↓ 切分
[Chunk1: 功能概述] [Chunk2: 购买流程] [Chunk3: 异常场景] ...
```

**切分策略（测试场景很重要）：**

| 策略 | 适用 |
|------|------|
| 固定长度（500 字 + 重叠 50 字） | 通用文档 |
| 按段落 / 标题 | 结构化文档 |
| 按业务结构 | 测试用例（标题 + 步骤 + 预期） |
| 一步一个 chunk | 步骤很多的长用例 |

**原则：** chunk 太大 → 检索不精准；太小 → 上下文不完整。

### 3.3 向量化（Embedding）

把文本变成**数字向量**，语义相近的文本，向量距离更近。

```
"云套餐续费"  →  [0.12, -0.34, 0.56, ...]  (384 维)
"套餐自动续费" →  [0.11, -0.33, 0.55, ...]  (很接近)
"摄像头安装"  →  [0.89, 0.21, -0.12, ...]  (较远)
```

常见方案：

- **云端 API**：OpenAI `text-embedding-3-small`
- **本地模型**：`sentence-transformers` 多语言模型
- **轻量方案**：hash + TF-IDF 风格稀疏向量

### 3.4 向量索引（Vector Index）

存储所有 chunk 的向量，支持**快速相似度搜索**。

常见存储：

- 文件：`vectors.npy` + `chunks.jsonl`
- 向量库：Chroma、Milvus、Faiss、Qdrant

### 3.5 检索（Retrieval）

用户提问 → 问题也向量化 → 在索引里找**最相似的 Top-K 个 chunk**。

```
问题: "免费云套餐和付费云套餐区别？"
检索结果 Top-3:
  1. [case_1234] 相似度 0.92 - 免费云套餐购买流程...
  2. [case_5678] 相似度 0.87 - 付费云套餐权益说明...
  3. [case_9012] 相似度 0.81 - 套餐类型对比表...
```

### 3.6 增强（Augmentation）

把检索到的 chunk **拼进 Prompt**，作为 LLM 的「参考资料」：

```
系统提示：你是测试知识库助手，仅依据以下片段回答，不足则说明「依据不足」。

问题：免费云套餐和付费云套餐区别？

知识片段：
---
[case_1234] 免费云套餐购买流程...
---
[case_5678] 付费云套餐权益说明...
---

请回答并列出引用的 case_id。
```

### 3.7 生成（Generation）

LLM 基于 Prompt 生成最终答案。

常用参数（要**准确、少编造**）：

- `temperature=0.2`（低随机性）
- `top_p=0.9`
- 明确约束：「不要编造」「必须引用来源」

---

## 四、完整问答流程

以「云套餐续费后流量怎么算？」为例：

| 步骤 | 做什么 | 输入 → 输出 |
|------|--------|-------------|
| 1 | 用户提问 | 自然语言问题 |
| 2 | 问题预处理 | 提取关键词：云套餐、续费、流量 |
| 3 | 向量化 | 问题 → 384 维向量 |
| 4 | 检索 Top-5 | 5 个最相关 chunk |
| 5 | 重排序（可选） | 用更精细模型再排一次 |
| 6 | 拼 Prompt | 问题 + 5 个 chunk |
| 7 | LLM 生成 | 结构化答案 + 引用 |
| 8 | 后处理 | 格式化、校验、返回链接 |

---

## 五、建库流程（Indexing 详解）

```
原始数据
  ↓ 1. 采集/导出
testcases.jsonl / docs/*.md
  ↓ 2. 清洗
去 HTML、统一编码、去空行
  ↓ 3. 结构化
提取 title、steps、expect、module_path
  ↓ 4. 切分
case_to_chunks() → 每个 chunk 带 metadata
  ↓ 5. 向量化
每个 chunk.text → embedding 向量
  ↓ 6. 存储
chunks.jsonl + vectors.npy + manifest.json
```

**manifest.json 示例：**

```json
{
  "generated_at": "2026-08-05T12:00:00",
  "chunk_total": 1520,
  "case_total": 380,
  "dim": 384
}
```

---

## 六、检索策略进阶

### 6.1 纯向量检索

语义相似，但对**精确 ID、编号、套餐名**可能不够准。

### 6.2 关键词检索（BM25 / 稀疏向量）

擅长精确匹配：`case_id=12345`、`云套餐-仅带图`。

### 6.3 混合检索（Hybrid Search，生产常用）

```
最终得分 = α × 向量相似度 + (1-α) × 关键词得分
```

### 6.4 重排序（Rerank）

Top-K 粗检索 → 用 Rerank 模型精排 → 取 Top-3 给 LLM。

效果往往更好，但多一次 API 调用。

---

## 七、Python 脚本开发 RAG 知识库

### 7.1 环境准备

```bash
mkdir my_rag && cd my_rag
python -m venv .venv

# Windows
.venv\Scripts\activate

pip install numpy openai chromadb sentence-transformers
```

**依赖怎么选：**

| 库 | 用途 |
|----|------|
| `numpy` | 向量运算、存 `.npy` |
| `chromadb` | 开箱即用的向量库（初学推荐） |
| `sentence-transformers` | 本地 Embedding 模型 |
| `openai` | 云端 Embedding + LLM（可选） |

### 7.2 项目结构

```
my_rag/
├── data/
│   └── docs/          # 放原始 txt/md
├── index/             # 索引产物（自动生成）
├── ingest.py          # 建库脚本
├── ask.py             # 问答脚本
└── rag_utils.py       # 公共函数
```

### 7.3 文档加载 + 切分

```python
# rag_utils.py
from pathlib import Path

def load_text_files(data_dir: str) -> list[dict]:
    docs = []
    for path in Path(data_dir).glob("**/*"):
        if path.suffix.lower() in {".txt", ".md"}:
            docs.append({
                "doc_id": path.stem,
                "source": str(path),
                "text": path.read_text(encoding="utf-8"),
            })
    return docs


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """固定长度滑动窗口切分（最简单策略）"""
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start = end - overlap
    return [c.strip() for c in chunks if c.strip()]
```

### 7.4 Embedding

**方案 A：本地模型（推荐入门）**

```python
from sentence_transformers import SentenceTransformer
import numpy as np

_model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")

def embed(texts: list[str]) -> np.ndarray:
    return np.array(_model.encode(texts, normalize_embeddings=True))
```

**方案 B：OpenAI API**

```python
from openai import OpenAI
client = OpenAI()

def embed_openai(texts: list[str]) -> list[list[float]]:
    resp = client.embeddings.create(model="text-embedding-3-small", input=texts)
    return [item.embedding for item in resp.data]
```

### 7.5 建库脚本 ingest.py

```python
import json
import numpy as np
from pathlib import Path
from rag_utils import load_text_files, chunk_text, embed

INDEX_DIR = Path("index")
INDEX_DIR.mkdir(exist_ok=True)

def build_index():
    all_chunks = []
    for doc in load_text_files("data/docs"):
        for i, text in enumerate(chunk_text(doc["text"])):
            all_chunks.append({
                "chunk_id": f"{doc['doc_id']}:{i}",
                "doc_id": doc["doc_id"],
                "source": doc["source"],
                "text": text,
            })

    texts = [c["text"] for c in all_chunks]
    vectors = embed(texts)

    with open(INDEX_DIR / "chunks.jsonl", "w", encoding="utf-8") as f:
        for chunk in all_chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    np.save(INDEX_DIR / "vectors.npy", vectors)
    print(f"完成: {len(all_chunks)} chunks, dim={vectors.shape[1]}")

if __name__ == "__main__":
    build_index()
```

### 7.6 检索 + 问答脚本 ask.py

```python
import json
import numpy as np
from rag_utils import embed

def cosine_search(query_vec, matrix, top_k=5):
    """向量已归一化时，点积 = 余弦相似度"""
    scores = matrix @ query_vec
    idx = np.argsort(scores)[::-1][:top_k]
    return idx, scores[idx]

def load_index():
    chunks = []
    with open("index/chunks.jsonl", encoding="utf-8") as f:
        for line in f:
            chunks.append(json.loads(line))
    vectors = np.load("index/vectors.npy")
    return chunks, vectors

def ask(question: str, top_k=5):
    chunks, vectors = load_index()
    q_vec = embed([question])[0]
    idx, scores = cosine_search(q_vec, vectors, top_k)

    context = "\n\n---\n\n".join(
        f"[{chunks[i]['chunk_id']}] score={scores[j]:.3f}\n{chunks[i]['text']}"
        for j, i in enumerate(idx)
    )

    prompt = f"""你是知识库助手。仅依据以下片段回答，不足则说明「依据不足」。

问题：{question}

知识片段：
{context}
"""
    print(prompt)

if __name__ == "__main__":
    import sys
    ask(sys.argv[1] if len(sys.argv) > 1 else "云套餐如何续费？")
```

### 7.7 接上 LLM 生成

```python
# rag_llm.py
from openai import OpenAI

client = OpenAI()

SYSTEM = "你是测试知识库助手。仅依据提供的片段回答，不要编造。"

def generate_answer(question: str, context: str) -> str:
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"问题：{question}\n\n依据：\n{context}"},
        ],
        temperature=0.2,
    )
    return resp.choices[0].message.content
```

### 7.8 运行方式

```bash
python ingest.py
python ask.py "你的测试问题"
python ask.py "云套餐如何续费？" --top-k 5
```

### 7.9 从 Demo 到生产的四个升级

| 升级项 | 说明 |
|--------|------|
| **混合检索** | 向量 + 关键词，融合打分 |
| **增量更新** | manifest 校验 + `--rebuild` 全量重建 |
| **领域化 Chunk** | 测试用例按步骤数切分（≤4 步整 case，>4 步逐步切） |
| **CLI 规范** | argparse 支持 `--top-k`、`--no-llm` 等参数 |

---

## 八、Top-K 详解

在 RAG 里，**Top-K** 指：检索时只取与问题**最相似的前 K 条**文档片段（chunk）。

### 直观理解

假设知识库有 10,000 个 chunk，用户问一个问题：

1. 把问题转成向量（或与每个 chunk 算相似度）
2. 按相似度从高到低排序
3. **只取前 K 个**（比如 K=5）作为上下文，送给 LLM

```
全部 chunks:  [A, B, C, D, E, F, G, ...]  (10000个)
                    ↓ 按相似度排序
排序结果:      [C(0.92), F(0.87), A(0.81), H(0.79), B(0.75), ...]
                    ↓ Top-K=5
最终选用:      [C, F, A, H, B]  → 拼进 Prompt
```

### K 的含义

| 参数 | 含义 |
|------|------|
| **K** | 取几条（整数） |
| **Top** | 排名最靠前的 |

所以 **Top-5** = 取相似度最高的 5 条；**Top-10** = 取 10 条。

### 为什么要设 K

| K 太小（如 1~2） | K 太大（如 20~50） |
|------------------|---------------------|
| 可能漏掉关键信息 | Prompt 变长、变慢、变贵 |
| 上下文不够完整 | 噪声多，LLM 容易跑偏 |

常见取值：**3 ~ 10**，默认 **5** 比较常见。

### 代码示例

```python
def cosine_search(query_vec, matrix, top_k=5):
    scores = matrix @ query_vec          # 和所有 chunk 算相似度
    idx = np.argsort(scores)[::-1][:top_k]  # 排序后取前 top_k 个下标
    return idx, scores[idx]
```

---

## 九、Top-K 与 Top-P 的区别

两者都是「只从一部分候选里选」，但**用在不同阶段、选的对象不同**。

### 一句话对比

| | **Top-K** | **Top-P（Nucleus Sampling）** |
|---|-----------|-------------------------------|
| **主要场景** | RAG **检索**；LLM **生成**也能用 | 几乎只用于 LLM **生成** |
| **选什么** | 相似度/概率**最高的 K 个** | 累积概率达到 P 的**最小 token 集合** |
| **数量** | **固定** K 个 | **不固定**，随概率分布变化 |
| **典型参数** | `top_k=5` | `top_p=0.9` |

### Top-K：固定取前 K 名

**在 RAG 检索里（最常见）：**

从所有 chunk 里，取与问题最相似的前 **K** 条。K=5 永远取 5 条，简单、好控 Prompt 长度。

**在 LLM 生成里：**

每个 token 生成时，只从概率最高的 **K 个词**里采样。K 小 → 更保守；K 大 → 更随机。

### Top-P：按累积概率动态选一批

也叫 **Nucleus Sampling（核采样）**。

每个 token 生成时：

1. 按概率从高到低排序
2. 从高到低累加，直到累积概率 ≥ P
3. **只在这个集合里**采样

```
概率排序:  的(0.4) + 是(0.3) + 在(0.15) = 0.85 ≥ 0.9? 否
           再加 了(0.05) = 0.90 ≥ 0.9? 是
→ 候选集 = [的, 是, 在, 了]  （4 个，不是固定数量）
```

- **P 小**（如 0.5）→ 候选少，输出更稳
- **P 大**（如 0.95）→ 候选多，更有变化

### 形象对比

```
Top-K = 「永远只考虑前 5 名选手」
Top-P = 「只考虑累计得票率达到 90% 的那些选手，人数不固定」
```

### 在 RAG 流水线里各在哪

| 阶段 | 常用参数 | 作用 |
|------|----------|------|
| **检索** | `top_k=5` | 选几条知识片段 |
| **LLM 生成** | `top_p=0.9` 或 `top_k=40` | 控制回答随机性 |
| **LLM 生成** | `temperature=0.2` | 常和 Top-P 一起用，越低越稳 |

RAG 问答脚本里的 `--top-k 5`，指的是**检索**，不是 LLM 采样。

### 实际配置建议

**检索（RAG）：**

```python
results = search(question, top_k=5)
```

**LLM 生成：**

```python
# 知识库问答：要准确、少编造
temperature=0.2
top_p=0.9

# 创意写作：要多样
temperature=0.8
top_p=0.95
```

> 注意：Top-K 和 Top-P 在 LLM 里通常二选一，同时开时多数 API 以 Top-P 为准或取更严的那个。

### 记忆口诀

- **Top-K**：**K 个**，个数固定 → 检索取几条、生成限几个词
- **Top-P**：**P 比例**，个数不固定 → 主要管 LLM 输出随机性

---

## 十、测试开发工程师的学习地图

### 第 1 阶段：理解概念（1~2 天）

- [ ] 能画出 Indexing + Query 两条流水线
- [ ] 说清 Document / Chunk / Embedding / Top-K
- [ ] 理解「检索质量 > LLM 能力」（检索错了，LLM 一定错）

### 第 2 阶段：动手最小 Demo（3~5 天）

- [ ] 10 篇 md 建库
- [ ] 实现 ingest + ask 两个脚本
- [ ] 手测 20 个问题，记录命中率

### 第 3 阶段：领域化（1~2 周）

- [ ] 按测试用例结构切 chunk
- [ ] 加 metadata：case_id、module、link
- [ ] Prompt 要求引用来源

### 第 4 阶段：优化与评估（持续）

- [ ] 混合检索
- [ ] 建立评估集：50 个问题 + 标准答案
- [ ] 指标：Recall@K、答案准确率、幻觉率

### 按周练习计划

| 阶段 | 目标 | 练习 |
|------|------|------|
| **第 1 周** | 跑通 ingest + ask | 用 10 篇 md 建库，手测 20 个问题 |
| **第 2 周** | 调 chunk + 评估 | 记录「检索命中率」，调 chunk_size / overlap |
| **第 3 周** | 混合检索 | 加 BM25 或 hash sparse，对比纯向量 |
| **第 4 周** | 接 LLM + 引用 | 输出必须带 case_id / 来源链接 |
| **第 5 周** | 读现有代码 | 从 `rag_core.py` → `ask_reolink_testcase_kb.py` 顺读 |

---

## 十一、评估 RAG 好不好

| 指标 | 含义 | 怎么测 |
|------|------|--------|
| **Recall@K** | 正确 chunk 是否出现在 Top-K | 人工标注标准 chunk，看是否命中 |
| **MRR** | 正确 chunk 排第几 | 越靠前越好 |
| **答案准确率** | 最终回答对不对 | 对比标准答案 |
| **幻觉率** | 是否编造了库里没有的内容 | 人工审核 |
| **引用正确率** | case_id / 链接是否真实 | 自动校验 |

**测试开发优势：** 可以把 RAG 当成一个系统做**用例设计 + 自动化评估**。

---

## 十二、常见问题与对策

| 现象 | 可能原因 | 对策 |
|------|----------|------|
| 答非所问 | chunk 切分不合理 | 按业务结构切 |
| 检索不到 | embedding 模型不适合中文 | 换 multilingual 模型 |
| LLM 编造 | Prompt 约束弱 | 「仅依据片段」「依据不足」 |
| 同一 case 重复出现 | 去重逻辑缺失 | 按 case_id 去重 |
| 索引过期 | 源数据更新未重建 | manifest + 定时 rebuild |
| 回答太长/太短 | Prompt 或 temperature | 约束输出格式 |
| 检索到无关内容 | chunk 太大 / 太碎 | 按业务结构切 |
| 脚本慢 | 每次 query 重建 index | 模块级缓存 `RAG_INDEX` |
| Windows 乱码 | stdout 编码 | `sys.stdout.reconfigure(encoding="utf-8")` |

---

## 十三、Reolink 知识库对照

`D:\reolink_knowledge` 是一套完整 RAG 实现：

```
D:\reolink_knowledge\
├── rag_core.py              # 核心：切分、向量化、RAGIndex、hybrid_search
├── build_rag_index.py       # 离线建库入口
├── ask_reolink_testcase_kb.py  # 在线问答入口（禅道用例 KB）
├── rag_llm.py               # LLM 封装
├── cursor_rag_client.py     # 给 Cursor Agent 用的 Prompt 封装
└── data/
    ├── testcases.jsonl      # 原始知识
    └── rag/
        ├── chunks.jsonl     # 切块元数据
        ├── vectors.npy      # 向量矩阵
        └── manifest.json    # 索引元信息
```

| RAG 概念 | 项目中的实现 |
|----------|-------------|
| 原始数据 | `data/testcases.jsonl` |
| 切分 | `rag_core.py` → `case_to_chunks()` |
| 向量化 | `text_to_vector()` / embedding |
| 索引存储 | `data/rag/chunks.jsonl` + `vectors.npy` |
| 建库脚本 | `build_rag_index.py` |
| 检索 | `hybrid_search_cases()` |
| 问答 | `ask_reolink_testcase_kb.py` |
| LLM 生成 | `rag_llm.py` |

**建议学习顺序：**

1. 先理解 Indexing / Query 两阶段
2. 跑一遍：`python build_rag_index.py --rebuild`
3. 再跑：`python ask_reolink_testcase_kb.py "你的问题"`
4. 对照 `rag_core.py` 看检索和切分怎么实现

**领域化 Chunk 策略（测试用例 KB）：**

```
步骤数 ≤ 4  → 整 case 一个 chunk
步骤数 > 4  → summary chunk + 每步一个 chunk
```

这比「固定 500 字切」更适合结构化测试数据。

---

## 十四、RAG 怎么调优

RAG 调优的核心原则：**先定位瓶颈在哪一层，再针对性改**。不要一上来就换模型或调 Prompt。

### 14.1 调优前先诊断：问题出在哪？

| 现象 | 大概率问题层 | 优先调什么 |
|------|-------------|-----------|
| 搜出来的片段就不相关 | **检索 / 索引** | chunk、embedding、Top-K、混合检索 |
| 片段对了，但答案还是错/编造 | **生成 / Prompt** | 系统提示、temperature、输出格式 |
| 有时对有时错 | **评估集不足** | 建 benchmark、分场景测 |
| 特定词（case_id、套餐名）搜不到 | **检索策略** | 关键词/BM25、混合检索 |
| 回答太长、重复、啰嗦 | **生成 + 后处理** | Prompt 约束、去重、截断 |

**调试顺序（很重要）：**

```
1. 只看检索结果（不调用 LLM）→ 检索准不准？
2. 把检索结果手动拼 Prompt → LLM 能不能答对？
3. 最后才调 LLM 参数
```

`ask_reolink_testcase_kb.py` 里的 `--no-llm` 或只打印 context，就是这一步。

### 14.2 Indexing 层调优（建库）

#### Chunk 切分（影响最大）

| 问题 | 调法 |
|------|------|
| 答案被截断在边界 | 加大 **overlap**（如 50→100） |
| 检索太泛、不精准 | **缩小 chunk**，或按结构切 |
| 上下文不完整 | **放大 chunk**，或 summary + detail 双层 |
| 测试用例场景 | 按步骤切（`case_to_chunks` 的策略） |

**测试用例推荐策略：**

```
步骤 ≤ 4  → 整 case 一个 chunk
步骤 > 4  → summary chunk + 每步一个 chunk
```

#### 元数据（Metadata）

给每个 chunk 带上可过滤、可展示的信息：

```json
{
  "chunk_id": "1234:step-2",
  "case_id": 1234,
  "module_path": "云套餐/续费",
  "title": "云套餐续费后流量计算",
  "link": "https://zentao.../case/1234"
}
```

用途：

- 检索后按 `case_id` **去重**
- 按模块 **预过滤**（缩小搜索范围）
- 回答里 **引用来源**

#### Embedding 模型

| 场景 | 建议 |
|------|------|
| 中文业务文档 | 多语言模型，如 `multilingual-MiniLM`、`bge-m3` |
| 纯英文 API 文档 | `text-embedding-3-small` |
| 离线、无 API | 本地 sentence-transformers |
| 精确词匹配弱 | 加 **稀疏向量 / BM25**（混合检索） |

**换 embedding 后必须 `--rebuild` 全量重建索引。**

#### 索引更新策略

- 源数据变了 → 重建索引
- 用 `manifest.json` 记录 `source_hash`、`generated_at`
- 大库可考虑增量更新，小库直接全量重建更简单

### 14.3 Retrieval 层调优（检索）

#### Top-K

| K 值 | 效果 |
|------|------|
| 太小（1~2） | 漏信息 |
| 适中（3~8） | 多数场景够用 |
| 太大（15+） | 噪声多、Prompt 长、贵、易幻觉 |

**调法：** 固定问题集，试 K=3/5/8/10，看 Recall@K 和最终答案准确率。

#### 混合检索（Hybrid Search）

纯向量对「云套餐-仅带图」「case_id=12345」往往不如关键词。

```
最终得分 = α × 向量相似度 + (1-α) × 稀疏/BM25 得分
```

**α 调参建议：**

| α | 适用 |
|---|------|
| 0.7~0.8 | 语义问题多（「续费和购买有什么区别？」） |
| 0.4~0.6 | 专有名词、编号多（套餐名、case_id） |
| 0.5 | 不确定时的起点 |

`rag_core.py` 的 `hybrid_search_cases` 就是这条路。

#### 查询改写（Query Rewriting）

用户原问题可能太短或口语化，检索前先改写：

```
原问题: "续费后流量咋算"
改写后: "云套餐续费后 流量计算规则 剩余流量"
```

也可：

- 提取关键词（套餐类型、模块名）
- 多 query 检索后合并去重

#### 重排序（Rerank）

两阶段检索，效果往往明显提升：

```
粗检索 Top-20 → Rerank 模型精排 → 取 Top-3~5 给 LLM
```

常用 Rerank 模型：`bge-reranker`、`cohere-rerank`。

代价：多一次 API/推理，延迟和成本上升。

#### 过滤与业务规则

测试 KB 里很常见：

- 按 `module_path` 过滤
- 按 `package_type`（云套餐、流量套餐）过滤
- 排除 supplemental / legacy 数据

**先过滤再检索**，比检索完再过滤更稳。

### 14.4 Generation 层调优（生成）

#### Prompt 模板

**系统提示要点：**

```
- 仅依据提供的知识片段回答
- 依据不足时明确说「依据不足」
- 必须列出引用的 case_id / 来源
- 不要编造未出现在依据中的规则
- 先给结论，再列依据
```

Camovue / Reolink KB 的 SYSTEM_PROMPT 就是这个思路。

#### LLM 参数

| 参数 | 知识库问答推荐 | 说明 |
|------|----------------|------|
| `temperature` | **0 ~ 0.3** | 越低越稳，少编造 |
| `top_p` | **0.8 ~ 0.95** | 与 temperature 配合 |
| `max_tokens` | 按需要限制 | 避免冗长 |

#### 上下文组织

检索到的 chunk 建议统一格式：

```
---
[case_id=1234] [score=0.87] 模块: 云套餐/续费
标题: 云套餐续费后流量计算
内容: ...
---
```

好处：LLM 更容易引用，也方便 debug。

#### 降级策略

LLM 不可用时的 fallback：

1. 直接返回 Top-1 片段摘要（`synthesize_extractive_answer`）
2. 只返回检索结果列表，让人工判断

### 14.5 建立评估体系（测试开发必做）

#### 构建 Benchmark

至少 **30~50 条** 问答对：

```json
{
  "question": "免费云套餐和付费云套餐有什么区别？",
  "expected_case_ids": [1234, 5678],
  "expected_answer_points": ["权益不同", "价格不同", "流量规则不同"]
}
```

#### 核心指标

| 指标 | 含义 | 目标 |
|------|------|------|
| **Recall@K** | 正确 chunk 是否在 Top-K 里 | > 0.8 |
| **MRR** | 正确 chunk 平均排第几 | 越接近 1 越好 |
| **答案准确率** | 最终回答是否正确 | > 0.85 |
| **幻觉率** | 是否编造库里没有的内容 | < 0.05 |
| **引用准确率** | case_id 是否真实存在 | 100% |

#### 调参流程

```
固定评估集
    ↓
改一个变量（如 chunk_size 或 top_k）
    ↓
跑全量评估
    ↓
记录指标变化
    ↓
保留最优配置
```

**一次只改一个变量**，否则不知道谁起作用。

### 14.6 调优优先级（实操建议）

按投入产出比排序：

| 优先级 | 动作 | 预期收益 |
|--------|------|----------|
| ⭐⭐⭐ | 优化 chunk 策略 | 高 |
| ⭐⭐⭐ | 建评估集 + 只看检索结果 | 高（能定位问题） |
| ⭐⭐⭐ | 混合检索 | 高（中文业务场景） |
| ⭐⭐ | 优化 Prompt + 低 temperature | 中高 |
| ⭐⭐ | 换多语言 embedding | 中 |
| ⭐⭐ | Top-K / α 网格搜索 | 中 |
| ⭐ | Rerank | 中（成本更高） |
| ⭐ | 换更大 LLM | 低（检索错时无效） |

### 14.7 常见调优场景速查

| 场景 | 调优方案 |
|------|----------|
| 套餐名搜不准 | 混合检索 + 业务词典 + query 关键词提取 |
| 长用例步骤漏掉 | 按步骤切 chunk + 提高 Top-K |
| 回答编造业务规则 | 强化 Prompt + temperature=0.2 + 要求引用 |
| 同一 case 重复出现 | 按 case_id 去重 |
| 检索慢 | 缓存 index、缩小过滤范围、降维 |
| 新用例入库后搜不到 | 触发 rebuild 或增量索引 |
| 跨模块问题答不好 | 提高 Top-K + Rerank |

### 14.8 Reolink KB 调优对照

| 调优点 | 对应位置 |
|--------|----------|
| Chunk 策略 | `rag_core.py` → `case_to_chunks()` |
| 混合检索 | `hybrid_search_cases()` |
| 业务过滤 | `ask_reolink_testcase_kb.py` 里的套餐类型、模块解析 |
| Prompt | `CAMOVUE_SYSTEM_PROMPT` / 各 KB 的模板 |
| 重建索引 | `build_rag_index.py --rebuild` |
| LLM 降级 | `rag_llm.py` → `synthesize_extractive_answer` |

**建议动手练习：**

1. 准备 20 个真实测试问题 + 标准答案
2. 跑检索，记录 Recall@5
3. 改 chunk 或加混合检索，再跑一遍对比
4. 最后才调 Prompt 和 temperature

### 14.9 调优决策图

```
效果不好
    │
    ├─ 检索片段就不对？
    │       ├─ 是 → 调 chunk / embedding / Top-K / 混合检索 / 过滤
    │       └─ 否 ↓
    │
    ├─ 片段对但答案错？
    │       ├─ 是 → 调 Prompt / temperature / 上下文格式
    │       └─ 否 ↓
    │
    └─ 偶发问题？
            → 建评估集、分场景测、加 Rerank
```

---

## 附录：关键原则

1. **检索质量 > LLM 能力** — 检索错了，LLM 一定错；先调 chunk 和 embedding，再调 LLM
2. **Indexing 和 Query 分离** — 建库和问答是两个独立脚本
3. **要求引用来源** — 测试场景必须可追溯
4. **低 temperature** — 知识库问答要准确，不要创意

---

*本文档由 Cursor AI 整理，供测试开发工程师学习 RAG 知识库使用。*
