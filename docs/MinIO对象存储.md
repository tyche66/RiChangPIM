# MinIO 对象存储

本文档描述当前 `v1.9.1` 的 MinIO 使用、备份和恢复规则。

## 连接配置

| 环境 | Endpoint | Console | 说明 |
| --- | --- | --- | --- |
| 生产 Compose | `minio:9000` | `minio:9001` | 仅 Compose 网络可达 |
| 开发 Compose | `localhost:9000` | `http://localhost:9001` | `docker-compose.dev.yml` 发布端口 |
| 后端配置 | `MINIO_ENDPOINT` | 不由后端使用 | endpoint 不含协议 |

应用和备份脚本的统一默认值为：

```text
MINIO_BUCKET=ai-pim
```

备份命令必须显式传入同一个 bucket，禁止依赖脚本中的其他默认值。生产凭据使用 `MINIO_ROOT_USER`、`MINIO_ROOT_PASSWORD`，后端分别通过 `MINIO_ACCESS_KEY`、`MINIO_SECRET_KEY` 注入。

## 对象内容

MinIO 保存产品主图、产品附图、场景图、说明书和其他媒体附件。`attachment`、`product_image`、`scene_image` 等数据库记录保存对象引用和业务关系，数据库与 MinIO 必须成对备份。

缩略图是派生对象，使用如下规则：

```text
derived/thumb/w{width}/{original_key}.webp
```

允许的 `width` 为 `96`、`192`、`240`、`480`、`960`。缩略图缺失时由服务端读穿生成；删除原图或替换原图时应清理对应派生对象。

## 备份

统一备份：

```bash
ENV_FILE=/etc/ai-pim/backup.env \
BACKUP_DIR=./backups \
MINIO_ENDPOINT=http://minio:9000 \
MINIO_ROOT_USER="$MINIO_ROOT_USER" \
MINIO_ROOT_PASSWORD="$MINIO_ROOT_PASSWORD" \
MINIO_BUCKET=ai-pim \
scripts/backup.sh
```

MinIO 单独备份依赖 `mc`：

```bash
MINIO_ENDPOINT=http://localhost:9000 \
MINIO_ROOT_USER=<user> \
MINIO_ROOT_PASSWORD=<password> \
MINIO_BUCKET=ai-pim \
scripts/minio_backup.sh
```

脚本会生成 `minio.tar.gz`、SHA-256 文件、组件 manifest 和对象数量；完整批次状态在 `backups/last_status.json`。bucket 不存在或连接失败必须视为失败，不得把错误 bucket 的空备份当作成功。

## 恢复

恢复必须显式指定目标 endpoint 和目标 bucket，建议先恢复到隔离的测试 bucket：

```bash
MINIO_ENDPOINT=http://localhost:9000 \
MINIO_ROOT_USER=<user> \
MINIO_ROOT_PASSWORD=<password> \
MINIO_BUCKET=ai-pim-restore \
scripts/minio_restore.sh backups/<batch_id>/minio.tar.gz
```

恢复脚本不会删除 Docker volume，也不会自动清理目标 bucket。生产恢复前必须取得明确授权，并在 PostgreSQL 恢复后核对对象引用、产品封面、场景图和说明书下载链路。
