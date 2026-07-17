"""MinIO 客户端工厂。

依据 docs/04 第十四章（文件管理）与 docs/03 ERD「资产存储域 attachment 表」。

设计要点（满足验收「本地可不安装 MinIO 服务，仅 module 能 import 即可」）：

- ``get_minio_client()`` 仅在请求处理路径内被调用，构造 ``Minio`` 客户端对象
  **不会**主动建立网络连接（连接推迟到真实的 ``put_object`` / ``get_object`` /
  ``presigned_get_object`` 执行时）。``presigned_*`` 签名在本地通过 HMAC 计算，
  同样不触网。因此本模块在 import 与路由收集阶段零网络开销。
- 不调用 ``_list_buckets`` / ``bucket_exists`` 等探测方法，避免在无服务环境下
  抛连接错误。
"""

from __future__ import annotations

from app.core.config import settings


def get_minio_client():
    """惰性构造 MinIO 客户端（无网络 IO）。"""
    from minio import Minio

    return Minio(
        settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=settings.MINIO_SECURE,
    )


def ensure_bucket(client) -> str:
    """返回桶名；调用方负责在能连接 MinIO 时确保桶存在。

    本函数本身不主动探测/创建桶（避免无服务环境报错），由上传逻辑在确有
    连接时按需 ``make_bucket``。
    """
    return settings.MINIO_BUCKET


__all__ = ["get_minio_client", "ensure_bucket"]
