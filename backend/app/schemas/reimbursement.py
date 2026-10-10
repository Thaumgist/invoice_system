from datetime import datetime
from decimal import Decimal
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

class ReimbursementNumber(BaseModel):
    invoice_num: str
    pages: List[int] = Field(default_factory=list)
    occurrences: int = 1
    confidence: Optional[float] = None
    source: Literal["text", "ocr", "manual"]


class ReimbursementJobResponse(BaseModel):
    id: str
    filename: str
    status: str
    page_count: int
    completed_pages: int
    numbers: List[ReimbursementNumber]
    error_message: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ReimbursementMatchRequest(BaseModel):
    invoice_nums: List[str] = Field(..., max_length=500)


class ReimbursementInvoice(BaseModel):
    id: str
    original_filename: str
    invoice_num: Optional[str] = None
    seller_name: Optional[str] = None
    invoice_date: Optional[datetime] = None
    total_amount: Optional[Decimal] = None
    amount_in_figures: Optional[Decimal] = None

    class Config:
        from_attributes = True


class ReimbursementMatch(BaseModel):
    invoice_num: str
    status: Literal["matched", "not_found", "ambiguous"]
    invoices: List[ReimbursementInvoice]


class ReimbursementMatchResponse(BaseModel):
    items: List[ReimbursementMatch]


class ReimbursementReportItem(BaseModel):
    invoice_id: str
    invoice_num: str


class ReimbursementReportCreate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    source_job_id: str
    items: List[ReimbursementReportItem] = Field(..., min_length=1, max_length=500)


class ReimbursementReportAddInvoices(BaseModel):
    invoice_ids: List[str] = Field(..., min_length=1, max_length=500)


class ReimbursementReportInvoice(BaseModel):
    id: str
    original_filename: str
    invoice_num: Optional[str] = None
    seller_name: Optional[str] = None
    invoice_date: Optional[datetime] = None
    total_amount: Optional[Decimal] = None
    amount_in_figures: Optional[Decimal] = None
    reimbursement_status: Optional[str] = None

    class Config:
        from_attributes = True


class ReimbursementReportResponse(BaseModel):
    id: str
    name: str
    source_job_id: Optional[str] = None
    file_available: bool
    invoice_count: int
    total_amount: Decimal
    invoices: List[ReimbursementReportInvoice]
    created_at: datetime
    updated_at: datetime


class ReimbursementReportSummary(BaseModel):
    id: str
    name: str
    source_job_id: Optional[str] = None
    file_available: bool
    invoice_count: int
    total_amount: Decimal
    created_at: datetime
    updated_at: datetime


class ReimbursementAmountRequest(BaseModel):
    amount: Decimal = Field(..., ge=0, max_digits=15, decimal_places=2)


class ReimbursementAmountSolution(BaseModel):
    invoice_ids: List[str]
    invoice_nums: List[str]
    total_amount: Decimal
    invoice_count: int


class ReimbursementAmountResponse(BaseModel):
    target_amount: Decimal
    solution: Optional[ReimbursementAmountSolution] = None
