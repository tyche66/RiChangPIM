from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _service_environment(compose_text: str, service: str) -> dict[str, str]:
    lines = compose_text.splitlines()
    service_start = lines.index(f"  {service}:")
    environment_start = next(
        index
        for index in range(service_start + 1, len(lines))
        if lines[index] == "    environment:"
    )
    values = {}
    for line in lines[environment_start + 1 :]:
        if not line.startswith("      - "):
            break
        key, value = line.removeprefix("      - ").split("=", 1)
        values[key] = value
    return values


def test_backend_and_postgres_receive_same_required_password():
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    expected = "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"
    backend_env = _service_environment(compose, "backend")
    postgres_env = _service_environment(compose, "postgres")

    assert backend_env["POSTGRES_PASSWORD"] == expected
    assert postgres_env["POSTGRES_PASSWORD"] == expected
    assert expected in backend_env["DATABASE_URL"]


def test_production_requires_admin_password():
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    backend_env = _service_environment(compose, "backend")
    assert backend_env["ADMIN_PASSWORD"] == "${ADMIN_PASSWORD:-}"


def test_pgvector_uses_sqlalchemy_type_without_conflicting_asyncpg_codec():
    from app.core import database

    assert database.Vector.__module__ == "pgvector.sqlalchemy.vector"
    assert not hasattr(database, "_register_vector_asyncpg")
    assert not hasattr(database, "_register_vector")
