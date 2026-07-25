"""AI 能力基线度量脚本（P0 阶段）。

用途：
    对 /chat（非流式）、/rag/search、/recommend 三个端点执行预置中文样本，
    记录首字节延迟（如适用）、完整延迟、HTTP 状态、回答长度、产品/来源数、
    是否 200、错误码，输出结构化 JSON 报告。

退出码：
    0 — 成功完成所有样本度量，报告已写入。
    1 — 环境错误（缺少 BASE_URL 依赖、登录失败等）。
    2 — 部分样本失败但报告仍会写入（非零以示警）。
"""

import asyncio
import json
import os
import statistics
import sys
import time
from pathlib import Path
from typing import Any

import httpx

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ENV_PATH = PROJECT_ROOT / "backend" / ".env.example"

CHAT_SAMPLES = [
    "找一张圣奥品牌的会议桌",
    "有材质是E1级板材的办公桌吗",
    "推荐适合10人会议室的桌子",
    "圣奥有没有带线盒的办公桌",
    "找一张白色烤漆的会议桌",
    "有没有适合开放式办公区的桌子",
    "圣奥的洽谈桌有哪些尺寸",
    "找一张带储物功能的办公桌",
    "适合高管办公室的会议桌推荐",
    "圣奥背柜和办公桌搭配建议",
]

RAG_SAMPLES = [
    "圣奥办公桌的安装说明",
    "会议桌的承重是多少",
    "办公桌E1级板材的环保标准",
    "圣奥产品的质保政策",
    "办公桌线盒怎么安装",
    "会议桌钢化玻璃如何清洁",
    "洽谈桌的包装尺寸",
    "办公桌脚垫如何调节",
    "圣奥背柜的层板承重",
    "产品说明书在哪里下载",
]

RECOMMEND_SAMPLES = [
    "推荐适合小型会议室的桌子",
    "找一张5000元以内的办公桌",
    "推荐带线盒功能的会议桌",
    "适合创业公司的办公桌组合",
    "推荐白色系的洽谈桌",
    "找一张1.2米的单人办公桌",
    "推荐高管办公室用的桌子",
    "适合开放式办公区的桌椅组合",
    "推荐带储物功能的办公桌",
    "找一张适合培训室的长桌",
]

SAMPLES = {
    "chat": CHAT_SAMPLES,
    "rag/search": RAG_SAMPLES,
    "recommend": RECOMMEND_SAMPLES,
}


def _load_env_defaults() -> dict[str, str]:
    defaults: dict[str, str] = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            defaults[key.strip()] = value.strip()
    return defaults


async def _login(client: httpx.AsyncClient, base_url: str, username: str, password: str) -> str:
    resp = await client.post(
        f"{base_url}/api/v1/auth/login",
        data={"username": username, "password": password},
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get("access_token", data.get("data", {}).get("access_token", ""))


async def _measure_chat(
    client: httpx.AsyncClient, base_url: str, token: str, query: str, runs: int
) -> dict[str, Any]:
    results = []
    for _ in range(runs):
        start = time.perf_counter()
        try:
            resp = await client.post(
                f"{base_url}/api/v1/ai/chat",
                headers={"Authorization": f"Bearer {token}"},
                json={"message": query, "stream": False, "history": []},
            )
            latency_ms = int((time.perf_counter() - start) * 1000)
            results.append(
                {
                    "latency_ms": latency_ms,
                    "http_status": resp.status_code,
                    "answer_length": len(resp.json().get("data", {}).get("answer", ""))
                    if resp.status_code == 200
                    else 0,
                    "sources_count": len(resp.json().get("data", {}).get("sources", []))
                    if resp.status_code == 200
                    else 0,
                    "is_200": resp.status_code == 200,
                    "error_code": resp.json().get("code") or resp.json().get("detail", {}).get("code", 0)
                    if resp.status_code != 200
                    else 0,
                }
            )
        except Exception as exc:
            latency_ms = int((time.perf_counter() - start) * 1000)
            results.append(
                {
                    "latency_ms": latency_ms,
                    "http_status": 0,
                    "answer_length": 0,
                    "sources_count": 0,
                    "is_200": False,
                    "error_code": str(exc),
                }
            )
    return {"endpoint": "chat", "query": query, "runs": results}


async def _measure_rag(
    client: httpx.AsyncClient, base_url: str, token: str, query: str, runs: int
) -> dict[str, Any]:
    results = []
    for _ in range(runs):
        start = time.perf_counter()
        try:
            resp = await client.post(
                f"{base_url}/api/v1/ai/rag/search",
                headers={"Authorization": f"Bearer {token}"},
                json={"query": query},
            )
            latency_ms = int((time.perf_counter() - start) * 1000)
            body = resp.json()
            data = body.get("data", {})
            results.append(
                {
                    "latency_ms": latency_ms,
                    "http_status": resp.status_code,
                    "answer_length": 0,
                    "sources_count": len(data.get("results", [])) if resp.status_code == 200 else 0,
                    "is_200": resp.status_code == 200,
                    "error_code": body.get("code") or body.get("detail", {}).get("code", 0)
                    if resp.status_code != 200
                    else 0,
                }
            )
        except Exception as exc:
            latency_ms = int((time.perf_counter() - start) * 1000)
            results.append(
                {
                    "latency_ms": latency_ms,
                    "http_status": 0,
                    "answer_length": 0,
                    "sources_count": 0,
                    "is_200": False,
                    "error_code": str(exc),
                }
            )
    return {"endpoint": "rag/search", "query": query, "runs": results}


async def _measure_recommend(
    client: httpx.AsyncClient, base_url: str, token: str, query: str, runs: int
) -> dict[str, Any]:
    results = []
    for _ in range(runs):
        start = time.perf_counter()
        try:
            resp = await client.post(
                f"{base_url}/api/v1/ai/recommend",
                headers={"Authorization": f"Bearer {token}"},
                json={"requirement": query, "limit": 10},
            )
            latency_ms = int((time.perf_counter() - start) * 1000)
            body = resp.json()
            data = body.get("data", {})
            results.append(
                {
                    "latency_ms": latency_ms,
                    "http_status": resp.status_code,
                    "answer_length": len(data.get("rationale", "")) if resp.status_code == 200 else 0,
                    "sources_count": len(data.get("products", [])) if resp.status_code == 200 else 0,
                    "is_200": resp.status_code == 200,
                    "error_code": body.get("code") or body.get("detail", {}).get("code", 0)
                    if resp.status_code != 200
                    else 0,
                }
            )
        except Exception as exc:
            latency_ms = int((time.perf_counter() - start) * 1000)
            results.append(
                {
                    "latency_ms": latency_ms,
                    "http_status": 0,
                    "answer_length": 0,
                    "sources_count": 0,
                    "is_200": False,
                    "error_code": str(exc),
                }
            )
    return {"endpoint": "recommend", "query": query, "runs": results}


MEASURERS = {
    "chat": _measure_chat,
    "rag/search": _measure_rag,
    "recommend": _measure_recommend,
}


def _compute_summary(samples: list[dict[str, Any]]) -> dict[str, Any]:
    all_latencies: list[int] = []
    total_runs = 0
    errors = 0
    for sample in samples:
        for run in sample["runs"]:
            if run["http_status"] > 0:
                all_latencies.append(run["latency_ms"])
            total_runs += 1
            if not run["is_200"]:
                errors += 1

    sorted_lat = sorted(all_latencies)
    p50 = statistics.median(sorted_lat) if sorted_lat else 0
    p95 = sorted_lat[int(len(sorted_lat) * 0.95)] if len(sorted_lat) >= 20 else (sorted_lat[-1] if sorted_lat else 0)
    p99 = sorted_lat[int(len(sorted_lat) * 0.99)] if len(sorted_lat) >= 100 else (sorted_lat[-1] if sorted_lat else 0)

    return {
        "p50_latency_ms": round(p50, 2),
        "p95_latency_ms": round(p95, 2),
        "p99_latency_ms": round(p99, 2),
        "error_rate": round(errors / total_runs, 4) if total_runs else 0,
        "total_samples": len(samples),
        "total_runs": total_runs,
    }


async def _main() -> int:
    env_defaults = _load_env_defaults()
    base_url = os.environ.get("BASE_URL", "http://localhost:8000")
    username = os.environ.get("ADMIN_USERNAME", env_defaults.get("ADMIN_USERNAME", "admin"))
    password = os.environ.get("ADMIN_PASSWORD", env_defaults.get("ADMIN_PASSWORD", "replace_with_a_strong_admin_password"))
    ai_adapter = os.environ.get("AI_ADAPTER", env_defaults.get("AI_ADAPTER", "none"))

    report_path = PROJECT_ROOT / "eval" / "p0" / "baseline-report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)

    timeout = httpx.Timeout(float(os.environ.get("AI_TIMEOUT", "30")))
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            token = await _login(client, base_url, username, password)
        except Exception as exc:
            print(f"登录失败: {exc}", file=sys.stderr)
            return 1

        all_samples: list[dict[str, Any]] = []
        exit_code = 0

        for endpoint, queries in SAMPLES.items():
            measurer = MEASURERS[endpoint]
            for query in queries:
                sample = await measurer(client, base_url, token, query, runs=3)
                all_samples.append(sample)

        summary = _compute_summary(all_samples)

        if ai_adapter == "none" or not ai_adapter:
            summary["adapter_note"] = "未配置模型，仅记录请求结构基线，不计效果指标"

        report = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "base_url": base_url,
            "adapter": ai_adapter,
            "samples": all_samples,
            "summary": summary,
        }

        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"报告已写入: {report_path}")
        print(f"总计 {len(all_samples)} 个样本, {summary['total_runs']} 次运行, 错误率 {summary['error_rate']:.2%}")

        if summary["error_rate"] > 0:
            exit_code = 2

    return exit_code


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
