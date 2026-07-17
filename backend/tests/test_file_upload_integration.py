"""附件上传真实集成测试（Task 1）。

在专用 PostgreSQL 测试库上真实覆盖 ``POST /api/v1/files/upload`` 的完整业务路径，
而非仅比对 MIME 映射与迁移源码。MinIO 由隔离的 ``FakeMinio`` 替身接管，绝不触达
生产对象存储。

覆盖：
- PDF / Word 上传：状态码、响应结构、``attachment.file_type`` 写入并真实 commit、
  满足 ``check_attachment_file_type``、无 ``IntegrityError``；
- 直接写入非法 ``file_type`` 被 PostgreSQL 真实拒绝（CHECK 约束）；
- 不支持的 MIME / 超限文件返回 422；
- MinIO 副作用隔离；
- 数据库 commit 失败时的一致性行为（对象已写、无补偿，明确记录）。
"""

from uuid import uuid4

import pytest
from _db_probe import resolve_test_database_url, to_sync_url
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError


class FakeMinio:
    """隔离的 MinIO 替身：记录写入，绝不建立真实网络连接。"""

    def __init__(self):
        self.puts = []
        self.buckets = set()
        self.presigned = []

    def make_bucket(self, name):
        self.buckets.add(name)

    def put_object(self, bucket, object_name, data, length, content_type=None):
        self.puts.append(
            {
                "bucket": bucket,
                "object_name": object_name,
                "length": length,
                "content_type": content_type,
            }
        )
        return length

    def presigned_get_object(self, bucket, object_name, **kwargs):
        self.presigned.append((bucket, object_name))
        return f"http://fake-minio/{bucket}/{object_name}"


def _sync_engine():
    return create_engine(to_sync_url(resolve_test_database_url()))


async def _login_admin(client):
    resp = await client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "admin123"}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["access_token"]


def _attachment_count(engine):
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT count(*) FROM attachment WHERE is_deleted = false")
        ).scalar()


def _latest_attachment(engine):
    with engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT id, file_type, file_name, file_url, file_size "
                "FROM attachment WHERE is_deleted = false "
                "ORDER BY create_time DESC LIMIT 1"
            )
        ).first()


@pytest.fixture
def minio(monkeypatch):
    from app.api.v1 import files as files_mod

    fake = FakeMinio()
    monkeypatch.setattr(files_mod, "get_minio_client", lambda: fake)
    return fake


@pytest.mark.anyio
async def test_upload_pdf_writes_pdf_type_and_commits(client, minio):
    token = await _login_admin(client)
    headers = {"Authorization": f"Bearer {token}"}
    content = b"%PDF-1.4 fake pdf content for integration test"
    resp = await client.post(
        "/api/v1/files/upload",
        files={"file": ("quote.pdf", content, "application/pdf")},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["code"] == 200
    data = body["data"]
    assert data["file_type"] == "pdf"

    # 真实 commit 到 PostgreSQL
    eng = _sync_engine()
    assert _attachment_count(eng) == 1
    row = _latest_attachment(eng)
    assert row is not None
    assert row.file_type == "pdf"  # 满足 check_attachment_file_type
    assert row.file_size == len(content)

    # MinIO 隔离：对象被写入替身，未触达生产存储
    assert minio.puts, "expected an object written to the isolated MinIO stub"
    assert minio.puts[0]["bucket"]


@pytest.mark.anyio
async def test_upload_word_doc_writes_doc_type_and_commits(client, minio):
    token = await _login_admin(client)
    headers = {"Authorization": f"Bearer {token}"}
    content = b"PK\x03\x04 fake docx content for integration test"
    resp = await client.post(
        "/api/v1/files/upload",
        files={
            "file": (
                "spec.docx",
                content,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["code"] == 200
    assert body["data"]["file_type"] == "doc"

    eng = _sync_engine()
    assert _attachment_count(eng) == 1
    row = _latest_attachment(eng)
    assert row.file_type == "doc"


@pytest.mark.anyio
async def test_upload_word_doc_legacy_mime_writes_doc_type(client, minio):
    token = await _login_admin(client)
    headers = {"Authorization": f"Bearer {token}"}
    content = b"\xd0\xcf\x11\xe0 fake .doc content"
    resp = await client.post(
        "/api/v1/files/upload",
        files={"file": ("legacy.doc", content, "application/msword")},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["data"]["file_type"] == "doc"


@pytest.mark.anyio
async def test_illegal_file_type_rejected_by_check_constraint(client):
    """直接向测试库写入非法 file_type，PostgreSQL 必须真实拒绝（CHECK 约束）。"""
    eng = _sync_engine()
    aid = str(uuid4())
    with pytest.raises(IntegrityError):
        with eng.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO attachment "
                    "(id, file_name, file_url, file_type, file_size, storage_type, "
                    " oss_key, create_time, update_time, is_deleted) "
                    "VALUES (:id, 'x', '/x', 'document', 1, 'minio', 'x', "
                    " now(), now(), false)"
                ),
                {"id": aid},
            )


@pytest.mark.anyio
async def test_unsupported_mime_returns_422(client, minio):
    token = await _login_admin(client)
    headers = {"Authorization": f"Bearer {token}"}
    resp = await client.post(
        "/api/v1/files/upload",
        files={"file": ("note.txt", b"plain text", "text/plain")},
        headers=headers,
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"]["code"] == 42202


@pytest.mark.anyio
async def test_oversize_file_returns_422(client, minio, monkeypatch):
    from app.api.v1 import files as files_mod

    # 把 PDF 上限临时降到 5 字节，便于在不生成 50MB 文件的情况下覆盖大小分支。
    monkeypatch.setitem(files_mod._ALLOWED, "application/pdf", ("pdf", 5))
    token = await _login_admin(client)
    headers = {"Authorization": f"Bearer {token}"}
    resp = await client.post(
        "/api/v1/files/upload",
        files={"file": ("big.pdf", b"x" * 100, "application/pdf")},
        headers=headers,
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"]["code"] == 42203


@pytest.mark.anyio
async def test_commit_failure_leaves_minio_object_and_no_compensation(client, minio, monkeypatch):
    """DB commit 失败时的真实一致性行为（Task 1 要求 7）。

    当前实现先写 MinIO 再 commit 数据库：若 commit 失败，对象已写入 MinIO 但无
    补偿/回滚（最小修复、不重新设计业务）。本测试隔离 MinIO 副作用并明确记录该行为。
    """
    from fastapi import Request

    from app.core.database import AsyncSessionLocal, get_db
    from app.main import app

    token = await _login_admin(client)
    headers = {"Authorization": f"Bearer {token}"}

    async def failing_override(request: Request):
        async with AsyncSessionLocal() as session:
            async def boom():
                raise RuntimeError("simulated DB commit failure")

            session.commit = boom
            yield session

    app.dependency_overrides[get_db] = failing_override
    try:
        status = None
        try:
            resp = await client.post(
                "/api/v1/files/upload",
                files={"file": ("c.pdf", b"%PDF commit fail", "application/pdf")},
                headers=headers,
            )
            status = resp.status_code
        except RuntimeError:
            # 模拟的 commit 失败会从被覆盖的依赖中冒泡出来；这本身就证明
            # 了“提交失败”，等价于点位 500。
            status = 500
        assert status == 500, f"expected commit failure (500), got {status}"
        # MinIO 对象已写入（无补偿）——明确记录该一致性行为。
        assert minio.puts, (
            "object was written to MinIO before the DB commit failed; "
            "no compensation is implemented (documented behavior)"
        )
        # 数据库侧不应留下 attachment 行。
        eng = _sync_engine()
        assert _attachment_count(eng) == 0
    finally:
        app.dependency_overrides.pop(get_db, None)
