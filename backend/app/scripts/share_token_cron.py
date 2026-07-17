#!/usr/bin/env python
"""ShareToken 过期扫描独立入口（docs/03 §5.2）。

作为 cron 任务以 ``/usr/bin/env python`` 调起；不依赖 FastAPI / 应用层定时器，
复用 ORM 模型直接操作数据库。典型 crontab（日志落在项目内的 logs/ 目录，
不写系统 /var/log，便于整体随项目目录迁移）：

    0 * * * * /path/to/venv/bin/python -m app.scripts.share_token_cron \
        >> logs/share_token_sweep.log 2>&1

如需自定义日志路径，设置环境变量 ``SHARE_SWEEP_LOG`` 覆盖。
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.services.share_token_sweeper import sweep_expired_tokens


def _project_root() -> str:
    # 指向 backend/ 项目根，使默认日志落在项目内而非系统目录。
    import app.core.config as _cfg

    return str(_cfg.PROJECT_ROOT)


# 日志默认落在项目内 logs/，可由 SHARE_SWEEP_LOG 环境变量覆盖。
LOG_FILE = os.environ.get(
    "SHARE_SWEEP_LOG",
    os.path.join(_project_root(), "logs", "share_token_sweep.log"),
)


async def _main() -> int:
    swept = await sweep_expired_tokens()
    msg = f"[share_token_sweep] swept {swept} expired token(s)"
    print(msg)
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as fh:
            fh.write(msg + "\n")
    except OSError:
        # 日志写入失败不影响扫描结果，仅退回 stdout。
        pass
    return swept


if __name__ == "__main__":
    asyncio.run(_main())
