"""覆盖前快照：把受影响产品的原值与图片绑定落成 JSON，供人工回滚。

为什么不做产品版本表：本期只解决「重传产品包」这一条路径，覆盖前的原值只需要
在误操作后能查回来。写一个独立 JSON 文件 + 一个恢复脚本，比引入产品版本表、
迁移历史数据、再改所有读取路径要小得多。

文件位置：``<PRODUCT_IMPORT_STAGING_DIR>/backups/<backup_id>.json``
恢复：``python -m app.scripts.restore_import_backup <backup_id>``
"""

from __future__ import annotations

import json
import secrets
import time
from pathlib import Path

from app.core.config import settings


def backup_root() -> Path:
    return Path(settings.PRODUCT_IMPORT_STAGING_DIR) / "backups"


def write_import_backup(records: list[dict], *, mode: str) -> str:
    """写入一份覆盖前快照，返回 ``backup_id``（同时它就是文件名）。"""
    backup_id = f"{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}-{secrets.token_hex(4)}"
    directory = backup_root()
    directory.mkdir(parents=True, exist_ok=True)
    payload = {
        "backup_id": backup_id,
        "mode": mode,
        "created_at": time.time(),
        "products": records,
    }
    path = directory / f"{backup_id}.json"
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return backup_id


def load_backup(backup_id: str) -> dict:
    path = backup_root() / f"{backup_id}.json"
    return json.loads(path.read_text(encoding="utf-8"))


__all__ = ["backup_root", "load_backup", "write_import_backup"]
