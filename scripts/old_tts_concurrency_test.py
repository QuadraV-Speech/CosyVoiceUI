#!/usr/bin/env python3
import argparse
import csv
import json
import os
import statistics
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime

import requests


@dataclass
class Result:
    index: int
    ok: bool
    status_code: int | None
    latency_ms: float
    bytes_len: int
    is_wav: bool
    content_type: str
    request_id: str
    error: str = ""


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * pct / 100
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    weight = rank - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def ensure_parent(path: str) -> None:
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)


def worker(index: int, url: str, payload: dict[str, str], timeout: float, start_event: threading.Event) -> Result:
    request_id = f"old-load-{uuid.uuid4().hex[:12]}"
    session = requests.Session()
    session.trust_env = False
    start_event.wait()

    start = time.perf_counter()
    try:
        response = session.post(url, data=payload, headers={"X-Request-ID": request_id}, timeout=timeout)
        latency_ms = (time.perf_counter() - start) * 1000
        content = response.content or b""
        is_wav = content.startswith(b"RIFF") and b"WAVE" in content[:16]
        ok = response.status_code == 200 and len(content) > 0 and is_wav
        error = ""
        if not ok:
            error = content[:300].decode("utf-8", errors="replace")
        return Result(
            index=index,
            ok=ok,
            status_code=response.status_code,
            latency_ms=latency_ms,
            bytes_len=len(content),
            is_wav=is_wav,
            content_type=response.headers.get("content-type", ""),
            request_id=request_id,
            error=error,
        )
    except Exception as exc:
        latency_ms = (time.perf_counter() - start) * 1000
        return Result(
            index=index,
            ok=False,
            status_code=None,
            latency_ms=latency_ms,
            bytes_len=0,
            is_wav=False,
            content_type="",
            request_id=request_id,
            error=repr(exc),
        )


def run_level(args: argparse.Namespace, concurrency: int) -> dict:
    total = args.requests_per_level or concurrency
    start_event = threading.Event()
    started_at = time.perf_counter()
    results = []
    payload = {
        "text": args.text,
        "language": args.language,
        "tts_style": str(args.tts_style),
        "speed": args.speed,
        "volume": args.volume,
        "codec": args.codec,
    }

    with ThreadPoolExecutor(max_workers=concurrency, thread_name_prefix=f"old-tts-{concurrency}") as executor:
        futures = [
            executor.submit(worker, index, args.url, payload, args.timeout, start_event)
            for index in range(total)
        ]
        start_event.set()
        for future in as_completed(futures):
            results.append(future.result())

    wall_time_s = time.perf_counter() - started_at
    latencies = [item.latency_ms for item in results]
    successes = [item for item in results if item.ok]
    failures = [item for item in results if not item.ok]
    status_counts: dict[str, int] = {}
    for item in results:
        key = str(item.status_code) if item.status_code is not None else "exception"
        status_counts[key] = status_counts.get(key, 0) + 1

    return {
        "concurrency": concurrency,
        "requests": total,
        "success": len(successes),
        "failure": len(failures),
        "success_rate": round(len(successes) / total * 100, 2),
        "wall_time_s": round(wall_time_s, 3),
        "throughput_rps": round(total / wall_time_s, 3) if wall_time_s else 0,
        "avg_ms": round(statistics.mean(latencies), 2) if latencies else 0,
        "p50_ms": round(percentile(latencies, 50), 2),
        "p95_ms": round(percentile(latencies, 95), 2),
        "max_ms": round(max(latencies), 2) if latencies else 0,
        "avg_bytes": round(statistics.mean([item.bytes_len for item in successes]), 2) if successes else 0,
        "status_counts": status_counts,
        "results": [asdict(item) for item in sorted(results, key=lambda item: item.index)],
    }


def write_reports(args: argparse.Namespace, levels: list[dict]) -> None:
    ensure_parent(args.json_report)
    with open(args.json_report, "w", encoding="utf-8") as f:
        json.dump(
            {
                "config": {
                    "url": args.url,
                    "levels": args.levels,
                    "requests_per_level": args.requests_per_level or "equal_to_concurrency",
                    "text": args.text,
                    "language": args.language,
                    "tts_style": args.tts_style,
                    "speed": args.speed,
                    "volume": args.volume,
                    "codec": args.codec,
                },
                "levels": levels,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    ensure_parent(args.csv_report)
    with open(args.csv_report, "w", encoding="utf-8", newline="") as f:
        fields = [
            "concurrency",
            "requests",
            "success",
            "failure",
            "success_rate",
            "throughput_rps",
            "avg_ms",
            "p50_ms",
            "p95_ms",
            "max_ms",
            "avg_bytes",
        ]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for level in levels:
            writer.writerow({field: level[field] for field in fields})

    ensure_parent(args.markdown_report)
    lines = [
        "# 早期 /tts 接口并发测试报告",
        "",
        f"- 测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 目标接口: `{args.url}`",
        f"- 请求参数: `text={args.text}`, `language={args.language}`, `tts_style={args.tts_style}`, `speed={args.speed}`, `volume={args.volume}`, `codec={args.codec}`",
        f"- 并发档位: `{','.join(map(str, args.levels))}`",
        f"- 每档请求数: `{args.requests_per_level or '等于并发数'}`",
        "",
        "| 并发 | 请求数 | 成功率 | 吞吐 req/s | avg ms | p50 ms | p95 ms | max ms | 平均大小 bytes |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for level in levels:
        lines.append(
            f"| {level['concurrency']} | {level['requests']} | {level['success_rate']}% | "
            f"{level['throughput_rps']} | {level['avg_ms']} | {level['p50_ms']} | "
            f"{level['p95_ms']} | {level['max_ms']} | {level['avg_bytes']} |"
        )
    lines.append("")
    with open(args.markdown_report, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def parse_levels(value: str) -> list[int]:
    levels = []
    for item in value.split(","):
        item = item.strip()
        if item:
            levels.append(int(item))
    return levels


def main() -> int:
    parser = argparse.ArgumentParser(description="Concurrency test for the old /tts/ form API")
    parser.add_argument("--url", default="http://127.0.0.1:10090/tts/")
    parser.add_argument("--levels", type=parse_levels, default=parse_levels("1,2,4,8,16,32,64,100"))
    parser.add_argument("--requests-per-level", type=int, default=0)
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--text", default="你好，我是语音助手，很高心为您服务")
    parser.add_argument("--language", default="zh")
    parser.add_argument("--tts-style", type=int, default=0)
    parser.add_argument("--speed", default="balanced")
    parser.add_argument("--volume", default="middle")
    parser.add_argument("--codec", default="wav")
    parser.add_argument("--markdown-report", default="tmp/old_tts_concurrency_report.md")
    parser.add_argument("--json-report", default="tmp/old_tts_concurrency_report.json")
    parser.add_argument("--csv-report", default="tmp/old_tts_concurrency_report.csv")
    args = parser.parse_args()

    levels = []
    for concurrency in args.levels:
        level = run_level(args, concurrency)
        levels.append(level)
        printable = {key: value for key, value in level.items() if key != "results"}
        print(json.dumps(printable, ensure_ascii=False), flush=True)

    write_reports(args, levels)
    print(f"markdown={args.markdown_report}")
    print(f"json={args.json_report}")
    print(f"csv={args.csv_report}")
    return 0 if all(level["failure"] == 0 for level in levels) else 1


if __name__ == "__main__":
    raise SystemExit(main())
