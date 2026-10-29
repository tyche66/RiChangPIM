"""产品导入预检暂存（重传产品包：preflight → commit）。

为什么落盘而不是放内存：

* 后台按 ``UVICORN_WORKERS=2`` 运行，两个 worker 各有自己的进程内存，只有共享
  同一份文件系统才能让 commit 命中任意一个 worker；
* 一个 259MB 的包已经在 preflight 上传过一次，commit 不该让用户再传一遍；
* 预检结果需要单次消费（防连点两次确认导致重复导入），文件存在天然适合做
  「改个名就表示已用掉」的原子标记。

目录结构（``PRODUCT_IMPORT_STAGING_DIR`` 下）::

    <token>/upload.bin        原始上传文件
    <token>/meta.json         文件名 / 大小 / sha256 / 归属用户 / 过期时间
    <token>/meta.consumed.json 已消费标记（meta.json 被改名成它）

这里只做文件与元数据，不碰数据库、不解析 xlsx。
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import shutil
import time
from pathlib import Path
from typing import BinaryIO

from app.core.config import settings

_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{16,80}$")
_UPLOAD_NAME = "upload.bin"
_META_NAME = "meta.json"
_CONSUMED_NAME = "meta.consumed.json"
_CHUNK = 1024 * 1024


class StagingError(Exception):
    """预检暂存失败。``code`` 与其它接口的 detail.code 口径一致。"""

    def __init__(self, code: int, message: str, *, status_code: int = 409) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def _root() -> Path:
    return Path(settings.PRODUCT_IMPORT_STAGING_DIR)


def _dir(token: str) -> Path:
    """token -> 目录。token 只允许 URL-safe 字符，杜绝 ``..`` 穿越。"""
    if not _TOKEN_RE.match(token or ""):
        raise StagingError(40401, "预检已过期或不存在，请重新选择文件", status_code=404)
    root = _root().resolve()
    target = (root / token).resolve()
    if root not in target.parents:
        raise StagingError(40401, "预检已过期或不存在，请重新选择文件", status_code=404)
    return target


def _write_json(path: Path, payload: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def _read_meta(directory: Path) -> dict:
    meta_path = directory / _META_NAME
    if not meta_path.exists():
        consumed = directory / _CONSUMED_NAME
        if consumed.exists():
            raise StagingError(40901, "这次导入已经提交过了，请重新选择文件")
        raise StagingError(40401, "预检已过期或不存在，请重新选择文件", status_code=404)
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise StagingError(40401, "预检已过期或不存在，请重新选择文件", status_code=404) from exc


def stage_upload(
    stream: BinaryIO,
    *,
    file_name: str,
    user_id: str,
    max_bytes: int,
) -> dict:
    """把上传流写进暂存目录，返回 token 与统计信息。"""
    token = secrets.token_urlsafe(24)
    directory = _root() / token
    directory.mkdir(parents=True, exist_ok=False)

    upload_path = directory / _UPLOAD_NAME
    digest = hashlib.sha256()
    size = 0
    try:
        with upload_path.open("wb") as sink:
            while True:
                chunk = stream.read(_CHUNK)
                if not chunk:
                    break
                size += len(chunk)
                if size > max_bytes:
                    raise StagingError(
                        40004,
                        f"上传 {size} 字节，超过上限 {max_bytes} 字节，请拆成多份导入",
                        status_code=400,
                    )
                digest.update(chunk)
                sink.write(chunk)
    except StagingError:
        shutil.rmtree(directory, ignore_errors=True)
        raise
    except OSError as exc:
        shutil.rmtree(directory, ignore_errors=True)
        raise StagingError(50001, "暂存上传文件失败，请重试", status_code=500) from exc

    now = time.time()
    expires_at = now + settings.PRODUCT_IMPORT_STAGING_TTL_SECONDS
    meta = {
        "token": token,
        "file_name": file_name or _UPLOAD_NAME,
        "size": size,
        "sha256": digest.hexdigest(),
        "user_id": str(user_id),
        "created_at": now,
        "expires_at": expires_at,
    }
    _write_json(directory / _META_NAME, meta)
    return meta


def load_staged(token: str, *, user_id: str) -> tuple[Path, dict]:
    """读取暂存信息并校验归属与有效期（不消费）。"""
    directory = _dir(token)
    if not directory.is_dir():
        raise StagingError(40401, "预检已过期或不存在，请重新选择文件", status_code=404)
    meta = _read_meta(directory)
    if float(meta.get("expires_at") or 0) < time.time():
        shutil.rmtree(directory, ignore_errors=True)
        raise StagingError(40902, "预检已过期，请重新选择文件")
    if str(meta.get("user_id")) != str(user_id):
        # 不暴露「存在但不属于你」：对别人一律当作不存在
        raise StagingError(40401, "预检已过期或不存在，请重新选择文件", status_code=404)
    return directory / _UPLOAD_NAME, meta


def update_staged_meta(token: str, *, user_id: str, **fields: object) -> dict:
    """更新暂存元数据（归属与有效期先校验）。预检用它登记别名冲突行。"""
    upload_path, meta = load_staged(token, user_id=user_id)
    meta.update(fields)
    _write_json(upload_path.parent / _META_NAME, meta)
    return meta


def consume_staged(token: str, *, user_id: str) -> tuple[Path, dict]:
    """取出暂存文件并标记已消费（同一 token 只能提交一次）。"""
    directory = _dir(token)
    upload_path, meta = load_staged(token, user_id=user_id)
    try:
        (directory / _META_NAME).replace(directory / _CONSUMED_NAME)
    except OSError as exc:
        raise StagingError(40901, "这次导入已经提交过了，请重新选择文件") from exc
    if not upload_path.exists():
        raise StagingError(40401, "预检已过期或不存在，请重新选择文件", status_code=404)
    return upload_path, meta


def discard_staged(token: str, *, user_id: str) -> None:
    """取消预检：删掉整份暂存。已消费或不存在时静默成功（幂等）。"""
    try:
        directory = _dir(token)
    except StagingError:
        return
    if not directory.is_dir():
        return
    try:
        meta = _read_meta(directory)
    except StagingError:
        shutil.rmtree(directory, ignore_errors=True)
        return
    if str(meta.get("user_id")) != str(user_id):
        return
    shutil.rmtree(directory, ignore_errors=True)


def cleanup_expired() -> int:
    """清理过期与已消费的暂存目录，返回删除数量。交给 cron / 启动时兜底。"""
    root = _root()
    if not root.is_dir():
        return 0
    removed = 0
    now = time.time()
    for directory in root.iterdir():
        if not directory.is_dir():
            continue
        meta_path = directory / _META_NAME
        expired = True
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                expired = float(meta.get("expires_at") or 0) < now
            except (OSError, ValueError):
                expired = True
        if expired:
            shutil.rmtree(directory, ignore_errors=True)
            removed += 1
    return removed


__all__ = [
    "StagingError",
    "cleanup_expired",
    "consume_staged",
    "discard_staged",
    "load_staged",
    "stage_upload",
    "update_staged_meta",
]
