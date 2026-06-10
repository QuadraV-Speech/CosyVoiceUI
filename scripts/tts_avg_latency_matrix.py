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

from tts_concurrency_test import make_payload, summarize, worker


BASE_TEXT = "这是用于语音合成并发性能测试的中文样本文本用于观察平均延迟随字长和并发变化的趋势"


def parse_int_list(value: str) -> list[int]:
    values = []
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        number = int(item)
        if number <= 0:
            raise argparse.ArgumentTypeError("values must be > 0")
        values.append(number)
    if not values:
        raise argparse.ArgumentTypeError("empty value list")
    return values


def make_text(length: int) -> str:
    text = (BASE_TEXT * ((length // len(BASE_TEXT)) + 2))[:length]
    if len(text) != length:
        raise ValueError(f"failed to build {length}-char text")
    return text


def ensure_parent(path: str) -> None:
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)


def run_case(args: argparse.Namespace, text_len: int, concurrency: int) -> dict:
    total = args.requests_per_case or concurrency
    text = make_text(text_len)
    payload_args = argparse.Namespace(
        text=text,
        language=args.language,
        tts_style=args.tts_style,
        speed=args.speed,
        volume=args.volume,
        output_format=args.output_format,
        max_chars=args.max_chars,
    )
    payload = make_payload(payload_args)

    start_event = threading.Event()
    results = []
    started_at = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency, thread_name_prefix=f"tts-{text_len}-{concurrency}") as executor:
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
    summary = summarize(results, wall_time_s)
    latency = summary["latency_ms"]
    return {
        "text_len": text_len,
        "concurrency": concurrency,
        "requests": total,
        "success": summary["success"],
        "failure": summary["failure"],
        "success_rate": summary["success_rate"],
        "avg_s": round(latency["avg"] / 1000, 2),
        "wall_time_s": summary["wall_time_s"],
        "throughput_rps": summary["throughput_rps"],
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
    by_len = {(row["text_len"], row["concurrency"]): row for row in rows}
    lines = [
        "# /tts avg 延迟矩阵",
        "",
        f"- 测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 目标接口: `{args.url}`",
        f"- 字长: `{','.join(map(str, args.lengths))}`",
        f"- 并发: `{','.join(map(str, args.concurrency))}`",
        f"- 请求数: 每个组合 `{args.requests_per_case or '等于并发数'}`",
        f"- 指标: `avg latency`，单位秒，保留两位",
        f"- 输出格式: `{args.output_format}`",
        "",
        "| 字长/并发 | " + " | ".join(str(item) for item in args.concurrency) + " |",
        "| ---: | " + " | ".join("---:" for _ in args.concurrency) + " |",
    ]
    for text_len in args.lengths:
        values = []
        for concurrency in args.concurrency:
            row = by_len[(text_len, concurrency)]
            value = f"{row['avg_s']:.2f}"
            if row["failure"]:
                value += f" ({row['failure']} fail)"
            values.append(value)
        lines.append(f"| {text_len} | " + " | ".join(values) + " |")

    lines += [
        "",
        f"![avg 延迟折线图]({os.path.basename(args.png)})",
        "",
    ]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def plot_png(path: str, args: argparse.Namespace, rows: list[dict]) -> None:
    ensure_parent(path)
    by_len = {}
    for row in rows:
        by_len.setdefault(row["text_len"], []).append(row)

    plt.figure(figsize=(11, 6.5))
    for text_len in args.lengths:
        items = sorted(by_len[text_len], key=lambda row: row["concurrency"])
        x = [row["concurrency"] for row in items]
        y = [row["avg_s"] for row in items]
        plt.plot(x, y, marker="o", linewidth=2, label=f"{text_len} chars")

    plt.xscale("log", base=2)
    plt.xticks(args.concurrency, [str(item) for item in args.concurrency])
    plt.xlabel("Concurrency")
    plt.ylabel("Avg latency (s)")
    plt.title("/tts avg latency by text length and concurrency")
    plt.grid(True, linestyle="--", alpha=0.35)
    plt.legend(title="Text length")
    plt.tight_layout()
    plt.savefig(path, dpi=160)
    plt.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Measure /tts avg latency matrix")
    parser.add_argument("--url", default="http://127.0.0.1:10100/tts/")
    parser.add_argument("--lengths", type=parse_int_list, default=parse_int_list("10,20,30,40,50"))
    parser.add_argument("--concurrency", type=parse_int_list, default=parse_int_list("1,2,4,8,16,32,64,100"))
    parser.add_argument("--requests-per-case", type=int, default=0)
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--language", default="zh")
    parser.add_argument("--tts-style", type=int, default=1)
    parser.add_argument("--speed", choices=["low", "balanced", "fast"], default="balanced")
    parser.add_argument("--volume", choices=["small", "middle", "large"], default="middle")
    parser.add_argument("--output-format", default="mp3")
    parser.add_argument("--max-chars", type=int, default=80)
    parser.add_argument("--png", default="tmp/tts_avg_latency_matrix.png")
    parser.add_argument("--csv", default="tmp/tts_avg_latency_matrix.csv")
    parser.add_argument("--json", default="tmp/tts_avg_latency_matrix.json")
    parser.add_argument("--markdown", default="tmp/tts_avg_latency_matrix.md")
    args = parser.parse_args()

    rows = []
    for text_len in args.lengths:
        for concurrency in args.concurrency:
            row = run_case(args, text_len, concurrency)
            rows.append(row)
            print(json.dumps(row, ensure_ascii=False))

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
                    "output_format": args.output_format,
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
