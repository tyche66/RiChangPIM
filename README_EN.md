# AI-PIM RiChangPIM

[中文 README](README.md)

RiChangPIM is an AI-assisted Product Information Management platform. It combines structured product data, media assets, proposals, quotations, secure sharing, and a pluggable AI / Knowledge Gateway layer.

## Current Release

| Item | Value |
| --- | --- |
| Release | `v1.9.1` |
| Database | PostgreSQL 16 + pgvector |
| Backend | FastAPI + SQLAlchemy + Alembic |
| Admin | Vue 3 + Vite + Element Plus + Pinia |
| AI Portal | Vue 3 + Vite, served separately from Admin |
| Cache | Redis 7 |
| Object storage | MinIO, bucket `ai-pim` |
| Migration head | `0017_operation_log_username` |
| Local production entry | `http://127.0.0.1:888/` |

The `v1.9.1` release includes product media import from XLSX/XLSM and ZIP files, import template download, row-isolated import failures, image deduplication, and MinIO-backed media binding.

## Quick Start

### Development

```bash
docker compose -f docker-compose.dev.yml up -d
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Run Admin from `frontend/` and Portal from `portal/` with `npm install && npm run dev`. Development services publish PostgreSQL `5432`, Redis `6379`, MinIO `9000/9001`, and Gotenberg `8002`.

### Production Compose

```bash
cp .env.example .env
# Set strong POSTGRES_PASSWORD, JWT_SECRET, ADMIN_PASSWORD and MINIO_ROOT_* values.
export PATH="$HOME/.nvm/versions/node/v24.18.0/bin:$PATH"
bash scripts/build_frontends.sh
docker compose up -d
```

The backend entrypoint runs migrations, administrator initialization, and seed data before starting Uvicorn. After frontend or nginx changes, rebuild the nginx image because the frontend distributions are copied into the image:

```bash
bash scripts/build_frontends.sh
docker compose build nginx
docker compose up -d --no-deps nginx
```

## Endpoints

- Portal and sharing: `http://127.0.0.1:888/`
- Admin: `http://127.0.0.1:888/admin/`
- API: `http://127.0.0.1:888/api/v1/`
- Local FastAPI docs during development: `http://localhost:8000/docs`
- OpenAPI JSON during development: `http://localhost:8000/openapi.json`

The current local production stack exposes nginx on `888:80`. PostgreSQL, Redis, MinIO, Gotenberg, and OCR are internal Compose services and are not production host ports.

## Storage

The application bucket is `ai-pim`. Products, scene images, manuals, and attachments are stored in MinIO. Derived thumbnails use `derived/thumb/w{width}/...` and may be rebuilt from original objects.

See:

- [Storage volumes](docs/数据卷与持久化存储.md)
- [MinIO operations](docs/MinIO对象存储.md)
- [Operations runbook](README-OPS.md)
- [Full migration bundle](MIGRATION_BUNDLE.md)
- [Cloud update package](docs/云端更新包.md)

## API Documentation

The maintained human contract is [docs/04-接口规范(OpenAPI).md](docs/04-接口规范(OpenAPI).md). FastAPI also generates `/docs`, `/redoc`, and `/openapi.json` from the running application. The generated specification is the machine-readable source of truth for route and schema details.

## Testing

```bash
cd backend
PYTHONPATH=. pytest

cd ../frontend
npm run test
npm run build
```

For the complete release gate, use `bash scripts/release_gate.sh`. Database integration tests require the dedicated `ai_pim_test` database.

## Documentation Map

- `README.md`: Chinese project overview
- `README_EN.md`: English project overview
- `README-OPS.md`: current machine operations and recovery runbook
- `docs/`: current product, architecture, API, deployment, storage, and test documentation
- `docs/过时/`: archived design, planning, review, delivery, and superseded deployment documents
- `AI-Docs/`: independent pluggable AI architecture, planning, governance, and extension documentation
- `RELEASE_GATE.md`: release checks
- `CHANGELOG.md`: release history

## Security

Never commit `.env`, AI keys, database passwords, MinIO credentials, migration bundles, or production data. The full migration bundle contains secrets and business data and must remain outside GitHub and public channels.

## License

Proprietary.
