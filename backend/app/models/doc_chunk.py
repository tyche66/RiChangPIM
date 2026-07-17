from sqlalchemy import Column, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import relationship

from app.core.database import Vector
from app.models.base import CommonBase


class ProductManualChunk(CommonBase):
    __tablename__ = "product_manual_chunk"

    product_manual_id = Column(
        PGUUID(as_uuid=True), ForeignKey("product_manual.id", ondelete="CASCADE"), nullable=False
    )
    product_id = Column(
        PGUUID(as_uuid=True), ForeignKey("product.id", ondelete="CASCADE"), nullable=False
    )
    chunk_index = Column(Integer, nullable=False)
    chunk_text = Column(Text, nullable=False)
    chunk_tokens = Column(Integer, nullable=True, default=0)
    chunk_hash = Column(String(64), nullable=True)
    embedding = Column(Vector(1536), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "product_manual_id", "chunk_index", name="uq_chunk_manual_index"
        ),
    )

    manual = relationship("ProductManual")
    product = relationship("Product")
