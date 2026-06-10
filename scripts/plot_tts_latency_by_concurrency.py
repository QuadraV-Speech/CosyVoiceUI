#!/usr/bin/env python3
import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime
from types import SimpleNamespace

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from tts_concurrency_test import make_payload, summarize, worker
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading


DEFAULT_TEXT = "这是一个用于语音合成并发测试的五十字中文句子用来观察不同并发数量下接口延迟变化趋势结果整体是否更可靠"


def parse_levels(value: str) -> list[int]:
    levels = []
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        level = int(item)
        if level <= 0:
            raise argparse.ArgumentTypeError("concurrency levels must be > 0")
        levels.append(level)
    if not levels:
        raise argparse.ArgumentTypeError("empty concurrency levels")
    return levels


def run_level(args: argparse.Namespace, concurrency: int) -> dict:
    total = args.requests_per_level or max(args.min_requests, concurrency * args.requests_multiplier)
    payload = make_payload(args)
    start_event = threading.Event()
    started_at = time.perf_counter()
    results = []

    with ThreadPoolExecutor(max_workers=concurrency, thread_name_prefix=f"tts-c{concurrency}") as executor:
        futures = [
            executor.submit(
                worker,
                index,
                args.url,
                payload,
                args.timeout,
                start_event,
                None,
            )
            for index in range(total)
        ]
        start_event.set()
        for future in as_completed(futures):
            results.append(future.result())

    wall_time_s = time.perf_counter() - started_at
    results.sort(key=lambda item: item.index)
    summary = summarize(results, wall_time_s)
    return {
        "concurrency": concurrency,
        "total": total,
        "summary": summary,
        "results": [result.__dict__ for result in results],
    }


def ensure_parent(path: str) -> None:
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)


def write_csv(path: str, rows: list[dict]) -> None:
    ensure_parent(path)
    fields = [
        "concurrency",
        "total",
        "success",
        "failure",
        "success_rate",
        "throughput_rps",
        "avg_ms",
        "p50_ms",
        "p90_ms",
        "p95_ms",
        "p99_ms",
        "max_ms",
    ]
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(path: str, args: argparse.Namespace, rows: list[dict], image_path: str) -> None:
    ensure_parent(path)
    lines = [
        "# /tts 并发数与延迟测试报告",
        "",
        f"- 测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 目标接口: `{args.url}`",
        f"- 文本长度: `{len(args.text)}` 字",
        f"- 测试文本: `{args.text}`",
        f"- 并发档位: `{','.join(str(level) for level in args.levels)}`",
        f"- 输出格式: `{args.output_format}`",
        f"- 图表: `{image_path}`",
        "",
        "## 数据表",
        "",
        "| 并发 | 请求数 | 成功率 | 吞吐 req/s | avg ms | p50 ms | p90 ms | p95 ms | p99 ms | max ms |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        lines.append(
            f"| {row['concurrency']} | {row['total']} | {row['success_rate']}% | "
            f"{row['throughput_rps']} | {row['avg_ms']} | {row['p50_ms']} | "
            f"{row['p90_ms']} | {row['p95_ms']} | {row['p99_ms']} | {row['max_ms']} |"
        )
    lines += ["", f"![并发数与延迟折线图]({os.path.basename(image_path)})", ""]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def plot_png(path: str, rows: list[dict]) -> None:
    ensure_parent(path)
    x = [row["concurrency"] for row in rows]
    avg = [row["avg_ms"] for row in rows]
    p50 = [row["p50_ms"] for row in rows]
    p95 = [row["p95_ms"] for row in rows]

    plt.figure(figsize=(10, 6))
    plt.plot(x, avg, marker="o", linewidth=2, label="avg")
    plt.plot(x, p50, marker="o", linewidth=2, label="p50")
    plt.plot(x, p95, marker="o", linewidth=2, label="p95")
    plt.xticks(x)
    plt.xlabel("Concurrency")
    plt.ylabel("Latency (ms)")
    plt.title("/tts latency by concurrency, 50-char text")
    plt.grid(True, linestyle="--", alpha=0.35)
    plt.legend()
    plt.tight_layout()
    plt.savefig(path, dpi=160)
    plt.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Plot /tts latency by concurrency")
    parser.add_argument("--url", default="http://127.0.0.1:10100/tts/")
    parser.add_argument("--levels", type=parse_levels, default=parse_levels("1,2,4,8,16"))
    parser.add_argument("--requests-per-level", type=int, default=0)
    parser.add_argument("--requests-multiplier", type=int, default=2)
    parser.add_argument("--min-requests", type=int, default=4)
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--text", default=DEFAULT_TEXT)
    parser.add_argument("--language", default="zh")
    parser.add_argument("--tts-style", type=int, default=1)
    parser.add_argument("--speed", choices=["low", "balanced", "fast"], default="balanced")
    parser.add_argument("--volume", choices=["small", "middle", "large"], default="middle")
    parser.add_argument("--output-format", default="mp3")
    parser.add_argument("--max-chars", type=int, default=80)
    parser.add_argument("--png", default="tmp/tts_latency_by_concurrency.png")
    parser.add_argument("--csv", default="tmp/tts_latency_by_concurrency.csv")
    parser.add_argument("--json", default="tmp/tts_latency_by_concurrency.json")
    parser.add_argument("--markdown", default="tmp/tts_latency_by_concurrency.md")
    args = parser.parse_args()

    if len(args.text) != 50:
        print(f"warning: text length is {len(args.text)}, not 50", file=sys.stderr)

    level_results = []
    rows = []
    for concurrency in args.levels:
        result = run_level(args, concurrency)
        summary = result["summary"]
        latency = summary["latency_ms"]
        row = {
            "concurrency": concurrency,
            "total": result["total"],
            "success": summary["success"],
            "failure": summary["failure"],
            "success_rate": summary["success_rate"],
            "throughput_rps": summary["throughput_rps"],
            "avg_ms": latency["avg"],
            "p50_ms": latency["p50"],
            "p90_ms": latency["p90"],
            "p95_ms": latency["p95"],
            "p99_ms": latency["p99"],
            "max_ms": latency["max"],
        }
        rows.append(row)
        level_results.append(result)
        print(json.dumps(row, ensure_ascii=False))

    ensure_parent(args.json)
    with open(args.json, "w", encoding="utf-8") as f:
        json.dump(
            {
                "config": {
                    "url": args.url,
                    "levels": args.levels,
                    "text": args.text,
                    "text_length": len(args.text),
                    "output_format": args.output_format,
                    "requests_per_level": args.requests_per_level,
                    "requests_multiplier": args.requests_multiplier,
                    "min_requests": args.min_requests,
                },
                "rows": rows,
                "level_results": level_results,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    write_csv(args.csv, rows)
    plot_png(args.png, rows)
    write_markdown(args.markdown, args, rows, args.png)
    print(f"png={args.png}")
    print(f"csv={args.csv}")
    print(f"json={args.json}")
    print(f"markdown={args.markdown}")
    return 0 if all(row["failure"] == 0 for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
