"""产品向量索引入口（v1.9.9 起为夜间调度服务的薄封装）。

历史行为（常驻进程每分钟 reconcile + 立即处理队列）已被
``app.services.knowledge_index_scheduler`` 的夜间窗口调度取代：

- 无参数：在前台运行调度主循环（等价于 backend 内置的 lifespan 调度任务，
  仅供本地调试/特殊部署使用；单例由 Postgres advisory lock 保证）。
- ``--once``：立即执行一次 run-now 式运行后退出，便于运维手动补跑。

``--once`` 与管理端 run-now 共用同一套约束（``run_now_sync``）：
- 服务停用（enabled=false）时拒绝执行；
- 进程内 asyncio.Lock + 跨进程 Postgres advisory lock 双重互斥，多个 CLI
  进程/后台服务不可能同时运行，也不能与夜间窗口重叠；
- 产品上限固定为 RUN_NOW_HARD_CAP（200），不受任何配置项影响。
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os

from app.services.knowledge_index_scheduler import (
    SchedulerBusyError,
    SchedulerDisabledError,
    get_scheduler,
)


async def _run_forever() -> None:
    scheduler = get_scheduler()
    scheduler.start()
    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        await scheduler.stop()


async def _run_once() -> None:
    result = await get_scheduler().run_now_sync(operator="cli:once")
    print(f"run finished: {result}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--once",
        action="store_true",
        help="立即执行一次 run-now 式运行（≤200 产品，单例互斥）后退出",
    )
    args = parser.parse_args()
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    try:
        if args.once:
            asyncio.run(_run_once())
        else:
            asyncio.run(_run_forever())
    except (SchedulerBusyError, SchedulerDisabledError) as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
