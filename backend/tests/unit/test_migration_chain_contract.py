"""Static Alembic ancestry contract; does not connect to a database."""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def test_track_a_migrations_follow_one_linear_head():
    backend = Path(__file__).resolve().parents[2]
    config = Config(str(backend / "alembic.ini"))
    config.set_main_option("script_location", str(backend / "alembic"))
    scripts = ScriptDirectory.from_config(config)

    assert scripts.get_heads() == ["0030_content_dna_fields"]
    expected = [
        "0017_operation_log_username",
        "0018_qwen_embedding_hnsw",
        "0019_crm_base_tables",
        "0020_crm_perms",
        "0021_content_tables",
        "0022_reminders",
        "0023_crm_sales_links_compat",
        "0024_attachment_biz_domain_compat",
        "0025_crm_schema_compat",
        "0026_catalog_attributes",
        "0027_content_skills",
        "0028_project_spaces",
        "0029_project_remark",
        "0030_content_dna_fields",
    ]
    revision = scripts.get_revision("0030_content_dna_fields")
    actual = []
    while revision is not None and revision.revision != "0016_embedding_dim_2048":
        actual.append(revision.revision)
        revision = scripts.get_revision(revision.down_revision)

    assert actual == list(reversed(expected))
