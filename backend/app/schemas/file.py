from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class FileUploadResponse(BaseModel):
    attachment_id: UUID
    file_name: str
    file_url: str
    preview_url: str | None = None
    file_type: str
    file_size: int

    model_config = ConfigDict(from_attributes=True)


class FileDownloadMeta(BaseModel):
    file_name: str
    file_type: str
    file_size: int


class FilePresignResponse(BaseModel):
    preview_url: str
    expire_in: int = 900


class ProductImageRef(BaseModel):
    product_id: UUID
    product_no: str
    product_name: str
    product_image_id: UUID
    is_cover: bool


class SceneImageBoundProduct(BaseModel):
    product_id: UUID
    product_no: str
    product_name: str


class SceneImageRef(BaseModel):
    scene_image_id: UUID
    scene_image_name: str
    bound_products: list[SceneImageBoundProduct]


class ManualRef(BaseModel):
    manual_id: UUID
    product_id: UUID
    product_no: str
    product_name: str
    doc_type: str


class FileReferences(BaseModel):
    product_images: list[ProductImageRef] = []
    scene_images: list[SceneImageRef] = []
    manuals: list[ManualRef] = []


class FileDetailResponse(BaseModel):
    id: UUID
    file_name: str
    file_type: str
    file_size: int
    file_url: str
    preview_url: str | None = None
    create_time: datetime | None = None
    update_time: datetime | None = None
    ref_count: int = 0
    references: FileReferences | None = None

    model_config = ConfigDict(from_attributes=True)


__all__ = [
    "FileUploadResponse",
    "FileDownloadMeta",
    "FilePresignResponse",
    "FileDetailResponse",
    "FileReferences",
    "ProductImageRef",
    "SceneImageRef",
    "ManualRef",
]
