"""
邮件列表服务
提供邮件列表查询、管理和发票检测状态跟踪功能
"""

from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc, func
from typing import List, Optional, Tuple, Dict, Any
from datetime import datetime, timedelta
from html import unescape
from urllib.parse import unquote, urlparse
import logging
import os
import re

from app.models.email import Email
from app.models.invoice import Invoice
from app.services.logging_service import logging_service

logger = logging.getLogger(__name__)


class EmailListService:
    """邮件列表服务类"""
    
    def __init__(self, db: Session):
        self.db = db

    def _extract_related_invoice_refs(self, email: Email) -> Tuple[List[str], List[str]]:
        invoice_ids: List[str] = []
        filenames: List[str] = []

        def add_id(value: Any) -> None:
            if value:
                text = str(value)
                if text not in invoice_ids:
                    invoice_ids.append(text)

        def add_filename(value: Any) -> None:
            if not value:
                return
            name = os.path.basename(str(value).strip())
            if name and name not in filenames:
                filenames.append(name)

        scan_result = email.scan_result or {}
        if isinstance(scan_result, dict):
            for item in scan_result.get("files") or []:
                if not isinstance(item, dict):
                    continue
                add_id(item.get("invoice_id"))
                add_id(item.get("existing_invoice_id"))
                add_filename(item.get("filename"))

        for item in email.attachment_info or []:
            if isinstance(item, dict):
                filename = item.get("filename")
                add_filename(filename)
                if filename and str(filename).lower().endswith(".zip"):
                    stem = os.path.splitext(os.path.basename(str(filename)))[0]
                    add_filename(f"{stem}__{stem}.pdf")

        body = unescape(f"{email.body_text or ''} {email.body_html or ''}")
        raw_urls = re.findall(r"https?://[^\s<>\"'{}|\\^`\[\]]+", body, re.IGNORECASE)
        for raw_url in raw_urls:
            try:
                parsed = urlparse(raw_url.strip().rstrip(").,;"))
            except Exception:
                continue
            if parsed.path.lower().endswith(".pdf"):
                add_filename(unquote(os.path.basename(parsed.path)))

        return invoice_ids, filenames

    def _attach_related_invoices(self, user_id: int, emails: List[Email]) -> None:
        if not emails:
            return

        refs_by_email: Dict[str, Tuple[List[str], List[str]]] = {}
        all_invoice_ids: List[str] = []
        all_filenames: List[str] = []

        for email in emails:
            invoice_ids, filenames = self._extract_related_invoice_refs(email)
            refs_by_email[email.id] = (invoice_ids, filenames)
            for invoice_id in invoice_ids:
                if invoice_id not in all_invoice_ids:
                    all_invoice_ids.append(invoice_id)
            for filename in filenames:
                if filename not in all_filenames:
                    all_filenames.append(filename)

        if not all_invoice_ids and not all_filenames:
            for email in emails:
                email.related_invoices = []
            return

        query = self.db.query(Invoice).filter(Invoice.user_id == user_id)
        match_clauses = []
        if all_invoice_ids:
            match_clauses.append(Invoice.id.in_(all_invoice_ids))
        if all_filenames:
            match_clauses.append(Invoice.original_filename.in_(all_filenames))
        invoices = query.filter(or_(*match_clauses)).all()

        invoices_by_id = {invoice.id: invoice for invoice in invoices}
        invoices_by_filename: Dict[str, List[Invoice]] = {}
        for invoice in invoices:
            invoices_by_filename.setdefault(invoice.original_filename, []).append(invoice)

        for email in emails:
            invoice_ids, filenames = refs_by_email.get(email.id, ([], []))
            related: List[Invoice] = []
            seen_ids = set()
            for invoice_id in invoice_ids:
                invoice = invoices_by_id.get(invoice_id)
                if invoice and invoice.id not in seen_ids:
                    related.append(invoice)
                    seen_ids.add(invoice.id)
            for filename in filenames:
                for invoice in invoices_by_filename.get(filename, []):
                    if invoice.id not in seen_ids:
                        related.append(invoice)
                        seen_ids.add(invoice.id)
            email.related_invoices = related

    def _normalize_email_data(self, email_data: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(email_data)
        length_limits = {
            "message_id": 255,
            "subject": 500,
            "sender": 255,
            "recipient": 255,
        }
        for key, max_length in length_limits.items():
            value = normalized.get(key)
            if value is None:
                continue
            value = str(value).strip()
            if len(value) > max_length:
                value = value[: max_length - 3] + "..."
            normalized[key] = value
        return normalized
    
    def create_or_update_email(
        self, 
        user_id: int, 
        message_id: str, 
        email_data: Dict[str, Any]
    ) -> Email:
        """创建或更新邮件记录"""
        try:
            message_id = str(message_id).strip()
            if len(message_id) > 255:
                message_id = message_id[:252] + "..."
            email_data = self._normalize_email_data(email_data)

            # 查找是否已存在
            existing_email = self.db.query(Email).filter(
                and_(
                    Email.user_id == user_id,
                    Email.message_id == message_id
                )
            ).first()
            
            if existing_email:
                # 更新现有记录
                for key, value in email_data.items():
                    if hasattr(existing_email, key):
                        setattr(existing_email, key, value)
                existing_email.updated_at = datetime.now()
                
                self.db.commit()
                self.db.refresh(existing_email)
                
                # 降噪：邮件记录更新不再入库
                
                return existing_email
            else:
                # 创建新记录
                email = Email(
                    user_id=user_id,
                    message_id=message_id,
                    **email_data
                )
                
                self.db.add(email)
                self.db.commit()
                self.db.refresh(email)
                
                # 降噪：邮件记录创建不再入库
                
                return email
                
        except Exception as e:
            self.db.rollback()
            logger.error(f"创建/更新邮件记录失败: {str(e)}")
            raise
    
    def get_emails(
        self, 
        user_id: int, 
        page: int = 1, 
        size: int = 20,
        filters: Optional[Dict[str, Any]] = None
    ) -> Tuple[List[Email], int]:
        """获取邮件列表"""
        try:
            query = self.db.query(Email).filter(Email.user_id == user_id)
            
            # 应用筛选条件
            if filters:
                # 发票扫描状态筛选
                if filters.get('invoice_scan_status'):
                    query = query.filter(Email.invoice_scan_status == filters['invoice_scan_status'])
                
                # 处理状态筛选
                if filters.get('processing_status'):
                    query = query.filter(Email.processing_status == filters['processing_status'])
                
                # 发送者筛选
                if filters.get('sender'):
                    query = query.filter(Email.sender.ilike(f"%{filters['sender']}%"))
                
                # 主题筛选
                if filters.get('subject'):
                    query = query.filter(Email.subject.ilike(f"%{filters['subject']}%"))
                
                # 是否有附件筛选
                if filters.get('has_attachments') is not None:
                    query = query.filter(Email.has_attachments == filters['has_attachments'])
                
                # 日期范围筛选
                if filters.get('date_from'):
                    query = query.filter(Email.date_sent >= filters['date_from'])
                
                if filters.get('date_to'):
                    query = query.filter(Email.date_sent <= filters['date_to'])
                
                # 是否检测到发票筛选
                if filters.get('has_invoice') is not None:
                    if filters['has_invoice']:
                        query = query.filter(Email.invoice_count > 0)
                    else:
                        query = query.filter(Email.invoice_count == 0)
            
            # 计算总数
            total = query.count()
            
            # 应用分页和排序
            emails = query.order_by(desc(Email.date_sent)).offset(
                (page - 1) * size
            ).limit(size).all()
            self._attach_related_invoices(user_id, emails)
            
            return emails, total
            
        except Exception as e:
            logger.error(f"获取邮件列表失败: {str(e)}")
            raise
    
    def get_email_detail(self, email_id: str, user_id: int) -> Optional[Email]:
        """获取邮件详情"""
        email = self.db.query(Email).filter(
            and_(Email.id == email_id, Email.user_id == user_id)
        ).first()
        if email:
            self._attach_related_invoices(user_id, [email])
        return email
    
    def update_scan_status(
        self, 
        email_id: str, 
        user_id: int, 
        scan_status: str, 
        invoice_count: int = 0,
        scan_result: Optional[Dict[str, Any]] = None
    ) -> bool:
        """更新邮件的发票扫描状态"""
        try:
            email = self.get_email_detail(email_id, user_id)
            if not email:
                return False
            
            old_status = email.invoice_scan_status
            old_count = email.invoice_count
            
            email.invoice_scan_status = scan_status
            email.invoice_count = invoice_count
            email.scanned_at = datetime.now()
            email.updated_at = datetime.now()
            # 同步更新处理状态闭环：无论有无发票，只要扫描完成即 completed；若传入失败则交由上层传递
            if scan_status in ("has_invoice", "no_invoice", "completed"):
                email.processing_status = "completed"
            
            if scan_result:
                email.scan_result = scan_result
            
            self.db.commit()
            
            # 降噪：邮件扫描状态更新不再入库
            
            return True
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"更新邮件扫描状态失败: {str(e)}")
            return False
    
    def get_email_statistics(self, user_id: int, days: int = 30) -> Dict[str, Any]:
        """获取邮件统计信息"""
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            
            # 基础查询
            base_query = self.db.query(Email).filter(
                and_(
                    Email.user_id == user_id,
                    Email.created_at >= start_date
                )
            )
            
            # 总邮件数
            total_emails = base_query.count()
            
            # 按扫描状态统计
            scan_status_stats = self.db.query(
                Email.invoice_scan_status,
                func.count(Email.id).label('count')
            ).filter(
                and_(
                    Email.user_id == user_id,
                    Email.created_at >= start_date
                )
            ).group_by(Email.invoice_scan_status).all()
            
            # 按处理状态统计
            processing_status_stats = self.db.query(
                Email.processing_status,
                func.count(Email.id).label('count')
            ).filter(
                and_(
                    Email.user_id == user_id,
                    Email.created_at >= start_date
                )
            ).group_by(Email.processing_status).all()
            
            # 有附件的邮件数
            emails_with_attachments = base_query.filter(Email.has_attachments == True).count()
            
            # 检测到发票的邮件数
            emails_with_invoices = base_query.filter(Email.invoice_count > 0).count()
            
            # 总发票数
            total_invoices = self.db.query(func.sum(Email.invoice_count)).filter(
                and_(
                    Email.user_id == user_id,
                    Email.created_at >= start_date
                )
            ).scalar() or 0
            
            # 构建统计结果
            statistics = {
                "period_days": days,
                "total_emails": total_emails,
                "emails_with_attachments": emails_with_attachments,
                "emails_with_invoices": emails_with_invoices,
                "emails_without_invoices": total_emails - emails_with_invoices,
                "total_invoices_found": int(total_invoices),
                "scan_status_breakdown": {
                    status: count for status, count in scan_status_stats
                },
                "processing_status_breakdown": {
                    status: count for status, count in processing_status_stats
                },
                "attachment_rate": round(emails_with_attachments / total_emails * 100, 2) if total_emails > 0 else 0,
                "invoice_detection_rate": round(emails_with_invoices / total_emails * 100, 2) if total_emails > 0 else 0
            }
            
            # 降噪：生成统计信息不再写库
            
            return statistics
            
        except Exception as e:
            logger.error(f"获取邮件统计失败: {str(e)}")
            return {
                "period_days": days,
                "error": "统计生成失败",
                "total_emails": 0
            }
    
    def mark_emails_for_rescan(self, user_id: int, email_ids: List[str]) -> Dict[str, Any]:
        """标记邮件重新扫描"""
        try:
            updated_count = 0
            failed_updates = []
            
            for email_id in email_ids:
                try:
                    email = self.get_email_detail(email_id, user_id)
                    if email:
                        email.invoice_scan_status = "pending"
                        email.processing_status = "unprocessed"
                        email.scan_result = None
                        email.invoice_count = 0
                        email.updated_at = datetime.now()
                        updated_count += 1
                    else:
                        failed_updates.append({
                            "email_id": email_id,
                            "reason": "email_not_found"
                        })
                except Exception as e:
                    failed_updates.append({
                        "email_id": email_id,
                        "reason": str(e)
                    })
            
            self.db.commit()
            
            # 降噪：标记重新扫描不再入库
            
            return {
                "success": True,
                "total": len(email_ids),
                "updated": updated_count,
                "failed": len(failed_updates),
                "failed_details": failed_updates
            }
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"标记邮件重新扫描失败: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "total": len(email_ids),
                "updated": 0
            }
    
    def delete_emails(self, user_id: int, email_ids: List[str]) -> Dict[str, Any]:
        """删除邮件记录"""
        try:
            deleted_count = 0
            failed_deletes = []
            
            for email_id in email_ids:
                try:
                    email = self.get_email_detail(email_id, user_id)
                    if email:
                        self.db.delete(email)
                        deleted_count += 1
                    else:
                        failed_deletes.append({
                            "email_id": email_id,
                            "reason": "email_not_found"
                        })
                except Exception as e:
                    failed_deletes.append({
                        "email_id": email_id,
                        "reason": str(e)
                    })
            
            self.db.commit()
            
            # 降噪：删除操作不再入库
            
            return {
                "success": True,
                "total": len(email_ids),
                "deleted": deleted_count,
                "failed": len(failed_deletes),
                "failed_details": failed_deletes
            }
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"删除邮件记录失败: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "total": len(email_ids),
                "deleted": 0
            }
