from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import relationship

from app.models.base import CommonBase


class Proposal(CommonBase):
    __tablename__ = "proposal"

    proposal_no = Column(String(64), nullable=False, unique=True)
    proposal_name = Column(String(255), nullable=False)
    creator_id = Column(PGUUID(as_uuid=True), ForeignKey("user.id"), nullable=False)
    customer_name = Column(String(128))
    status = Column(String(20), default="draft")
    ai_polished = Column(Boolean, default=False)
    total_face_value = Column(Float, default=0)

    creator = relationship("User")
    items = relationship("ProposalItem", back_populates="proposal", cascade="all, delete-orphan")
    ai_polish_content = Column(Text, nullable=True)
    ai_polish_at = Column(DateTime(timezone=True), nullable=True)
    ai_polish_model = Column(String(64), nullable=True)


class ProposalItem(CommonBase):
    __tablename__ = "proposal_item"

    proposal_id = Column(
        PGUUID(as_uuid=True), ForeignKey("proposal.id", ondelete="CASCADE"), nullable=False
    )
    product_id = Column(PGUUID(as_uuid=True), ForeignKey("product.id"), nullable=False)
    quantity = Column(Integer, nullable=False, default=1)
    sort = Column(Integer, default=0)
    remark = Column(Text)

    proposal = relationship("Proposal", back_populates="items")
    product = relationship("Product")


class Quotation(CommonBase):
    __tablename__ = "quotation"

    quotation_no = Column(String(64), nullable=False, unique=True)
    proposal_id = Column(PGUUID(as_uuid=True), ForeignKey("proposal.id"), nullable=False)
    creator_id = Column(PGUUID(as_uuid=True), ForeignKey("user.id"), nullable=False)
    valid_until = Column(DateTime(timezone=True))
    total_amount = Column(Float, default=0)
    subtotal = Column(Float, default=0)
    tax_rate = Column(Float, default=0.13)
    discount = Column(Float, default=1.0)
    status = Column(String(20), default="draft")

    proposal = relationship("Proposal")
    creator = relationship("User")
    items = relationship("QuotationItem", back_populates="quotation", cascade="all, delete-orphan")


class QuotationItem(CommonBase):
    __tablename__ = "quotation_item"

    quotation_id = Column(
        PGUUID(as_uuid=True), ForeignKey("quotation.id", ondelete="CASCADE"), nullable=False
    )
    product_id = Column(PGUUID(as_uuid=True), ForeignKey("product.id"), nullable=False)
    quantity = Column(Integer, nullable=False, default=1)
    unit_price = Column(Float, nullable=False)
    tax_rate = Column(Float, default=0.13)
    subtotal = Column(Float, nullable=False)

    quotation = relationship("Quotation", back_populates="items")
    product = relationship("Product")
