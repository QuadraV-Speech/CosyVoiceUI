#!/usr/bin/env python3
import argparse
import json
import os
import statistics
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Optional

import requests


@dataclass
class RequestResult:
    index: int
    ok: bool
    status_code: Optional[int]
    latency_ms: float
    bytes_len: int
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


def make_payload(args: argparse.Namespace) -> dict[str, str]:
    return {
        "text": args.text,
        "language": args.language,
        "tts_style": str(args.tts_style),
        "speed": args.speed,
        "volume": args.volume,
        "output_format": args.output_format,
        "max_chars": str(args.max_chars),
    }


def worker(
    index: int,
    url: str,
    payload: dict[str, str],
    timeout: float,
    start_event: threading.Event,
    output_dir: Optional[str],
) -> RequestResult:
    request_id = f"load-{uuid.uuid4().hex[:12]}"
    session = requests.Session()
    session.trust_env = False
    start_event.wait()

    start = time.perf_counter()
    try:
        response = session.post(
            url,
            data=payload,
            headers={"X-Request-ID": request_id},
            timeout=timeout,
        )
        latency_ms = (time.perf_counter() - start) * 1000
        content = response.content or b""
        content_type = response.headers.get("content-type", "")
        ok = response.status_code == 200 and len(content) > 0

        if ok and output_dir:
            os.makedirs(output_dir, exist_ok=True)
            ext = payload.get("output_format", "mp3")
            with open(os.path.join(output_dir, f"tts_{index:04d}.{ext}"), "wb") as f:
                f.write(content)

        error = ""
        if not ok:
            error = content[:500].decode("utf-8", errors="replace")

        return RequestResult(
            index=index,
            ok=ok,
            status_code=response.status_code,
            latency_ms=latency_ms,
            bytes_len=len(content),
            content_type=content_type,
            request_id=request_id,
            error=error,
        )
    except Exception as exc:
        latency_ms = (time.perf_counter() - start) * 1000
        return RequestResult(
            index=index,
            ok=False,
            status_code=None,
            latency_ms=latency_ms,
            bytes_len=0,
            content_type="",
            request_id=request_id,
            error=repr(exc),
        )


def summarize(results: list[RequestResult], wall_time_s: float) -> dict:
    successes = [r for r in results if r.ok]
    failures = [r for r in results if not r.ok]
    latencies = [r.latency_ms for r in results]
    success_latencies = [r.latency_ms for r in successes]
    bytes_values = [r.bytes_len for r in successes]

    status_counts: dict[str, int] = {}
    error_counts: dict[str, int] = {}
    for result in results:
        key = str(result.status_code) if result.status_code is not None else "exception"
        status_counts[key] = status_counts.get(key, 0) + 1
        if not result.ok:
            error_key = result.error[:160] or key
            error_counts[error_key] = error_counts.get(error_key, 0) + 1

    return {
        "total": len(results),
        "success": len(successes),
        "failure": len(failures),
        "success_rate": round(len(successes) / len(results) * 100, 2) if results else 0,
        "wall_time_s": round(wall_time_s, 3),
        "throughput_rps": round(len(results) / wall_time_s, 3) if wall_time_s > 0 else 0,
        "success_throughput_rps": round(len(successes) / wall_time_s, 3) if wall_time_s > 0 else 0,
        "latency_ms": {
            "min": round(min(latencies), 2) if latencies else 0,
            "avg": round(statistics.mean(latencies), 2) if latencies else 0,
            "p50": round(percentile(latencies, 50), 2),
            "p90": round(percentile(latencies, 90), 2),
            "p95": round(percentile(latencies, 95), 2),
            "p99": round(percentile(latencies, 99), 2),
            "max": round(max(latencies), 2) if latencies else 0,
        },
        "success_latency_ms": {
            "avg": round(statistics.mean(success_latencies), 2) if success_latencies else 0,
            "p95": round(percentile(success_latencies, 95), 2),
            "max": round(max(success_latencies), 2) if success_latencies else 0,
        },
        "audio_bytes": {
            "min": min(bytes_values) if bytes_values else 0,
            "avg": round(statistics.mean(bytes_values), 2) if bytes_values else 0,
            "max": max(bytes_values) if bytes_values else 0,
        },
        "status_counts": status_counts,
        "error_counts": error_counts,
    }


def write_report(path: str, args: argparse.Namespace, summary: dict, results: list[RequestResult]) -> None:
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    payload = make_payload(args)

    slowest = sorted(results, key=lambda r: r.latency_ms, reverse=True)[: min(5, len(results))]
    lines = [
        "# /tts 并发测试报告",
        "",
        f"- 测试时间: {now}",
        f"- 目标接口: `{args.url}`",
        f"- 并发数: `{args.concurrency}`",
        f"- 请求总数: `{args.total}`",
        f"- 超时: `{args.timeout}s`",
        f"- 请求参数: `{json.dumps(payload, ensure_ascii=False)}`",
        "",
        "## 结果概览",
        "",
        f"- 成功/总数: `{summary['success']}/{summary['total']}`",
        f"- 成功率: `{summary['success_rate']}%`",
        f"- 总耗时: `{summary['wall_time_s']}s`",
        f"- 吞吐量: `{summary['throughput_rps']} req/s`",
        f"- 成功吞吐量: `{summary['success_throughput_rps']} req/s`",
        "",
        "## 延迟",
        "",
        "| 指标 | 毫秒 |",
        "| --- | ---: |",
    ]

    for key in ("min", "avg", "p50", "p90", "p95", "p99", "max"):
        lines.append(f"| {key} | {summary['latency_ms'][key]} |")

    lines += [
        "",
        "## 音频大小",
        "",
        f"- 最小: `{summary['audio_bytes']['min']}` bytes",
        f"- 平均: `{summary['audio_bytes']['avg']}` bytes",
        f"- 最大: `{summary['audio_bytes']['max']}` bytes",
        "",
        "## 状态码分布",
        "",
        "```json",
        json.dumps(summary["status_counts"], ensure_ascii=False, indent=2),
        "```",
    ]

    if summary["error_counts"]:
        lines += [
            "",
            "## 错误摘要",
            "",
            "```json",
            json.dumps(summary["error_counts"], ensure_ascii=False, indent=2),
            "```",
        ]

    lines += [
        "",
        "## 最慢请求",
        "",
        "| index | ok | status | latency_ms | bytes | request_id |",
        "| ---: | --- | ---: | ---: | ---: | --- |",
    ]
    for item in slowest:
        lines.append(
            f"| {item.index} | {item.ok} | {item.status_code} | "
            f"{item.latency_ms:.2f} | {item.bytes_len} | {item.request_id} |"
        )

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Concurrent load test for CosyVoiceUI /tts/")
    parser.add_argument("--url", default="http://127.0.0.1:10100/tts/")
    parser.add_argument("--total", type=int, default=20)
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--text", default="你好，这是一次语音合成并发测试。")
    parser.add_argument("--language", default="zh")
    parser.add_argument("--tts-style", type=int, default=1)
    parser.add_argument("--speed", choices=["low", "balanced", "fast"], default="balanced")
    parser.add_argument("--volume", choices=["small", "middle", "large"], default="middle")
    parser.add_argument(
        "--output-format",
        choices=["pcm", "mp3", "wav", "aac", "m4a", "opus", "ogg", "flac", "webm"],
        default="mp3",
    )
    parser.add_argument("--max-chars", type=int, default=80)
    parser.add_argument("--save-audio-dir", default="")
    parser.add_argument("--report", default="tmp/tts_concurrency_report.md")
    parser.add_argument("--json-report", default="tmp/tts_concurrency_report.json")
    args = parser.parse_args()

    if args.total <= 0:
        raise SystemExit("--total must be > 0")
    if args.concurrency <= 0:
        raise SystemExit("--concurrency must be > 0")

    concurrency = min(args.concurrency, args.total)
    payload = make_payload(args)
    start_event = threading.Event()

    started_at = time.perf_counter()
    results: list[RequestResult] = []
    with ThreadPoolExecutor(max_workers=concurrency, thread_name_prefix="tts-load") as executor:
        futures = [
            executor.submit(
                worker,
                index,
                args.url,
                payload,
                args.timeout,
                start_event,
                args.save_audio_dir or None,
            )
            for index in range(args.total)
        ]
        start_event.set()
        for future in as_completed(futures):
            results.append(future.result())

    wall_time_s = time.perf_counter() - started_at
    results.sort(key=lambda item: item.index)
    summary = summarize(results, wall_time_s)

    report_data = {
        "config": {
            "url": args.url,
            "total": args.total,
            "concurrency": concurrency,
            "timeout": args.timeout,
            "payload": payload,
        },
        "summary": summary,
        "results": [asdict(item) for item in results],
    }

    json_report_dir = os.path.dirname(args.json_report)
    if json_report_dir:
        os.makedirs(json_report_dir, exist_ok=True)
    with open(args.json_report, "w", encoding="utf-8") as f:
        json.dump(report_data, f, ensure_ascii=False, indent=2)

    write_report(args.report, args, summary, results)

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"markdown_report={args.report}")
    print(f"json_report={args.json_report}")
    return 0 if summary["failure"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
