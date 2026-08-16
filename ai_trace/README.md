# AI 日志根因分析（ai_trace）

传入原始日志，按三步流水线输出根因建议：

1. **日志结构化** → `LogEvent`
2. **异常检测**（TF-IDF + Isolation Forest，辅以 ERROR/超时等规则）
3. **根因分析**（构建事件链 → LLM JSON → 事件路径与建议；失败则启发式兜底）

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
