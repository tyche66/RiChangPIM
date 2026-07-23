from app.api.v1.auth import router as auth_router
from app.api.v1.brands import router as brands_router
from app.api.v1.categories import router as categories_router
from app.api.v1.files import router as files_router
from app.api.v1.health import router as health_router
from app.api.v1.products import router as products_router
from app.api.v1.proposals import router as proposals_router
from app.api.v1.quotations import router as quotations_router
from app.api.v1.roles import router as roles_router
from app.api.v1.scene_images import router as scene_images_router
from app.api.v1.share_token import router as share_token_router
from app.api.v1.shares import router as shares_router
from app.api.v1.stats import router as stats_router
from app.api.v1.suppliers import router as suppliers_router
from app.api.v1.tags import router as tags_router
from app.api.v1.users import router as users_router
from app.api.v1.version import router as version_router

__all__ = [
    "auth_router",
    "users_router",
    "roles_router",
    "products_router",
    "categories_router",
    "brands_router",
    "suppliers_router",
    "tags_router",
    "proposals_router",
    "shares_router",
    "health_router",
    "share_token_router",
    "quotations_router",
    "files_router",
    "stats_router",
    "scene_images_router",
    "version_router",
]
