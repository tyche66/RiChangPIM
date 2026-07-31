"""版本号的两条不变量，不依赖数据库，所以在任何环境都会真的跑起来。

`tests/test_version.py` 里那几条是接口级测试，需要一个可连的 Postgres；没有服务时整文件
skip。而这两条恰恰是最容易悄悄退化的：

1. **后端不许替前端报版本。** `/api/v1/version` 以前返回过 `frontend_version`，值直接抄
   `backend_version`。前端是独立构建、独立部署的（`frontend/dist` 可以比后端旧任意多个
   版本），那个字段在前后端真不同版时照样显示一致 —— 它把 `compareBuilds()` 的一致性
   比对变成了恒等式。真实前端版本由 `frontend/src/config/version.ts` 在构建期注入。

2. **兜底版本号必须是真话。** `settings.VERSION` 是 `APP_VERSION` 没注入时用的值，原来
   写死 `0.1.0`，于是所有开发环境和所有忘传构建参数的部署都对外报一个不存在的版本，比
   真实产品版本差了 8 个 MINOR。`版本控制规范和Git.md` §1 规定版本锚点是
   `frontend/package.json`，这里就按锚点校验，谁改了锚点忘了改这里，测试直接红。
"""

import json
from pathlib import Path

from app.api.v1 import version as version_module
from app.core.config import settings

REPO_ROOT = Path(__file__).resolve().parents[3]


def _package_version(relative_path: str) -> str:
    payload = json.loads((REPO_ROOT / relative_path).read_text(encoding="utf-8"))
    return payload["version"]


async def test_version_payload_never_claims_a_frontend_version():
    data = (await version_module.get_version())["data"]
    assert "frontend_version" not in data
    assert not [key for key in data if key.startswith("frontend")]
    # 这几个是后端真的知道的东西，删掉哪个都会让「版本」页少一格。
    assert {
        "app_name",
        "backend_version",
        "build_id",
        "git_commit",
        "build_time",
        "environment",
        "api_version",
    } <= data.keys()


async def test_version_payload_reports_the_effective_backend_version():
    data = (await version_module.get_version())["data"]
    assert data["backend_version"] == (settings.APP_VERSION or settings.VERSION)
    assert data["api_version"] == "v1"


def test_fallback_version_matches_the_frontend_package_anchor():
    assert settings.VERSION == _package_version("frontend/package.json")


def test_portal_version_matches_the_frontend_package_anchor():
    """门户和后台是同版发布的（生产 nginx 把两者挂在同一个域名下），不允许各报一个版本。"""
    assert _package_version("portal/package.json") == _package_version("frontend/package.json")
