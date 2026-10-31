FROM python:3.11-slim@sha256:9534e5a8e315485d4061ed659af0fd78a284c015f9b73661b41d6bab25604534

ARG APP_VERSION=dev
ARG BUILD_ID=dev-local
ARG GIT_COMMIT=unknown
ARG BUILD_TIME=unknown
ARG APP_ENV=production
# 本镜像默认不装编译工具链：requirements 里的 psycopg2-binary / psycopg[binary] /
# asyncpg / pgvector 在 python:3.11-slim 上都有预编译 wheel，apt 只在自建
# 依赖时才需要。默认关闭让构建不依赖发行版软件源（离线、镜像源不可达、代理
# 未透传时不至于整个构建失败）；确实要编译时 --build-arg INSTALL_BUILD_DEPS=1。
ARG INSTALL_BUILD_DEPS=0

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_VERSION=${APP_VERSION} \
    BUILD_ID=${BUILD_ID} \
    GIT_COMMIT=${GIT_COMMIT} \
    BUILD_TIME=${BUILD_TIME} \
    APP_ENV=${APP_ENV}

RUN if [ "$INSTALL_BUILD_DEPS" = "1" ]; then \
        apt-get update && apt-get install -y --no-install-recommends \
            gcc \
            libpq-dev \
        && rm -rf /var/lib/apt/lists/*; \
    fi

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN useradd --create-home --uid 1000 --shell /usr/sbin/nologin appuser
COPY --chown=appuser:appuser . .

RUN chmod +x docker/backend-entrypoint.sh
USER appuser

# 自包含健康探针（Python），不依赖容器内 curl/pg_isready。
# 通过 docker compose 运行时，compose 的 healthcheck 配置会覆盖此处。
HEALTHCHECK --interval=15s --timeout=5s --retries=5 --start-period=30s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/api/v1/health').status==200 else 1)"

# 容器启动后自动完成：迁移 -> 初始管理员 -> 种子数据 -> 启动服务
ENTRYPOINT ["./docker/backend-entrypoint.sh"]
