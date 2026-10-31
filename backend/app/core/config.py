from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# 项目根目录（backend/），不依赖启动时的当前工作目录，保证从任意目录
# 以 `python -m app...` 或容器/docker compose 启动时都能定位 .env。
# 解析链：app/core/config.py -> app/core -> app -> backend
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ENV_FILE = PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    # env_file 相对项目根解析；真实环境变量（Docker/K8s/进程注入）优先级最高，
    # 便于服务器部署时仅通过环境变量配置，无需 .env 文件。
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )
    APP_NAME: str = "AI-PIM"
    DEBUG: bool = False
    # 产品版本基线。`版本控制规范和Git.md` §1 规定版本号锚点是
    # `frontend/package.json` 的 version，这里必须跟着一起改（发版清单见
    # `CHANGELOG.md` 顶部的「改版本号要动哪几处」）。
    #
    # 这个值是 APP_VERSION 没被注入时的兜底：原来写死 "0.1.0"，于是任何忘记传
    # 构建参数的部署（以及全部开发环境）都会在 /api/v1/version、/health、
    # OpenAPI 文档里报 0.1.0，和真实产品版本差了 8 个 MINOR。兜底值必须是真话。
    VERSION: str = "1.9.8"
    APP_VERSION: str | None = None
    BUILD_ID: str = "dev-local"
    GIT_COMMIT: str = "unknown"
    BUILD_TIME: str = "unknown"
    APP_ENV: str = "development"
    ENABLE_API_DOCS: bool = False
    CORS_ALLOW_ORIGINS: str = ""
    METRICS_TOKEN: str | None = None
    HEALTH_READY_CACHE_SECONDS: float = 5.0

    DATABASE_URL: str
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 10
    REDIS_URL: str

    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    LOGIN_MAX_FAILURES: int = 5
    LOGIN_LOCKOUT_SECONDS: int = 900
    SHARE_MAX_FAILURES: int = 5
    SHARE_LOCKOUT_SECONDS: int = 900
    SHARE_RATE_LIMIT: int = 30
    SHARE_RATE_WINDOW: int = 60

    MINIO_ENDPOINT: str
    MINIO_ACCESS_KEY: str
    MINIO_SECRET_KEY: str
    MINIO_BUCKET: str = "ai-pim"
    MINIO_SECURE: bool = False

    GOTENBERG_URL: str = "http://gotenberg:3000"

    OCR_ADAPTER: str = "none"
    OCR_API_URL: str = "http://ocr:8080"
    OCR_TIMEOUT: float = 300.0

    AI_ADAPTER: str | None = None
    AI_API_URL: str | None = None
    AI_API_KEY: str | None = None
    AI_API_KEY_FILE: str | None = None

    AI_CHAT_MODEL: str = "gpt-4o-mini"
    # 视觉标注模型（多模态）。留空表示不启用视觉标注，不回落 chat_model。
    AI_VISION_MODEL: str | None = None
    AI_EMBEDDING_MODEL: str = "nvidia/nemotron-3-embed-1b:free"
    AI_EMBEDDING_VERSION: str | None = None
    AI_EMBEDDING_CACHE_ENABLED: bool = False
    AI_EMBEDDING_CACHE_TTL_SECONDS: int = 3600
    AI_EMBEDDING_CACHE_MAX_ITEMS: int = 10000
    AI_EMBEDDING_DIM: int = 2048
    AI_TIMEOUT: float = 30.0
    AI_EMBEDDING_API_KEY: str | None = None
    AI_EMBEDDING_API_URL: str | None = None
    AI_TOOL_PLANNING_TIMEOUT: float = 8.0
    KNOWLEDGE_GATEWAY_ENABLED: bool = True
    AI_PENDING_ACTIONS_ENABLED: bool = True
    AI_PROCUREMENT_ENABLED: bool = True
    AI_RAG_TOP_K: int = 8
    AI_RAG_MIN_SCORE: float = 0.65
    AI_RAG_CHUNK_SIZE: int = 600
    AI_RAG_CHUNK_OVERLAP: int = 80
    KNOWLEDGE_JOB_POLL_INTERVAL_SECONDS: float = 2.0
    KNOWLEDGE_JOB_BATCH_SIZE: int = 10
    KNOWLEDGE_JOB_MAX_ATTEMPTS: int = 3
    KNOWLEDGE_JOB_RETRY_DELAY_SECONDS: int = 60
    AI_QUOTA_CHECK_ENABLED: bool = False
    AI_QUOTA_CHECKER_BACKEND: str = "noop"
    AI_LIMIT_TPS: int | None = None
    AI_LIMIT_CONCURRENT_STREAMS: int | None = None
    AI_LIMIT_USER_PER_MIN: int | None = None
    AI_LIMIT_USER_PER_DAY: int | None = None
    AI_LIMIT_USER_DAILY_TOKENS: int | None = None
    AI_LIMIT_USER_DAILY_COST_USD: float | None = None
    AI_LIMIT_SYSTEM_DAILY_COST_USD: float | None = None
    AI_BUDGET_NOTIFY_RATIO: float = 0.8
    AI_BUDGET_DISABLE_RATIO: float = 1.0
    AI_ESTIMATED_PRICE_TABLE_PATH: str | None = None
    AI_PRICING_BACKEND: str | None = None

    # 内容域独立 AI 配置。内容服务只使用 chat，不使用该适配器做 embeddings。
    CONTENT_AI_API_URL: str = "https://api.hcnsec.cn/v1"
    CONTENT_AI_API_KEY: str | None = None
    CONTENT_AI_API_KEY_FILE: str | None = None
    CONTENT_AI_CHAT_MODEL: str = "step-5-preview"
    CONTENT_AI_CHAT_MODELS: str = "step-5-preview,sensenova-6.8-flash-lite"
    CONTENT_AI_TIMEOUT: float = 180.0
    CONTENT_AI_ROUTE_TIMEOUT: float = 3.0
    CONTENT_AI_MAX_RETRIES: int = 0

    SHARE_IMAGE_URL_EXPIRE_HOURS: int = 24

    # 批量导入产品（POST /api/v1/products/import）。带图导入的上传体积比纯表格大
    # 两个数量级，所以每一项都要能按部署环境调，而不是写死在代码里。
    #
    # 上限是照真实供应商样本定的：圣奥那份「4255 行 + 4242 张图」的包，压缩后 259 MB、
    # 解压后 394 MB。原来的 200MB / 2000 行会把它直接挡在门外，而拆成三份导入正是
    # 「批量」想省掉的那份工。改这一项必须同时改 nginx 的 client_max_body_size
    # （docker/nginx/conf.d/default.conf 的 location /api/v1/products/import），
    # 否则用户在 nginx 那层就吃 413，压根到不了这个检查。
    PRODUCT_IMPORT_MAX_FILE_BYTES: int = 512 * 1024 * 1024
    PRODUCT_IMPORT_MAX_ROWS: int = 5000
    PRODUCT_IMPORT_MAX_IMAGE_BYTES: int = 20 * 1024 * 1024
    # 每行的图片上限跟 api/v1/products.py 的 MAX_PRODUCT_IMAGES /
    # MAX_PRODUCT_SCENE_IMAGES 对齐；端点会再取两者的小值，配大了也不会越过接口上限。
    PRODUCT_IMPORT_MAX_IMAGES_PER_ROW: int = 10
    PRODUCT_IMPORT_MAX_SCENES_PER_ROW: int = 30
    # 表格里写图片直链（http/https）时，服务端要替用户去 GET —— 那就是 SSRF 的入口。
    # 校验（只放公网地址、逐跳复查重定向）在 services/product_import_media.guard_url，
    # 但 DNS rebinding 仍有残留风险，所以默认关闭，只在来源可信的部署上手动打开。
    PRODUCT_IMPORT_ALLOW_URL_FETCH: bool = False
    PRODUCT_IMPORT_URL_TIMEOUT: float = 10.0

    # 预检暂存（重传产品包：先 preflight 再 commit）。
    # 为什么落盘而不是内存：后台是 UVICORN_WORKERS=2，两个 worker 共享同一份文件
    # 系统但各有自己的进程内存，暂存到共享目录才能让 commit 命中任意 worker；
    # 也避免 259MB 的包让用户为了「确认一次」再传一遍。
    PRODUCT_IMPORT_STAGING_DIR: str = "/tmp/pim_import_staging"
    PRODUCT_IMPORT_STAGING_TTL_SECONDS: int = 7200
    # 预检回显的冲突明细条数上限（超出只给计数 + truncated 标记）。
    PRODUCT_IMPORT_CONFLICT_LIMIT: int = 200

    # 提醒引擎（HLD §14）
    REMINDER_HOUR: int = 9
    REMINDER_SKIP_WEEKEND: bool = False
    REMINDER_ADOPT_DAYS: int = 2
    REMINDER_PUBLISH_DAYS: int = 2
    REMINDER_METRIC_DAYS: str = "1,3,7"
    REMINDER_ESCALATE_HOURS: int = 24
    REMINDER_LLM_POLISH: bool = False

    def model_post_init(self, __context) -> None:
        if self.JWT_ALGORITHM != "HS256":
            raise ValueError("JWT_ALGORITHM must be HS256")
        if len(self.JWT_SECRET.encode("utf-8")) < 32:
            raise ValueError("JWT_SECRET must be at least 32 bytes")
        if "REPLACE_ME" in self.JWT_SECRET.upper():
            raise ValueError("JWT_SECRET still contains the example placeholder")
        if self.AI_API_KEY_FILE:
            self.AI_API_KEY = Path(self.AI_API_KEY_FILE).read_text(encoding="utf-8").strip()
        if self.CONTENT_AI_API_KEY_FILE:
            try:
                self.CONTENT_AI_API_KEY = Path(self.CONTENT_AI_API_KEY_FILE).read_text(
                    encoding="utf-8"
                ).strip()
            except (OSError, UnicodeError):
                # 内容域缺少 key/file 时由 factory 回落 NoneAdapter，保持 fail-closed。
                self.CONTENT_AI_API_KEY = None


settings = Settings()
