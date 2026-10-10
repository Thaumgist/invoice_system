import logging
import subprocess

from celery.exceptions import SoftTimeLimitExceeded

from app.core.database import SessionLocal
from app.models.reimbursement import ReimbursementJob
from app.services.reimbursement_service import extract_invoice_numbers, source_path
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(soft_time_limit=180, time_limit=210)
def recognize_reimbursement_numbers(job_id, user_id):
    path = source_path(user_id, job_id)
    with SessionLocal() as db:
        claimed = db.query(ReimbursementJob).filter(
            ReimbursementJob.id == job_id, ReimbursementJob.user_id == user_id,
            ReimbursementJob.status == "pending",
        ).update({"status": "processing"})
        db.commit()
        if not claimed:
            return
        job = db.query(ReimbursementJob).filter(
            ReimbursementJob.id == job_id, ReimbursementJob.user_id == user_id,
        ).first()
        if job is None:
            return
        try:

            def progress(completed, total):
                job.completed_pages = completed
                job.page_count = total
                db.commit()

            job.numbers, job.page_count = extract_invoice_numbers(str(path), progress)
            job.status = "completed"
            job.error_message = None
            db.commit()
        except Exception as exc:
            db.rollback()
            job.status = "failed"
            if isinstance(exc, (subprocess.TimeoutExpired, SoftTimeLimitExceeded)):
                job.error_message = "票号识别超时，请拆分报销单后重试"
            elif isinstance(exc, ValueError):
                job.error_message = str(exc)
            else:
                job.error_message = "报销单识别失败，请检查 PDF 文件后重新上传"
            db.commit()
            logger.warning("Reimbursement OCR failed: job=%s type=%s", job_id, type(exc).__name__)
        finally:
            if job.status != "completed":
                path.unlink(missing_ok=True)
