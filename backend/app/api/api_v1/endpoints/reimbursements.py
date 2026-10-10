from pathlib import Path
from datetime import datetime, timedelta
import shutil
import uuid

import fitz
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_active_user
from app.models.invoice import Invoice
from app.models.reimbursement import ReimbursementJob, ReimbursementReport, reimbursement_report_invoices
from app.schemas.reimbursement import (
    ReimbursementAmountRequest, ReimbursementAmountResponse, ReimbursementAmountSolution,
    ReimbursementJobResponse, ReimbursementMatchRequest, ReimbursementMatchResponse,
    ReimbursementReportAddInvoices, ReimbursementReportCreate, ReimbursementReportResponse,
    ReimbursementReportSummary,
)
from app.schemas.user import User
from app.services.reimbursement_service import (
    find_exact_amount_solution, match_invoice_numbers, report_response, source_path,
)
from app.workers.reimbursement_tasks import recognize_reimbursement_numbers

router = APIRouter()


def owned_report(db, user_id, report_id):
    report = db.query(ReimbursementReport).filter(
        ReimbursementReport.id == report_id, ReimbursementReport.user_id == user_id,
    ).first()
    if report is None:
        raise HTTPException(status_code=404, detail="报销单不存在")
    return report


def expire_stalled_jobs(db, user_id):
    stale = db.query(ReimbursementJob).filter(
        ReimbursementJob.user_id == user_id,
        ReimbursementJob.status.in_(["pending", "processing"]),
        ReimbursementJob.updated_at < datetime.now() - timedelta(minutes=15),
    ).all()
    for job in stale:
        job.status = "failed"
        job.error_message = "识别任务超时或服务已中断，请重新上传"
        source_path(user_id, job.id).unlink(missing_ok=True)
    if stale:
        db.commit()


def owned_job(db, user_id, job_id):
    expire_stalled_jobs(db, user_id)
    job = db.query(ReimbursementJob).filter(
        ReimbursementJob.id == job_id, ReimbursementJob.user_id == user_id,
    ).first()
    if job is None:
        raise HTTPException(status_code=404, detail="报销单记录不存在")
    return job


@router.post("/upload", response_model=ReimbursementJobResponse, status_code=202)
def upload_reimbursement(
    file: UploadFile = File(...),
    user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="仅支持 PDF 报销单")
    expire_stalled_jobs(db, user.id)
    active = db.query(ReimbursementJob).filter(
        ReimbursementJob.user_id == user.id, ReimbursementJob.status.in_(["pending", "processing"]),
    ).count()
    if active >= 3:
        raise HTTPException(status_code=429, detail="最多同时识别 3 份报销单，请等待当前任务完成")
    job_id = str(uuid.uuid4())
    path = source_path(user.id, job_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    queued = False
    try:
        size = 0
        with path.open("xb") as destination:
            while chunk := file.file.read(1024 * 1024):
                size += len(chunk)
                if size > settings.MAX_FILE_SIZE:
                    raise HTTPException(status_code=400, detail="报销单超过文件大小限制")
                destination.write(chunk)
        with path.open("rb") as source:
            if not source.read(5).startswith(b"%PDF-"):
                raise HTTPException(status_code=400, detail="文件不是有效的 PDF")
        try:
            with fitz.open(path) as document:
                if document.needs_pass:
                    raise HTTPException(status_code=400, detail="请上传未加密的 PDF")
                if not 1 <= document.page_count <= settings.REIMBURSEMENT_MAX_PAGES:
                    raise HTTPException(status_code=400, detail=f"报销单最多支持 {settings.REIMBURSEMENT_MAX_PAGES} 页")
                page_count = document.page_count
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=400, detail="无法打开 PDF，请核对文件") from None
        job = ReimbursementJob(
            id=job_id, user_id=user.id,
            filename=Path(file.filename.replace("\\", "/")).name[:255],
            status="pending", numbers=[], page_count=page_count, completed_pages=0,
        )
        db.add(job)
        db.commit()
        try:
            recognize_reimbursement_numbers.delay(job_id, user.id)
            queued = True
        except Exception:
            job.status = "failed"
            job.error_message = "识别任务未能启动，请稍后重新上传"
            db.commit()
            raise HTTPException(status_code=503, detail=job.error_message) from None
        return job
    finally:
        file.file.close()
        if not queued:
            path.unlink(missing_ok=True)


@router.get("/", response_model=list[ReimbursementJobResponse])
def list_reimbursements(user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    expire_stalled_jobs(db, user.id)
    return db.query(ReimbursementJob).filter(ReimbursementJob.user_id == user.id).order_by(
        ReimbursementJob.created_at.desc(), ReimbursementJob.id.desc(),
    ).limit(50).all()


@router.post("/{job_id}/match", response_model=ReimbursementMatchResponse)
def match_reimbursement(
    job_id: str, body: ReimbursementMatchRequest,
    user: User = Depends(get_current_active_user), db: Session = Depends(get_db),
):
    job = owned_job(db, user.id, job_id)
    if job.status != "completed":
        raise HTTPException(status_code=409, detail="请等待报销单识别完成")
    try:
        return {"items": match_invoice_numbers(db, user.id, body.invoice_nums)}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@router.post("/reports", response_model=ReimbursementReportResponse, status_code=201)
def create_reimbursement_report(
    body: ReimbursementReportCreate,
    user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    requested = {item.invoice_id: item.invoice_num for item in body.items}
    if len(requested) != len(body.items):
        raise HTTPException(status_code=400, detail="报销单中存在重复发票，请核对匹配结果")
    invoices = db.query(Invoice).filter(
        Invoice.user_id == user.id, Invoice.id.in_(requested.keys())
    ).all()
    if len(invoices) != len(requested):
        raise HTTPException(status_code=400, detail="报销单包含不存在或无权访问的发票")
    if any(invoice.invoice_num != requested[invoice.id] for invoice in invoices):
        raise HTTPException(status_code=400, detail="报销单发票号码与发票库记录不一致，请重新匹配")
    if len({invoice.invoice_num for invoice in invoices}) != len(invoices):
        raise HTTPException(status_code=400, detail="报销单中有重复发票号码，请核对")
    source_job = None
    if body.source_job_id:
        source_job = owned_job(db, user.id, body.source_job_id)
        if source_job.status != "completed":
            raise HTTPException(status_code=409, detail="报销单识别尚未完成")
    previous = db.query(ReimbursementReport).filter(
        ReimbursementReport.source_job_id == body.source_job_id,
        ReimbursementReport.user_id == user.id,
    ).first()
    if previous:
        raise HTTPException(status_code=409, detail="该报销单已经入库")
    temporary_path = source_path(user.id, body.source_job_id)
    if not temporary_path.is_file():
        raise HTTPException(status_code=409, detail="报销单原文件已过期，请重新上传后入库")
    report_id = str(uuid.uuid4())
    destination = Path(settings.UPLOAD_DIR) / "reimbursement_reports" / str(user.id) / f"{report_id}.pdf"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(temporary_path, destination)
    report = ReimbursementReport(
        id=report_id,
        user_id=user.id,
        name=(body.name or source_job.filename if source_job else body.name or "未命名报销单"),
        source_job_id=body.source_job_id,
        file_path=str(destination),
        invoices=invoices,
    )
    try:
        db.add(report)
        db.commit()
    except IntegrityError:
        db.rollback()
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=409, detail="该报销单已经入库") from None
    except Exception:
        db.rollback()
        destination.unlink(missing_ok=True)
        raise
    temporary_path.unlink(missing_ok=True)
    db.refresh(report)
    return report_response(report)


@router.get("/reports", response_model=list[ReimbursementReportSummary])
def list_reimbursement_reports(user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    reports = db.query(ReimbursementReport).filter(
        ReimbursementReport.user_id == user.id
    ).order_by(ReimbursementReport.created_at.desc()).limit(100).all()
    return [report_response(report) for report in reports]


@router.get("/reports/{report_id}", response_model=ReimbursementReportResponse)
def get_reimbursement_report(report_id: str, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    return report_response(owned_report(db, user.id, report_id))


@router.post("/reports/{report_id}/invoices", response_model=ReimbursementReportResponse)
def add_report_invoices(
    report_id: str,
    body: ReimbursementReportAddInvoices,
    user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    report = owned_report(db, user.id, report_id)
    invoices = db.query(Invoice).filter(
        Invoice.user_id == user.id, Invoice.id.in_(set(body.invoice_ids))
    ).all()
    if len(invoices) != len(set(body.invoice_ids)):
        raise HTTPException(status_code=400, detail="包含不存在或无权访问的发票")
    existing_ids = {invoice.id for invoice in report.invoices}
    report.invoices.extend(invoice for invoice in invoices if invoice.id not in existing_ids)
    db.commit()
    db.refresh(report)
    return report_response(report)


@router.delete("/reports/{report_id}/invoices/{invoice_id}", response_model=ReimbursementReportResponse)
def remove_report_invoice(
    report_id: str,
    invoice_id: str,
    user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    report = owned_report(db, user.id, report_id)
    original_count = len(report.invoices)
    report.invoices = [invoice for invoice in report.invoices if invoice.id != invoice_id]
    if len(report.invoices) == original_count:
        raise HTTPException(status_code=404, detail="发票不在该报销单中")
    db.commit()
    db.refresh(report)
    return report_response(report)


@router.delete("/reports/{report_id}", status_code=204)
def delete_reimbursement_report(report_id: str, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    report = owned_report(db, user.id, report_id)
    path = Path(report.file_path)
    db.delete(report)
    db.commit()
    path.unlink(missing_ok=True)


@router.get("/reports/{report_id}/file")
def download_reimbursement_report(report_id: str, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    report = owned_report(db, user.id, report_id)
    path = Path(report.file_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="报销单原文件不存在")
    return FileResponse(path, media_type="application/pdf", filename=report.name)


@router.post("/reports/{report_id}/amount-solution", response_model=ReimbursementAmountResponse)
def reimbursement_amount_solution(
    report_id: str,
    body: ReimbursementAmountRequest,
    user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    report = owned_report(db, user.id, report_id)
    try:
        solution = find_exact_amount_solution(report.invoices, body.amount)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    if solution is None:
        return {"target_amount": body.amount, "solution": None}
    invoices = solution["invoices"]
    return {
        "target_amount": body.amount,
        "solution": {
            "invoice_ids": [invoice.id for invoice in invoices],
            "invoice_nums": [invoice.invoice_num for invoice in invoices],
            "total_amount": solution["total_amount"],
            "invoice_count": len(invoices),
        },
    }


@router.get("/{job_id}", response_model=ReimbursementJobResponse)
def get_reimbursement(job_id: str, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    return owned_job(db, user.id, job_id)


@router.delete("/{job_id}", status_code=204)
def delete_reimbursement(job_id: str, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    job = owned_job(db, user.id, job_id)
    if job.status in ("pending", "processing"):
        raise HTTPException(status_code=409, detail="识别进行中，暂时不能删除记录")
    source_path(user.id, job.id).unlink(missing_ok=True)
    db.delete(job)
    db.commit()
