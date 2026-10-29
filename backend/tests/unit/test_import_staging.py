"""预检暂存：单次消费、过期、归属、路径穿越（纯文件层，不碰数据库）。"""

import io
import json
import time

import pytest

from app.services import import_staging
from app.services.import_staging import (
    StagingError,
    cleanup_expired,
    consume_staged,
    discard_staged,
    load_staged,
    stage_upload,
)


@pytest.fixture(autouse=True)
def staging_dir(tmp_path, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "PRODUCT_IMPORT_STAGING_DIR", str(tmp_path / "staging"))
    monkeypatch.setattr(settings, "PRODUCT_IMPORT_STAGING_TTL_SECONDS", 7200)
    return tmp_path / "staging"


def _stage(payload: bytes = b"xlsx-bytes", *, user_id: str = "user-1", name="a.xlsx"):
    return stage_upload(
        io.BytesIO(payload), file_name=name, user_id=user_id, max_bytes=1024 * 1024
    )


def test_stage_then_load_and_consume_once(staging_dir):
    meta = _stage()
    path, loaded = load_staged(meta["token"], user_id="user-1")

    assert path.read_bytes() == b"xlsx-bytes"
    assert loaded["size"] == len(b"xlsx-bytes")
    assert len(loaded["sha256"]) == 64

    upload_path, _ = consume_staged(meta["token"], user_id="user-1")
    assert upload_path.read_bytes() == b"xlsx-bytes"

    # 第二次消费必须失败：否则连点两次确认会把同一份包写两遍
    with pytest.raises(StagingError) as exc:
        consume_staged(meta["token"], user_id="user-1")
    assert exc.value.code == 40901


def test_expired_token_is_rejected_and_removed(staging_dir, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "PRODUCT_IMPORT_STAGING_TTL_SECONDS", 0)
    meta = _stage()
    time.sleep(0.01)

    with pytest.raises(StagingError) as exc:
        load_staged(meta["token"], user_id="user-1")
    assert exc.value.code == 40902
    assert not (staging_dir / meta["token"]).exists()


def test_other_user_cannot_touch_the_token(staging_dir):
    meta = _stage(user_id="user-1")
    with pytest.raises(StagingError) as exc:
        load_staged(meta["token"], user_id="user-2")
    # 对别人一律当作不存在，不暴露「这个 token 存在但不属于你」
    assert exc.value.code == 40401


def test_path_traversal_token_is_rejected(staging_dir):
    for token in ("../../etc/passwd", "..", "a" * 8):
        with pytest.raises(StagingError) as exc:
            load_staged(token, user_id="user-1")
        assert exc.value.code == 40401


def test_discard_is_idempotent(staging_dir):
    meta = _stage()
    discard_staged(meta["token"], user_id="user-1")
    assert not (staging_dir / meta["token"]).exists()
    # 再删一次不报错
    discard_staged(meta["token"], user_id="user-1")


def test_cleanup_removes_expired_and_leftover_consumed_dirs(staging_dir):
    expired = _stage()
    meta_path = staging_dir / expired["token"] / "meta.json"
    payload = json.loads(meta_path.read_text(encoding="utf-8"))
    payload["expires_at"] = time.time() - 1
    meta_path.write_text(json.dumps(payload), encoding="utf-8")

    consumed = _stage()
    consume_staged(consumed["token"], user_id="user-1")

    fresh = _stage()

    assert cleanup_expired() == 2
    assert not (staging_dir / expired["token"]).exists()
    assert not (staging_dir / consumed["token"]).exists()
    assert (staging_dir / fresh["token"]).exists()


def test_partial_upload_is_cleaned_up_on_failure(staging_dir):
    class Boom(io.BytesIO):
        def read(self, size=-1):
            raise OSError("disk gone")

    with pytest.raises(StagingError):
        import_staging.stage_upload(
            Boom(b"x"), file_name="a.xlsx", user_id="user-1", max_bytes=1024
        )
    # 失败后不能留下半截目录
    assert list(staging_dir.iterdir()) == []
