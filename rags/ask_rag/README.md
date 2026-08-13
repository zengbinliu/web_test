# 禅道测试用例本地知识库

## 来源与范围

- 浏览入口：[https://pms.reolink.com.cn/index.php?m=testcase&f=browse&productID=42&branch=all&browseType=byModule&param=20331](https://pms.reolink.com.cn/index.php?m=testcase&f=browse&productID=42&branch=all&browseType=byModule&param=20331)
- 产品 ID：`42`
- 根模块 ID：`20331`
- 根模块路径：`全量用例`
- 同步时间：`2026-07-06 18:12:57`

## 统计概览

- 用例总数：`2498`
- 实际模块数：`231`
- 输出目录：`D:\reolink_knowledge`

## 文件说明

- `README.md`：说明文件。
- `INDEX.md`：模块索引。
- `data/index.csv`：逐条用例索引。
- `data/testcases.jsonl`：完整结构化用例数据。
- `data/module_tree.json` / `data/module_map.json`：模块树快照。
- `corpus/module-*.md`：按实际模块分组的 Markdown 语料。
- `export_zentao_module_kb.py`：导出脚本。
- `import_jmx_scenarios.py`：将 JMeter JMX 接口自动化场景导入 supplemental 知识库。
- `ask_reolink_testcase_kb.py`：本地问答/检索脚本，支持关键词、自然语言问题、交互模式和按 `case_id` 直查。
- `rag_core.py` / `build_rag_index.py`：RAG 向量索引与混合检索（关键词 + TF-IDF 向量）。
- `data/rag/`：RAG 索引文件（`vectors.npy`、`chunks.jsonl`、`manifest.json`）。
- `data/supplemental_cases.json`：补充知识（接口自动化场景、站点爬取等）。
- `data/jmx_import_report.json`：JMX 导入统计报告。
- `corpus/api-automation-index.md`：接口自动化场景人类可读索引。

## 接口自动化场景导入

将 `C:\Users\Reolink\Downloads\接口自动化场景` 下的 JMX 脚本解析为 supplemental 知识（组合场景 + 单接口 + 禅道串联索引）：

```bash
python "D:\reolink_knowledge\import_jmx_scenarios.py"
python "D:\reolink_knowledge\import_jmx_scenarios.py" --merge
python "D:\reolink_knowledge\build_rag_index.py" --rebuild
```

导入后可用 `askreolink` 查询，例如：

```bash
askreolink "注册接口自动化调用了哪些API"
askreolink "paypal支付接口自动化场景"
askreolink "/v2/shop/orders 在哪些自动化场景"
```

## 本地问答 / 检索

默认已启用 **RAG 混合检索**（关键词 + 向量），并在未配置 LLM 时使用抽取式回答；配置 LLM 后会自动生成自然语言答案。

直接运行：

```bash
python "D:\reolink_knowledge\ask_reolink_testcase_kb.py" "切换套餐什么时候生效"
```

常用示例：

```bash
python "D:\reolink_knowledge\ask_reolink_testcase_kb.py" "登录提醒邮件 相同B段IP"
python "D:\reolink_knowledge\ask_reolink_testcase_kb.py" --case 4725 --full
python "D:\reolink_knowledge\ask_reolink_testcase_kb.py" "删除成员" --module "机型组"
python "D:\reolink_knowledge\ask_reolink_testcase_kb.py" --interactive
python "D:\reolink_knowledge\ask_reolink_testcase_kb.py" --stats
python "D:\reolink_knowledge\build_rag_index.py" --rebuild
python "D:\reolink_knowledge\ask_reolink_testcase_kb.py" "切换套餐" --no-rag
python "D:\reolink_knowledge\ask_reolink_testcase_kb.py" "切换套餐" --retrieve-only
```

已额外安装 Windows 启动器 `askreolink.cmd` 到 `PATH` 目录，可直接执行：

```bash
askreolink "有几种套餐类型"
askreolink "切换套餐什么时候生效"
askreolink "流量套餐能切换到合并套餐吗"
askreolink "付费合并套餐能切换到免费合并套餐吗"
askreolink "流量套餐能切换到合并套餐吗" --brief
askreolink --case 4725 --full
askreolink --rebuild-index
askreolink
```

### RAG / LLM 配置

默认使用 **Cursor Cloud Agents API**（[Bearer 认证](https://cursor.com/cn/docs/api#bearer-cloud-agents-api)），无需 OpenAI Key。

编辑 [`llm.env`](D:\reolink_knowledge\llm.env)：

```ini
CURSOR_API_KEY=crsr_...
REOLINK_RAG_LLM_PROVIDER=cursor
REOLINK_RAG_LLM_MODEL=auto
REOLINK_RAG_CURSOR_TIMEOUT=180
```

**模型池说明**：`auto` 走 First-party 模型池（与 IDE Agent 同池）；显式指定 `composer-2.5` 等 frontier 模型会走 API 池，需 Dashboard Spend Limit 保留至少 $2 可用额度。

可选模型（通过 `GET https://api.cursor.com/v1/models` 获取）：`auto`、`composer-2.5`、`claude-sonnet-5`、`gpt-5.5` 等。

若改用 OpenAI 兼容 API：

```ini
REOLINK_RAG_LLM_PROVIDER=openai
REOLINK_RAG_LLM_API_KEY=sk-...
REOLINK_RAG_LLM_API_BASE=https://api.openai.com/v1
REOLINK_RAG_LLM_MODEL=gpt-4o-mini
```

**注意**：Cursor 模式每次问答会创建无仓库 Cloud Agent 并在完成后归档，通常需 10–60 秒。

默认输出会优先给出更短的“结论 + 依据”。如果想展开完整步骤和预期，请加 `--full`。
如果只想要一句简短答案，请加 `--brief`。
如果只想关闭 RAG 回到旧版关键词检索，请加 `--no-rag`。

交互模式支持：

- 直接输入关键词或问题
- `case 4725`
- `stats` / `统计`
- `help`
- `exit` / `quit` / `退出`
