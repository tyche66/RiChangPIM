"""Unit tests for permission seed sync (HLD §6.3).

Asserts that seed_data.py contains every permission seeded by the CRM and
Track B migrations.
"""

import ast
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

# tests/test_permission_seed_sync.py -> backend/tests/test_permission_seed_sync.py
# .parent = backend/tests/
# .parent.parent = backend/
BACKEND_ROOT = Path(__file__).parent.parent

SEED_DATA_PATH = BACKEND_ROOT / "app" / "scripts" / "seed_data.py"
MIGRATION_PATHS = (
    BACKEND_ROOT / "alembic" / "versions" / "0020_crm_perms.py",
    BACKEND_ROOT / "alembic" / "versions" / "0027_content_skills.py",
)


def _import_seed_data():
    """Import seed_data.py PERMISSIONS without executing app imports."""
    with open(SEED_DATA_PATH) as f:
        source = f.read()

    tree = ast.parse(source)

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "PERMISSIONS":
                    return ast.literal_eval(node.value)

    raise ValueError("PERMISSIONS not found in seed_data.py")


def _import_seed_roles():
    """Import seed_data.py ROLES without executing app imports."""
    with open(SEED_DATA_PATH) as f:
        source = f.read()

    tree = ast.parse(source)

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "ROLES":
                    return ast.literal_eval(node.value)

    raise ValueError("ROLES not found in seed_data.py")


def _import_migrations():
    """Import NEW_PERMISSIONS from all post-seed permission migrations."""
    permissions = []
    for migration_path in MIGRATION_PATHS:
        with open(migration_path) as f:
            source = f.read()

        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "NEW_PERMISSIONS":
                        permissions.extend(ast.literal_eval(node.value))
    return permissions


class TestPermissionSeedSync:
    """Permission seed sync tests."""

    def test_seed_data_permissions_match_migration(self):
        """PERMISSIONS in seed_data.py == NEW_PERMISSIONS in 0020_crm_perms.

        The migration only contains NEW permissions (CRM-Lite + scene_image),
        while seed_data.py contains ALL permissions (including pre-existing).
        So we verify that all migration permissions exist in seed_data.
        """
        seed_perms = _import_seed_data()
        migration_perms = _import_migrations()

        seed_codes = {p[0] for p in seed_perms}
        migration_codes = {p[0] for p in migration_perms}

        # All migration permissions must be in seed_data
        assert migration_codes.issubset(seed_codes), (
            f"Migration permissions missing from seed_data.py: {migration_codes - seed_codes}"
        )

    def test_seed_data_has_crm_permissions(self):
        """seed_data.py includes all 16 CRM-Lite permissions (HLD §6.1)."""
        seed_perms = _import_seed_data()
        seed_codes = {p[0] for p in seed_perms}

        crm_perms = {
            "customer:view", "customer:edit", "customer:pii",
            "customer:export", "customer:transfer",
            "project:view", "project:edit", "project:member", "project:asset",
            "dashboard:view",
            "content:view", "content:generate", "content:adopt",
            "content:publish", "content:metric", "content:manage",
            "reminder:edit",
        }
        assert crm_perms.issubset(seed_codes), (
            f"Missing CRM permissions in seed_data.py: {crm_perms - seed_codes}"
        )

    def test_seed_data_has_scene_image_permissions(self):
        """seed_data.py includes scene_image permissions (G0-4.8 drift fix)."""
        seed_perms = _import_seed_data()
        seed_codes = {p[0] for p in seed_perms}

        scene_image_perms = {
            "scene_image:view", "scene_image:create",
            "scene_image:edit", "scene_image:delete",
        }
        assert scene_image_perms.issubset(seed_codes), (
            f"Missing scene_image permissions in seed_data.py: {scene_image_perms - seed_codes}"
        )

    def test_seed_data_has_new_roles(self):
        """seed_data.py includes manager/designer/operator roles."""
        roles = _import_seed_roles()
        role_codes = {r[0] for r in roles}

        expected_roles = {
            "admin", "manager", "sales", "designer", "operator", "purchaser", "viewer"
        }
        assert expected_roles.issubset(role_codes), (
            f"Missing roles in seed_data.py: {expected_roles - role_codes}"
        )

    def test_migration_has_crm_permissions(self):
        """Migration 0020_crm_perms includes all 16 CRM-Lite permissions."""
        migration_perms = _import_migrations()
        migration_codes = {p[0] for p in migration_perms}

        crm_perms = {
            "customer:view", "customer:edit", "customer:pii",
            "customer:export", "customer:transfer",
            "project:view", "project:edit", "project:member", "project:asset",
            "dashboard:view",
            "content:view", "content:generate", "content:adopt",
            "content:publish", "content:metric", "content:manage",
            "reminder:edit",
        }
        assert crm_perms.issubset(migration_codes), (
            f"Missing CRM permissions in migration: {crm_perms - migration_codes}"
        )

    def test_migration_has_new_roles(self):
        """Migration 0020_crm_perms includes manager/designer/operator roles."""
        migration_path = BACKEND_ROOT / "alembic" / "versions" / "0020_crm_perms.py"
        with open(migration_path) as f:
            source = f.read()

        tree = ast.parse(source)

        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "NEW_ROLES":
                        roles = ast.literal_eval(node.value)
                        role_codes = {r[0] for r in roles}
                        break

        expected_roles = {"manager", "designer", "operator"}
        assert expected_roles.issubset(role_codes), (
            f"Missing roles in migration: {expected_roles - role_codes}"
        )

    def test_content_manage_is_admin_only_in_seed_data(self):
        source = SEED_DATA_PATH.read_text()
        tree = ast.parse(source)
        role_permissions = None
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "ROLE_PERMISSIONS":
                        role_permissions = ast.literal_eval(node.value)
                        break
        assert role_permissions is not None
        assert role_permissions["admin"] == ["*"]
        assert all(
            "content:manage" not in role_permissions.get(role, [])
            for role in ("purchaser", "sales", "viewer", "manager", "designer", "operator")
        )
