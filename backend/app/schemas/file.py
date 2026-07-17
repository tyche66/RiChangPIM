from uuid import UUID

from pydantic import BaseModel, ConfigDict


class FileUploadResponse(BaseModel):
    attachment_id: UUID
    file_name: str
    file_url: str
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


__all__ = ["FileUploadResponse", "FileDownloadMeta", "FilePresignResponse"]
