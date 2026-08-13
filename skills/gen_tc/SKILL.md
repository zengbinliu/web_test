---
name: gen_tc
description: >-
  从需求文档生成 Reolink 测试用例并写入 Excel。结合 askreolink RAG 知识库补充业务规则与历史用例模式。
  适用于：需求文档生成测试用例、PRD 转测试点/用例、gen_tc、需求转 Excel 用例、仅需求文档无 XMind 的用例设计。
---

# 需求文档 → Excel 测试用例（gen_tc）

将**需求文档**转化为符合团队规范的测试用例，**输出为 Excel（.xlsx）**。业务背景与术语对齐 **askreolink** RAG 知识库。

**团队规范基准**：`D:/web_1151/02流程规范/测试用例编写规范.md`（字段、步骤/预期写法、优先级、颗粒度）。

**脚本根目录**（Windows）：`C:\Users\Reolink\.cursor\skills\gen_tc\scripts\`

## 快速决策

```
需求文档（PDF/DOCX/MD/TXT）
    ↓ parse_prd.py → 结构化摘要（模块/规则/边界/待确认）
askreolink RAG（MCP 优先 → Shell fallback，至少 4 轮）
    ↓ 历史用例、业务规则、缺陷线索、API 线索
测试点覆盖矩阵（需求条目 → 测试点 → 设计方法 → 优先级）
    ↓ 一个测试点 = 一条用例
编写 JSON 用例 → validate_cases.py 校验
    ↓
write_testcases_excel.py → .xlsx
    ↓
交付：.xlsx + cases.json + coverage.md + RAG 引用摘要
```

## 必须先读

| 资源 | 用途 |
|------|------|
| [reference.md](reference.md) | Excel 列、JSON/覆盖矩阵结构、RAG 查询模板 |
| [examples.md](examples.md) | 完整工作流示例 |
| `02流程规范/测试用例编写规范.md` | 字段必填项、优先级、命名 |

**禁止**在技能、脚本或交付物中写入账号、密码、Cookie、密钥。

## 标准工作流（顺序执行）

```
- [ ] 1. parse_prd.py 解析需求文档
- [ ] 2. askreolink RAG（至少 4 轮，可并行）
- [ ] 3. 输出测试点覆盖矩阵 coverage.md
- [ ] 4. 编写 cases.json 用例
- [ ] 5. validate_cases.py 校验 → 修复 ERROR
- [ ] 6. write_testcases_excel.py 写入 Excel
- [ ] 7. 交付说明
```

### 1. 接收输入并解析需求文档

**输入（至少一项）**：

- 用户提供的**需求文档路径**或粘贴的全文
- 可选：`所属项目`、`版本标签`（如 `【Cloud 3.2】`）、输出路径、模块前缀

**统一解析（首选）**：

```bash
python C:\Users\Reolink\.cursor\skills\gen_tc\scripts\parse_prd.py ^
  --input <需求文档路径> ^
  --output <输出目录>\prd_parsed.json
```

| 格式 | 脚本支持 | 备选 |
|------|----------|------|
| `.md` / `.txt` | ✅ | Read 工具直接读 |
| `.docx` | ✅（需 `python-docx`） | pandoc `-t plain` |
| `.pdf` | ✅（需 `pdfplumber` 或 `pymupdf`） | 乱码时在交付说明标注，以可拷贝片段 + RAG 补全 |

解析后基于 `structure` 输出**需求摘要**：`modules`、`rules`、`boundaries`、`exceptions`、`open_questions`。`parse_warnings` 非空时须在交付说明中说明。

用户仅粘贴全文、无文件时：Agent 手工整理同等结构的摘要，跳过 `parse_prd.py`。

### 2. askreolink RAG 检索（强制，至少 4 轮）

**优先 MCP**（`user-flask-mcp-local` → `askreolink`）。

MCP 连接失败时：先尝试 `mcp_auth`（空参数）重连；仍失败则 **Shell fallback**，并在交付说明记录所用路径。

| 轮次 | 目的 | 示例 |
|------|------|------|
| 1 | 模块主流程 / 历史用例 | `"<模块> 主流程 购买 订阅"` |
| 2 | 业务规则 / 计算 / 状态机 | `"<术语> 规则 边界"` |
| 3 | 历史缺陷 / 易错点 | `"<模块> 缺陷 边界 案例"` |
| 4 | 接口 / API（若涉及支付、订单、订阅） | `"API /v2/cloud checkout"` |

多模块需求时，**各模块查询可并行**执行。

| 场景 | 调用 |
|------|------|
| MCP 完整检索 | `askreolink(query="<模块> <功能> 测试", top=8, full=true)` |
| 限定 Cloud/官网/ERP | `askreolink(query="...", module="cloud", top=5)` |
| Shell 仅检索片段 | `python D:/reolink_knowledge/ask_reolink_testcase_kb.py "<关键词>" --retrieve-only --top 8` |

**交叉验证**：需求名词、状态机、计算公式 → 与 RAG 对齐；冲突处以需求文档为准，记入备注或交付说明。

用户消息以 `askreolink` 开头时：**先 MCP**，失败再 Shell。

### 3. 输出测试点覆盖矩阵（强制中间产物）

展开完整用例前，先产出 `coverage.md`（或 `coverage.json`），格式见 [reference.md — 覆盖矩阵](reference.md#覆盖矩阵)。

每条需求条目至少映射一个测试点；`open_questions` 中无法设计的项单独列出「待产品确认」，**不强行编造用例**。

矩阵自检：

- 每个测试点只验证一件事
- 标注设计方法（等价类 / 边界值 / 场景法 / 判定表 / 错误推测）
- 标注优先级草案

### 4. 生成测试点并编写 cases.json

结合**需求摘要 + RAG + 覆盖矩阵**编写用例 JSON（结构见 [reference.md — JSON 结构](reference.md#json-结构)）。

原则：

- **一个测试点一条用例**
- **等价类**、**边界值**、**场景法**（正向 + 异常 + 边界）
- 步骤 **建议 ≤7 步**（§3.1 颗粒度）；**硬上限 10 步**（§4.1），超过须拆分
- 含「或」且需分别验证的场景**拆开编写**
- 术语与需求/RAG **一致**，不自造名词、不缩写
- RAG 命中 API 路径时，用例类型标「接口测试」，步骤写清接口与关键字段

**用例标题**：

```
【<版本标签>】<一级模块>-<二级模块>-<三级模块>，<单一测试点简述>
```

- 用户未给版本标签时可省略 `【…】`
- 标题体现测试目的（动词：验证 / 检查）

**优先级**：P1 核心主流程；P2 重要功能；P3 一般/异常；P4 边缘展示。小模块 P1 **不超过 5 条**。

**步骤与预期**：

- 条数一致、逐步一一对应
- 步骤写**页面路径 + 操作**；预期写**可验证结果**（字段、数值、文案关键词、中英文按钮名）
- 编号 **`1）` `2）`**，**禁止** `1、`
- 预期禁止模糊语：「文案正确」「页面正常」；须列出关键词或规则/公式
- 前台与后台结果**分开描述**（同格多行时标「前台：」「后台：」）

**中间产物路径**（与 Excel 同目录）：

- `<需求文件名>_cases.json`
- `<需求文件名>_coverage.md`

### 5. 校验用例（写入 Excel 前）

```bash
python C:\Users\Reolink\.cursor\skills\gen_tc\scripts\validate_cases.py ^
  --input <cases.json>
```

- **ERROR**：必须修复后再写 Excel（步骤/预期数量不等、`1、` 编号、步骤 >10）
- **WARNING**：模糊预期、步骤 >7、标题疑似多点、模块 P1 超标 → 优先修复；用户催交付时可说明后 `--no-validate` 跳过

`write_testcases_excel.py` **默认先校验**；加 `--strict` 时 WARNING 也阻断写入。

### 6. 写入 Excel（强制交付物）

```bash
python C:\Users\Reolink\.cursor\skills\gen_tc\scripts\write_testcases_excel.py ^
  --input <cases.json> ^
  --output <输出路径>.xlsx
```

**默认输出路径**（用户未指定时）：

- 与需求文档同目录：`<需求文件名>_测试用例_<YYYYMMDD>.xlsx`
- 或工作区：`D:/web_1151/05测试数据与脚本/测试用例/<项目>_<YYYYMMDD>.xlsx`

写入后抽查：表头、列宽、步骤格式、必填列无空值。

**不要**只输出 Markdown 表格而不生成 xlsx；Excel 是 gen_tc 的**唯一正式交付格式**。

### 7. 交付说明

向用户汇报时需包含：

- 输出 Excel **完整路径**及同目录 `cases.json`、`coverage.md`
- 用例总数、P1/P2/P3/P4 分布
- 需求覆盖：已覆盖功能点 / `open_questions` 待确认项
- RAG 查询关键词摘要（含 MCP/Shell 使用路径）
- `parse_warnings` 或 PDF 解析不完整说明

## 交付物检查清单

- [ ] 已运行 `parse_prd.py` 或等价手工摘要；解析问题已说明
- [ ] RAG 至少 4 轮；关键业务点有检索依据
- [ ] 已产出 `coverage.md`；每个测试点对应一条用例
- [ ] `validate_cases.py` 无 ERROR（或已说明例外）
- [ ] 标题、前置条件、步骤、预期、优先级均已填写
- [ ] 步骤数 = 预期数；步骤用 `1）`；预期具体可验证
- [ ] 已生成 `.xlsx` 且路径已告知用户
- [ ] 未写入密钥或账号信息

## 与 xmind-prd-zentao-testcase 的分工

| 输入 | 使用技能 |
|------|----------|
| XMind + 需求文档 → 禅道 | `xmind-prd-zentao-testcase` |
| **仅需求文档 → Excel** | **`gen_tc`（本技能）** |
| Excel/禅道用例 → 自动化 | `zentao-ui-automation` |

若用户后续要导入禅道，Excel 列与团队规范已对齐，可按禅道导入模板微调列名。

## 扩展阅读

- [reference.md](reference.md) — Excel 列、JSON/覆盖矩阵、脚本与 RAG 清单
- [examples.md](examples.md) — 端到端示例
- [samples/auto_renew_cases.sample.json](samples/auto_renew_cases.sample.json) — 完整 JSON 样例
