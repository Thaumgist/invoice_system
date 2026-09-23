"""
邮件管理API端点
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Any, Dict, Optional
from pydantic import BaseModel
from datetime import datetime

from app.core.database import get_db
from app.core.deps import get_current_user
from app.services.email_list_service import EmailListService
from app.services.email_service import EmailService
from app.services.invoice_service import InvoiceService
from app.schemas.email import (
    Email, EmailFilter, PaginationParams, EmailListResponse, 
    EmailStatistics, EmailBatchOperation, EmailBatchOperationResponse,
    EmailUpdate
)
from app.schemas.user import User
from app.workers.email_tasks import _process_scanned_file

router = APIRouter()


def _fail_stored_rescan(
    db: Session,
    email_record,
    reason: str,
    links_processed: int = 0,
    errors: Optional[list[str]] = None,
) -> Dict[str, Any]:
    now = datetime.now()
    email_record.invoice_scan_status = "pending"
    email_record.processing_status = "failed"
    email_record.invoice_count = 0
    email_record.error_message = reason
    email_record.scan_result = {
        "source": "stored_email_rescan",
        "links_processed": links_processed,
        "invoices_found": 0,
        "errors": errors or [reason],
        "scan_completed": True,
        "scan_time": now.isoformat(),
    }
    email_record.scanned_at = now
    email_record.updated_at = now
    db.commit()
    return {
        "success": False,
        "reason": reason,
        "links_processed": links_processed,
        "found": 0,
        "imported": 0,
        "duplicates": 0,
    }


def _rescan_saved_email_links(
    db: Session,
    email_list_service: EmailListService,
    user_id: int,
    email_id: str,
) -> Dict[str, Any]:
    """重扫已保存邮件正文中的 PDF 链接。

    历史附件内容没有落库，无法从邮件列表记录恢复；但京东这类链接型发票可以
    直接用保存的 body_text/body_html 重新下载并导入。
    """
    email_record = email_list_service.get_email_detail(email_id, user_id)
    if not email_record:
        return {
            "success": False,
            "reason": "email_not_found",
            "links_processed": 0,
            "found": 0,
            "imported": 0,
            "duplicates": 0,
        }

    now = datetime.now()
    email_record.invoice_scan_status = "pending"
    email_record.processing_status = "processing"
    email_record.invoice_count = 0
    email_record.scan_result = None
    email_record.error_message = None
    email_record.updated_at = now
    db.commit()

    email_service = EmailService(db)
    invoice_service = InvoiceService(db)
    body = f"{email_record.body_text or ''} {email_record.body_html or ''}"
    context_text = f"{email_record.subject or ''} {body}"
    pdf_links = email_service._extract_pdf_links(body)

    if not pdf_links:
        return _fail_stored_rescan(
            db,
            email_record,
            "已保存邮件正文中没有可重扫的 PDF 链接；附件型历史邮件需要重新从邮箱扫描原件",
            links_processed=0,
        )

    imported = 0
    duplicates = 0
    errors: list[str] = []
    processed_files = []

    for link in pdf_links:
        scan_results = email_service._download_and_process_pdf(
            user_id=user_id,
            url=link,
            email_id=email_record.id,
            context_text=context_text,
        )
        if not scan_results:
            errors.append("PDF 链接下载或预检失败")
            continue

        for scan_result in scan_results:
            filename = scan_result.get("filename")
            if scan_result.get("status") == "duplicate":
                duplicates += 1
                processed_files.append({
                    "filename": filename,
                    "status": "duplicate",
                    "existing_invoice_id": scan_result.get("existing_invoice_id"),
                })
                continue

            try:
                invoice_id = _process_scanned_file(user_id, scan_result, invoice_service)
            except Exception as exc:
                errors.append(f"{filename or 'unknown.pdf'}: {str(exc)}")
                continue

            if invoice_id == "DUPLICATE":
                duplicates += 1
                processed_files.append({"filename": filename, "status": "duplicate"})
            elif invoice_id:
                imported += 1
                processed_files.append({
                    "filename": filename,
                    "status": "success",
                    "invoice_id": invoice_id,
                })
            else:
                errors.append(f"{filename or 'unknown.pdf'}: 导入失败")

    found = imported + duplicates
    scan_result_payload = {
        "source": "stored_email_rescan",
        "attachments_processed": 0,
        "links_processed": len(pdf_links),
        "invoices_found": found,
        "imported": imported,
        "duplicates": duplicates,
        "errors": errors,
        "files": processed_files[:10],
        "scan_completed": True,
        "scan_time": datetime.now().isoformat(),
    }

    if found:
        email_list_service.update_scan_status(
            email_id=email_record.id,
            user_id=user_id,
            scan_status="has_invoice",
            invoice_count=found,
            scan_result=scan_result_payload,
        )
        return {
            "success": True,
            "links_processed": len(pdf_links),
            "found": found,
            "imported": imported,
            "duplicates": duplicates,
        }

    return _fail_stored_rescan(
        db,
        email_record,
        "PDF 链接已找到，但下载、预检或导入失败",
        links_processed=len(pdf_links),
        errors=errors or ["PDF 链接处理失败"],
    )


@router.get("", response_model=EmailListResponse)
def get_emails(
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(20, ge=1, le=100, description="每页大小"),
    invoice_scan_status: Optional[str] = Query(None, description="发票扫描状态"),
    processing_status: Optional[str] = Query(None, description="处理状态"),
    sender: Optional[str] = Query(None, description="发送者"),
    subject: Optional[str] = Query(None, description="主题关键词"),
    has_attachments: Optional[bool] = Query(None, description="是否有附件"),
    has_invoice: Optional[bool] = Query(None, description="是否检测到发票"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取邮件列表"""
    email_service = EmailListService(db)
    
    # 构建筛选条件
    filters = EmailFilter(
        invoice_scan_status=invoice_scan_status,
        processing_status=processing_status,
        sender=sender,
        subject=subject,
        has_attachments=has_attachments,
        has_invoice=has_invoice
    ).dict(exclude_unset=True)
    
    emails, total = email_service.get_emails(
        user_id=current_user.id,
        page=page,
        size=size,
        filters=filters
    )
    
    return EmailListResponse.create(emails, total, page, size)


# 新增：POST 搜索接口，支持复杂筛选通过请求体提交
class EmailSearchRequest(BaseModel):
    page: int = 1
    size: int = 20
    invoice_scan_status: Optional[str] = None
    processing_status: Optional[str] = None
    sender: Optional[str] = None
    subject: Optional[str] = None
    has_attachments: Optional[bool] = None
    has_invoice: Optional[bool] = None


@router.post("/search", response_model=EmailListResponse)
def search_emails(
    body: EmailSearchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取邮件列表（POST）"""
    email_service = EmailListService(db)

    filters = EmailFilter(
        invoice_scan_status=body.invoice_scan_status,
        processing_status=body.processing_status,
        sender=body.sender,
        subject=body.subject,
        has_attachments=body.has_attachments,
        has_invoice=body.has_invoice,
    ).dict(exclude_unset=True)

    emails, total = email_service.get_emails(
        user_id=current_user.id,
        page=body.page,
        size=body.size,
        filters=filters,
    )

    return EmailListResponse.create(emails, total, body.page, body.size)


@router.get("/statistics", response_model=EmailStatistics)
def get_email_statistics(
    days: int = Query(30, ge=1, le=365, description="统计天数"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取邮件统计信息"""
    email_service = EmailListService(db)
    statistics = email_service.get_email_statistics(current_user.id, days)
    return EmailStatistics(**statistics)


@router.get("/{email_id}", response_model=Email)
def get_email_detail(
    email_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取邮件详情"""
    email_service = EmailListService(db)
    email = email_service.get_email_detail(email_id, current_user.id)
    
    if not email:
        raise HTTPException(status_code=404, detail="邮件不存在")
    
    return email


@router.put("/{email_id}", response_model=Email)
def update_email(
    email_id: str,
    email_update: EmailUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """更新邮件信息"""
    email_service = EmailListService(db)
    
    # 获取邮件
    email = email_service.get_email_detail(email_id, current_user.id)
    if not email:
        raise HTTPException(status_code=404, detail="邮件不存在")
    
    # 更新扫描状态
    if email_update.invoice_scan_status:
        success = email_service.update_scan_status(
            email_id=email_id,
            user_id=current_user.id,
            scan_status=email_update.invoice_scan_status,
            invoice_count=email_update.invoice_count or 0,
            scan_result=email_update.scan_result
        )
        if not success:
            raise HTTPException(status_code=400, detail="更新扫描状态失败")
    
    # 获取更新后的邮件
    updated_email = email_service.get_email_detail(email_id, current_user.id)
    return updated_email


@router.post("/batch", response_model=EmailBatchOperationResponse)
def batch_operation(
    operation: EmailBatchOperation,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """批量操作邮件"""
    email_service = EmailListService(db)
    
    if operation.operation == "rescan":
        rescan_results = [
            _rescan_saved_email_links(db, email_service, current_user.id, email_id)
            for email_id in operation.email_ids
        ]
        failed_details = [
            {
                "email_id": email_id,
                "reason": item.get("reason", "rescan_failed"),
            }
            for email_id, item in zip(operation.email_ids, rescan_results)
            if not item.get("success")
        ]
        processed = len(operation.email_ids) - len(failed_details)
        imported = sum(item.get("imported", 0) for item in rescan_results)
        duplicates = sum(item.get("duplicates", 0) for item in rescan_results)
        found = sum(item.get("found", 0) for item in rescan_results)
        result = {
            "success": len(failed_details) == 0,
            "total": len(operation.email_ids),
            "updated": processed,
            "failed": len(failed_details),
            "failed_details": failed_details or None,
        }
        message = (
            f"重新扫描完成：处理 {processed} 封，发现 {found} 个 PDF，"
            f"新增 {imported} 张，重复 {duplicates} 张，失败 {len(failed_details)} 封"
        )
        
    elif operation.operation == "delete":
        result = email_service.delete_emails(
            user_id=current_user.id,
            email_ids=operation.email_ids
        )
        message = f"删除 {result.get('deleted', 0)} 封邮件记录"
        
    else:
        raise HTTPException(status_code=400, detail="不支持的操作类型")
    
    return EmailBatchOperationResponse(
        success=result["success"],
        total=result["total"],
        processed=result.get("updated", result.get("deleted", 0)),
        failed=result["failed"],
        failed_details=result.get("failed_details"),
        message=message
    )


@router.get("/status/options")
def get_status_options():
    """获取状态选项"""
    return {
        "invoice_scan_status": [
            {"value": "pending", "label": "待扫描"},
            {"value": "no_invoice", "label": "无发票"},
            {"value": "has_invoice", "label": "有发票"}
        ],
        "processing_status": [
            {"value": "unprocessed", "label": "未处理"},
            {"value": "processing", "label": "处理中"},
            {"value": "completed", "label": "已完成"},
            {"value": "failed", "label": "处理失败"}
        ]
    }
