#!/usr/bin/env python3
import argparse
import csv
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from old_tts_concurrency_test import worker


BASE_TEXT = "这是用于早期语音合成接口并发性能测试的中文样本文本用来观察平均延迟随字长变化"


def parse_int_list(value: str) -> list[int]:
    values = []
    for item in value.split(","):
        item = item.strip()
        if item:
            number = int(item)
            if number <= 0:
                raise argparse.ArgumentTypeError("values must be > 0")
            values.append(number)
    if not values:
        raise argparse.ArgumentTypeError("empty value list")
    return values


def make_text(length: int) -> str:
    return (BASE_TEXT * ((length // len(BASE_TEXT)) + 2))[:length]


def ensure_parent(path: str) -> None:
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)


def run_case(args: argparse.Namespace, text_len: int, concurrency: int) -> dict:
    total = args.requests_per_case or concurrency
    payload = {
        "text": make_text(text_len),
        "language": args.language,
        "tts_style": str(args.tts_style),
        "speed": args.speed,
        "volume": args.volume,
        "codec": args.codec,
    }
    start_event = threading.Event()
    started_at = time.perf_counter()
    results = []

    with ThreadPoolExecutor(max_workers=concurrency, thread_name_prefix=f"old-tts-{text_len}-{concurrency}") as executor:
        futures = [
            executor.submit(worker, index, args.url, payload, args.timeout, start_event)
            for index in range(total)
        ]
        start_event.set()
        for future in as_completed(futures):
            results.append(future.result())

    wall_time_s = time.perf_counter() - started_at
    success = sum(1 for item in results if item.ok)
    failure = total - success
    avg_ms = sum(item.latency_ms for item in results) / total if total else 0

    return {
        "text_len": text_len,
        "concurrency": concurrency,
        "requests": total,
        "success": success,
        "failure": failure,
        "success_rate": round(success / total * 100, 2) if total else 0,
        "avg_s": round(avg_ms / 1000, 2),
        "wall_time_s": round(wall_time_s, 3),
        "throughput_rps": round(total / wall_time_s, 3) if wall_time_s else 0,
    }


def write_csv(path: str, rows: list[dict]) -> None:
    ensure_parent(path)
    fields = [
        "text_len",
        "concurrency",
        "requests",
        "success",
        "failure",
        "success_rate",
        "avg_s",
        "wall_time_s",
        "throughput_rps",
    ]
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(path: str, args: argparse.Namespace, rows: list[dict]) -> None:
    ensure_parent(path)
    by_case = {(row["text_len"], row["concurrency"]): row for row in rows}
    lines = [
        "# 早期 /tts avg 延迟矩阵",
        "",
        f"- 测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 目标接口: `{args.url}`",
        f"- 字长: `{','.join(map(str, args.lengths))}`",
        f"- 并发: `{','.join(map(str, args.concurrency))}`",
        f"- 请求数: 每个组合 `{args.requests_per_case or '等于并发数'}`",
        f"- 参数: `language={args.language}`, `tts_style={args.tts_style}`, `speed={args.speed}`, `volume={args.volume}`, `codec={args.codec}`",
        f"- 指标: `avg latency`，单位秒，保留两位",
        "",
        "| 字长/并发 | " + " | ".join(str(item) for item in args.concurrency) + " |",
        "| ---: | " + " | ".join("---:" for _ in args.concurrency) + " |",
    ]
    for text_len in args.lengths:
        values = []
        for concurrency in args.concurrency:
            row = by_case[(text_len, concurrency)]
            value = f"{row['avg_s']:.2f}"
            if row["failure"]:
                value += f" ({row['failure']} fail)"
            values.append(value)
        lines.append(f"| {text_len} | " + " | ".join(values) + " |")
    lines += ["", f"![avg 延迟折线图]({os.path.basename(args.png)})", ""]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def plot_png(path: str, args: argparse.Namespace, rows: list[dict]) -> None:
    ensure_parent(path)
    by_len: dict[int, list[dict]] = {}
    for row in rows:
        by_len.setdefault(row["text_len"], []).append(row)

    plt.figure(figsize=(11, 6.5))
    for text_len in args.lengths:
        items = sorted(by_len[text_len], key=lambda item: item["concurrency"])
        x = [item["concurrency"] for item in items]
        y = [item["avg_s"] for item in items]
        plt.plot(x, y, marker="o", linewidth=2, label=f"{text_len} chars")

    plt.xscale("log", base=2)
    plt.xticks(args.concurrency, [str(item) for item in args.concurrency])
    plt.xlabel("Concurrency")
    plt.ylabel("Avg latency (s)")
    plt.title("Old /tts avg latency by text length and concurrency")
    plt.grid(True, linestyle="--", alpha=0.35)
    plt.legend(title="Text length")
    plt.tight_layout()
    plt.savefig(path, dpi=160)
    plt.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Measure old /tts avg latency matrix")
    parser.add_argument("--url", default="http://127.0.0.1:10090/tts/")
    parser.add_argument("--lengths", type=parse_int_list, default=parse_int_list("10,20,30,40,50"))
    parser.add_argument("--concurrency", type=parse_int_list, default=parse_int_list("1,2,4,8,16,32,64,100"))
    parser.add_argument("--requests-per-case", type=int, default=0)
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--language", default="zh")
    parser.add_argument("--tts-style", type=int, default=0)
    parser.add_argument("--speed", default="balanced")
    parser.add_argument("--volume", default="middle")
    parser.add_argument("--codec", default="wav")
    parser.add_argument("--png", default="tmp/old_tts_avg_latency_matrix.png")
    parser.add_argument("--csv", default="tmp/old_tts_avg_latency_matrix.csv")
    parser.add_argument("--json", default="tmp/old_tts_avg_latency_matrix.json")
    parser.add_argument("--markdown", default="tmp/old_tts_avg_latency_matrix.md")
    args = parser.parse_args()

    rows = []
    for text_len in args.lengths:
        for concurrency in args.concurrency:
            row = run_case(args, text_len, concurrency)
            rows.append(row)
            print(json.dumps(row, ensure_ascii=False), flush=True)

    ensure_parent(args.json)
    with open(args.json, "w", encoding="utf-8") as f:
        json.dump(
            {
                "config": {
                    "url": args.url,
                    "lengths": args.lengths,
                    "concurrency": args.concurrency,
                    "requests_per_case": args.requests_per_case or "equal_to_concurrency",
                    "timeout": args.timeout,
                    "language": args.language,
                    "tts_style": args.tts_style,
                    "speed": args.speed,
                    "volume": args.volume,
                    "codec": args.codec,
                },
                "rows": rows,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    write_csv(args.csv, rows)
    plot_png(args.png, args, rows)
    write_markdown(args.markdown, args, rows)
    print(f"png={args.png}")
    print(f"csv={args.csv}")
    print(f"json={args.json}")
    print(f"markdown={args.markdown}")
    return 0 if all(row["failure"] == 0 for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
