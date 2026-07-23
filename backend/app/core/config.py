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
    VERSION: str = "0.1.0"
    APP_VERSION: str | None = None
    BUILD_ID: str = "dev-local"
    GIT_COMMIT: str = "unknown"
    BUILD_TIME: str = "unknown"
    APP_ENV: str = "development"

    DATABASE_URL: str
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 10
    REDIS_URL: str

    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 120

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

    AI_CHAT_MODEL: str = "gpt-4o-mini"
    AI_EMBEDDING_MODEL: str = "text-embedding-3-small"
    AI_EMBEDDING_DIM: int = 1536
    AI_TIMEOUT: float = 30.0
    AI_RAG_TOP_K: int = 8
    AI_RAG_MIN_SCORE: float = 0.65
    AI_RAG_CHUNK_SIZE: int = 600
    AI_RAG_CHUNK_OVERLAP: int = 80

    SHARE_IMAGE_URL_EXPIRE_HOURS: int = 24


settings = Settings()
