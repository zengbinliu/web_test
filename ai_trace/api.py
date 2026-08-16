# -*- coding: utf-8 -*-
"""FastAPI 入口：uvicorn ai_trace.api:app --reload"""

from __future__ import annotations

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field

from .config import get_llm_status
from .pipeline import analyze_logs

app = FastAPI(
    title="AI Trace RCA",
    description="日志结构化 → 异常检测 → LLM 根因分析",
    version="0.1.0",
)


class AnalyzeRequest(BaseModel):
    log_text: str = Field(..., description="原始日志文本")


@app.get("/health")
def health():
    """依赖与 LLM 配置状态（脱敏）。"""
    return {
        "ok": True,
        "service": "ai_trace",
        "llm": get_llm_status(),
    }


@app.post("/analyze")
async def analyze(request: Request):
    """分析日志：application/json 的 log_text，或 multipart 上传日志文件。"""
    content_type = (request.headers.get("content-type") or "").lower()
    log_text = ""

    if "multipart/form-data" in content_type:
        form = await request.form()
        upload = form.get("file")
        if upload is None:
            raise HTTPException(status_code=400, detail="multipart 请使用字段 file 上传日志")
        raw = await upload.read()
        log_text = raw.decode("utf-8", errors="replace")
    else:
        try:
            payload = await request.json()
        except Exception as exc:
            raise HTTPException(status_code=400, detail="请求体必须是 JSON 或 multipart 文件") from exc
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="JSON 体必须是对象")
        log_text = str(payload.get("log_text") or "")

    if not log_text.strip():
        raise HTTPException(status_code=400, detail="请提供 log_text 或上传日志文件")

    report = analyze_logs(log_text)
    return report.to_dict()


@app.post("/analyze/upload")
async def analyze_upload(file: UploadFile = File(...)):
    """上传 .log / 文本文件进行分析。"""
    raw = await file.read()
    log_text = raw.decode("utf-8", errors="replace")
    if not log_text.strip():
        raise HTTPException(status_code=400, detail="上传文件为空")
    return analyze_logs(log_text).to_dict()
