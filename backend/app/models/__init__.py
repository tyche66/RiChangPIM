from app.models.ai_action import PendingAction
from app.models.audit import AIConversation, OperationLog, Share, ShareLog, ShareToken, Visitor
from app.models.content import (
    ContentBatch,
    ContentItem,
    ContentMetricSnapshot,
    ContentPublication,
)
from app.models.customer import (
    Customer,
    CustomerDialogue,
    CustomerDialogueAttachment,
    EntityStageLog,
    FollowUp,
    Requirement,
)
from app.models.doc_chunk import ProductManualChunk
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument, KnowledgeIndexJob
from app.models.product import (
    Attachment,
    Brand,
    Category,
    Product,
    ProductImage,
    ProductManual,
    ProductTag,
    SceneImage,
    Supplier,
    Tag,
    product_scene_image,
)
from app.models.project import Project, ProjectAsset, ProjectMember
from app.models.reminder import Notification, Reminder
from app.models.sales import Proposal, ProposalItem, Quotation, QuotationItem
from app.models.user import Permission, Role, RolePermission, User

__all__ = [
    "AIConversation",
    "Attachment",
    "Brand",
    "Category",
    "ContentBatch",
    "ContentItem",
    "ContentMetricSnapshot",
    "ContentPublication",
    "Customer",
    "CustomerDialogue",
    "CustomerDialogueAttachment",
    "EntityStageLog",
    "FollowUp",
    "Requirement",
    "KnowledgeChunk",
    "KnowledgeDocument",
    "KnowledgeIndexJob",
    "Notification",
    "OperationLog",
    "PendingAction",
    "Permission",
    "Product",
    "ProductImage",
    "ProductManual",
    "ProductManualChunk",
    "ProductTag",
    "Project",
    "ProjectAsset",
    "ProjectMember",
    "Proposal",
    "ProposalItem",
    "Quotation",
    "QuotationItem",
    "Reminder",
    "Role",
    "RolePermission",
    "SceneImage",
    "Share",
    "ShareLog",
    "ShareToken",
    "Supplier",
    "Tag",
    "User",
    "Visitor",
    "product_scene_image",
]
