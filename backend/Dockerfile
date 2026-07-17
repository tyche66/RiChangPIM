FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chmod +x docker/backend-entrypoint.sh

# 自包含健康探针（Python），不依赖容器内 curl/pg_isready。
# 通过 docker compose 运行时，compose 的 healthcheck 配置会覆盖此处。
HEALTHCHECK --interval=15s --timeout=5s --retries=5 --start-period=30s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/api/v1/health').status==200 else 1)"

# 容器启动后自动完成：迁移 -> 初始管理员 -> 种子数据 -> 启动服务
ENTRYPOINT ["./docker/backend-entrypoint.sh"]
