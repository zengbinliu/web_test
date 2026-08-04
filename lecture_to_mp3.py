# -*- coding: utf-8 -*-
"""Convert Day1 lecture script to MP3 with 30s pause markers."""
import asyncio
import re
import sys
from pathlib import Path

import edge_tts

VOICE = "zh-CN-XiaoxiaoNeural"
RATE = "+5%"  # slightly slower for learning
CHUNK_SIZE = 2800
PAUSE_MARKER = "【停顿30秒】"
SILENCE_SECONDS = 30


def clean_for_speech(text: str) -> str:
    text = re.sub(r"^#.*$", "", text, flags=re.M)
    text = re.sub(r"!\[.*?\]\(.*?\)", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"```[\w]*\n?", "", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.M)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    text = re.sub(r"^[-*]\s+", "", text, flags=re.M)
    text = re.sub(r"^\|.*\|$", "", text, flags=re.M)
    text = re.sub(r"^---+$", "", text, flags=re.M)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_chunks(text: str, size: int = CHUNK_SIZE):
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks, buf = [], ""
    for p in paras:
        if len(buf) + len(p) + 2 <= size:
            buf = f"{buf}\n\n{p}" if buf else p
        else:
            if buf:
                chunks.append(buf)
            if len(p) <= size:
                buf = p
            else:
                for i in range(0, len(p), size):
                    chunks.append(p[i : i + size])
                buf = ""
    if buf:
        chunks.append(buf)
    return chunks


def silence_ssml(seconds: int) -> str:
    # Edge TTS break often caps around 10s; stack breaks for longer pauses.
    parts = []
    remain = seconds
    while remain > 0:
        step = min(10, remain)
        parts.append(f'<break time="{step}s"/>')
        remain -= step
    body = "".join(parts)
    return (
        '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
        'xml:lang="zh-CN">'
        f'<voice name="{VOICE}">{body}</voice></speak>'
    )


async def synth_text(text: str, out: Path):
    communicate = edge_tts.Communicate(text, VOICE, rate=RATE)
    await communicate.save(str(out))


async def synth_silence(out: Path, seconds: int = SILENCE_SECONDS):
    communicate = edge_tts.Communicate(silence_ssml(seconds), VOICE)
    await communicate.save(str(out))


async def synthesize_lecture(script: str, out_path: Path):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sections = script.split(PAUSE_MARKER)
    tmp_files = []
    part = 0

    for idx, section in enumerate(sections):
        cleaned = clean_for_speech(section)
        if cleaned:
            for chunk in split_chunks(cleaned):
                part += 1
                tmp = out_path.with_suffix(f".part{part:03d}.mp3")
                print(f"[{part}] speech {len(chunk)} chars -> {tmp.name}")
                await synth_text(chunk, tmp)
                tmp_files.append(tmp)
        if idx < len(sections) - 1:
            part += 1
            tmp = out_path.with_suffix(f".part{part:03d}.mp3")
            print(f"[{part}] silence {SILENCE_SECONDS}s -> {tmp.name}")
            await synth_silence(tmp, SILENCE_SECONDS)
            tmp_files.append(tmp)

    with open(out_path, "wb") as out:
        for tmp in tmp_files:
            out.write(tmp.read_bytes())
            tmp.unlink(missing_ok=True)
    print(f"Done: {out_path} ({out_path.stat().st_size} bytes)")


def main():
    if len(sys.argv) < 2:
        print("Usage: python lecture_to_mp3.py <script.md> [output.mp3]")
        sys.exit(1)
    src = Path(sys.argv[1])
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else src.with_suffix(".mp3")
    raw = src.read_text(encoding="utf-8")
    print(f"Source: {src.name}, chars={len(raw)}, pauses={raw.count(PAUSE_MARKER)}")
    asyncio.run(synthesize_lecture(raw, dst))


if __name__ == "__main__":
    main()
