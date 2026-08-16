# AI 日志根因分析（ai_trace）

传入原始日志，按三步流水线输出根因建议：

1. **日志结构化** → `LogEvent`
2. **异常检测**（TF-IDF + Isolation Forest，辅以 ERROR/超时等规则）
3. **根因分析**（构建事件链 → LLM JSON → 事件路径与建议；失败则启发式兜底）

## 完整 trace-id 日志的处理流程

当你传入**同一 `trace_id` / `request_id` 的完整调用链**（如样例中的 `req-1001`）时，系统按下列路径处理：

```text
完整 trace 日志
  → parser：逐行结构化，抽出 trace_id / request_id / session_id
  → 全部 LogEvent（同 ID 的 INFO/WARN/ERROR/堆栈都挂上同一 trace_id）
  → AnomalyDetector：在整批日志上做 TF-IDF + Isolation Forest + 规则检测
  → 异常点（如 ERROR、timeout）
  → build_event_chains：异常点带 trace_id 时，按 ID 聚合同一请求的全部事件
  → 格式化事件链（异常行标 [ANOMALY]）
  → LLM 输出根因 JSON；不可用或解析失败则启发式兜底（fallback=true）
```

### 各步要点

1. **结构化**  
   从 JSON 字段或正文中的 `trace_id=` / `request_id=` / `session_id=` 写入 `LogEvent.trace_id`。多行堆栈并入上一条 ERROR 的 `message`。

2. **异常检测**  
   对你传入的**全部**日志训练/检测，找出异常点；不会只保留异常行，后续建链仍需要同 ID 的正常上下文。

3. **事件链（有 trace_id 时的关键行为）**  
   只要异常点带有 `trace_id`，就**只收集该 ID 下的全部事件**，不走「前后 30 秒 / 前后 8 条」时间窗。  
   因此完整单 trace 会收齐：下单 → 库存 → 支付 → 超时 → 重试 → 失败等；同文件里其它请求（如 `job-77`、`/health`）不会进入这条链，除非它们自己也被判为异常且带有别的 ID。

4. **LLM / 兜底**  
   链上事件格式化后送入 LLM，得到 `event_path`、`root_cause`、`confidence`、`suggestions`、`evidence`。未配置 LLM 或 JSON 解析失败时，根因取链上首条 ERROR/异常摘要，并标记 `fallback=true`。

### 使用建议

| 条件 | 效果 |
|------|------|
| 每行都能抽出同一 ID | 链路完整、上下文干净 |
| 链上有 ERROR / 超时等 | 能检出异常点并触发 RCA |
| 只喂这一条 trace | 最干净；混入其它请求也会按 ID 隔离 |
| 异常行抽不出 ID | 退回时间窗 + 前后邻居，可能混进无关日志 |

样例文件：`samples/sample.log`（主链路 `request_id=req-1001`）。

## 安装

在仓库根目录或本目录：

```bash
pip install -r ai_trace/requirements.txt
```

可选：复制 `llm.env.example` 为 `llm.env` 并填写：

```env
AI_TRACE_LLM_API_KEY=sk-...
AI_TRACE_LLM_API_BASE=https://api.openai.com/v1
AI_TRACE_LLM_MODEL=gpt-4o-mini
```

也支持回退读取 `REOLINK_RAG_LLM_*` / `OPENAI_*`。未配置 LLM 时仍可跑通，结果带 `fallback=true`。

## 本地文件

在仓库根目录（保证能 `import ai_trace`）：

```bash
# Windows PowerShell
$env:PYTHONPATH="D:\web_test"
python -m ai_trace.cli --file ai_trace/samples/sample.log --out ai_trace/result.json
```

或直接传文本：

```bash
python -m ai_trace.cli --text "2026-08-16 17:49:01 [ERROR] pay: timeout request_id=r1"
```

## FastAPI

```bash
$env:PYTHONPATH="D:\web_test"
uvicorn ai_trace.api:app --reload --port 8090
```

- `GET /health`：服务与 LLM 脱敏状态
- `POST /analyze`：JSON `{"log_text":"..."}` 或 `multipart/form-data` 字段 `file`
- `POST /analyze/upload`：上传日志文件

示例：

```bash
curl -X POST http://127.0.0.1:8090/analyze ^
  -H "Content-Type: application/json" ^
  -d "{\"log_text\":\"2026-08-16 17:49:01 [ERROR] pay: timeout request_id=r1\"}"
```

## 输出字段

```json
{
  "event_path": ["INFO 下单", "WARN 库存紧张", "ERROR 支付超时"],
  "root_cause": "支付网关超时导致订单未确认",
  "confidence": 0.82,
  "suggestions": ["检查支付超时配置"],
  "evidence": ["timeout after 30s"],
  "fallback": false,
  "anomaly_count": 3,
  "event_count": 14
}
```

## 测试

```bash
$env:PYTHONPATH="D:\web_test"
python -m pytest ai_trace/tests -q
```

测试使用假 LLM，不调用真实接口。

## 模块说明

| 文件 | 职责 |
|------|------|
| `parser.py` | 文本 / JSON Lines / 堆栈续行结构化 |
| `anomaly_detector.py` | TF-IDF + Isolation Forest + 规则 |
| `root_cause.py` | 事件链、LLM 格式化、JSON 提取、兜底 |
| `llm_client.py` | OpenAI Compatible 调用 |
| `pipeline.py` | `analyze_logs` / `analyze_log_file` |
| `cli.py` / `api.py` | 本地文件与 HTTP 入口 |
