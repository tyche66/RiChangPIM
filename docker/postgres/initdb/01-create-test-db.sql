-- ============================================================================
-- AI-PIM PostgreSQL 初始化脚本（仅需数据目录为空时由官方镜像自动执行一次）
--
-- 作用：在默认库 ai_pim 之外，创建集成测试专用库 ai_pim_test。
--   - 测试库名字含 "test"，conftest 的探针才会允许落库/清库；
--   - TEST_DATABASE_URL 默认即指向 ai_pim_test，无需额外配置即可跑 pytest；
--   - 数据随 ./docker/volumes/postgres 留在项目目录内，便于随目录迁移。
--
-- 幂等：ai_pim_test 已存在则跳过（\gexec 仅对返回行执行）。
-- 若数据目录已初始化（脚本不重跑），请用 scripts/create_test_db.sh 补建。
-- ============================================================================

SELECT 'CREATE DATABASE ai_pim_test'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'ai_pim_test')\gexec
