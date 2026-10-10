import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, Text, Table, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.mysql import CHAR

from app.core.database import Base


reimbursement_report_invoices = Table(
    "reimbursement_report_invoices",
    Base.metadata,
    Column("report_id", CHAR(36), ForeignKey("reimbursement_reports.id", ondelete="CASCADE"), nullable=False),
    Column("invoice_id", CHAR(36), ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False),
    Column("created_at", DateTime, nullable=False, default=datetime.now),
    UniqueConstraint("report_id", "invoice_id", name="uq_reimbursement_report_invoice"),
)


class ReimbursementJob(Base):
    __tablename__ = "reimbursement_jobs"

    id = Column(CHAR(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    status = Column(String(20), nullable=False, default="pending", index=True)
    numbers = Column(JSON, nullable=False, default=list)
    page_count = Column(Integer, default=0)
    completed_pages = Column(Integer, default=0)
    error_message = Column(Text)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)


class ReimbursementReport(Base):
    __tablename__ = "reimbursement_reports"

    id = Column(CHAR(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    source_job_id = Column(CHAR(36), ForeignKey("reimbursement_jobs.id", ondelete="SET NULL"), nullable=True, unique=True)
    file_path = Column(String(500), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    invoices = relationship(
        "Invoice",
        secondary=reimbursement_report_invoices,
        order_by="Invoice.created_at, Invoice.id",
        lazy="selectin",
    )
