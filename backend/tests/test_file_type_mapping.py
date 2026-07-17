"""附件 file_type 映射测试（安全整改：修复 document 与 CHECK 约束不一致）。

canonical 决策：0001_initial.py 的 CHECK 约束 `check_attachment_file_type` 仅允许
image / video / pdf / doc / other；未发现任何已交付规范要求使用 "document"。
因此以数据库约束为准：PDF -> pdf，Word -> doc。

本测试无需数据库：
- 直接从 files.py 读取 MIME 白名单映射，断言所有产出的 file_type 满足约束；
- 从 0001_initial 迁移源码解析 CHECK 约束允许集合，作为「真相来源」交叉校验，
  防止未来有人再把映射改回不合法值。
"""

import pathlib
import re

from app.api.v1.files import _ALLOWED, ALLOWED_FILE_TYPES


def _check_constraint_allowed_set():
    """从 0001_initial.py 解析 check_attachment_file_type 允许的取值集合。"""
    path = (
        pathlib.Path(__file__).resolve().parent.parent / "alembic" / "versions" / "0001_initial.py"
    )
    src = path.read_text(encoding="utf-8")
    m = re.search(r"file_type IN \(([^)]*)\)", src)
    assert m, "未能在 0001_initial 中定位 file_type CHECK 约束"
    return {v.strip().strip("'\"") for v in m.group(1).split(",")}


def test_allowed_file_types_matches_db_check_constraint():
    """files.py 的 ALLOWED_FILE_TYPES 必须与 0001 迁移 CHECK 约束完全一致。"""
    assert ALLOWED_FILE_TYPES == _check_constraint_allowed_set()


def test_every_mapped_file_type_satisfies_check_constraint():
    """每个 MIME 映射产出的 file_type 都必须落在 CHECK 约束允许集合内。"""
    allowed = _check_constraint_allowed_set()
    for content_type, (file_type, max_size) in _ALLOWED.items():
        assert file_type in allowed, (
            f"MIME {content_type} 映射到非法 file_type={file_type}（允许: {sorted(allowed)}）"
        )
        assert max_size > 0


def test_pdf_maps_to_pdf_not_document():
    assert _ALLOWED["application/pdf"][0] == "pdf"


def test_word_maps_to_doc_not_document():
    assert _ALLOWED["application/msword"][0] == "doc"
    assert (
        _ALLOWED["application/vnd.openxmlformats-officedocument.wordprocessingml.document"][0]
        == "doc"
    )


def test_no_mapping_uses_legacy_document_value():
    """回归防护：不得再出现历史上违反 CHECK 约束的 "document" 值。"""
    assert "document" not in {ft for ft, _ in _ALLOWED.values()}


def test_image_and_video_mappings_are_canonical():
    assert _ALLOWED["image/jpeg"][0] == "image"
    assert _ALLOWED["image/png"][0] == "image"
    assert _ALLOWED["image/webp"][0] == "image"
    assert _ALLOWED["video/mp4"][0] == "video"
