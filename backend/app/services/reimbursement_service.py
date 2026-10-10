import csv
import io
import os
from decimal import Decimal
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time

import fitz

from app.core.config import settings
from app.models.invoice import Invoice


NUMBER_PATTERN = re.compile(r"(?<![0-9])(?:[0-9]{20}|[0-9]{8})(?![0-9])")


def normalize_invoice_numbers(values):
    numbers = []
    for value in values:
        number = value.strip()
        if not re.fullmatch(r"[0-9]{20}|[0-9]{8}", number):
            raise ValueError("发票号码必须是 8 位或 20 位数字")
        if number not in numbers:
            numbers.append(number)
    return numbers


def match_invoice_numbers(db, user_id, numbers):
    numbers = normalize_invoice_numbers(numbers)
    invoices = db.query(Invoice).filter(
        Invoice.user_id == user_id,
        Invoice.invoice_num.in_(numbers),
    ).order_by(Invoice.created_at, Invoice.id).all() if numbers else []
    grouped = {number: [] for number in numbers}
    for invoice in invoices:
        grouped[invoice.invoice_num].append(invoice)
    return [{
        "invoice_num": number,
        "status": "not_found" if not grouped[number] else "matched" if len(grouped[number]) == 1 else "ambiguous",
        "invoices": grouped[number],
    } for number in numbers]


def amount_to_cents(value):
    return int((value * 100).quantize(Decimal("1")))


def find_exact_amount_solution(invoices, target_amount):
    target = amount_to_cents(target_amount)
    if target == 0:
        return {"invoices": [], "total_amount": Decimal("0.00")}
    candidates = []
    for invoice in invoices:
        amount = invoice.amount_in_figures if invoice.amount_in_figures is not None else invoice.total_amount
        if amount is None:
            continue
        cents = amount_to_cents(Decimal(str(amount)))
        if cents > 0 and cents <= target:
            candidates.append((invoice, cents))
    dp = {0: None}
    for index, (invoice, cents) in enumerate(candidates):
        for current in sorted(tuple(dp.keys()), reverse=True):
            next_total = current + cents
            if next_total <= target and next_total not in dp:
                dp[next_total] = (dp[current], index)
                if len(dp) > 250_000:
                    raise ValueError("金额组合搜索范围过大，请缩小候选发票范围")
        if target in dp:
            break
    if target not in dp:
        return None
    selected_indexes = []
    node = dp[target]
    while node is not None:
        previous, index = node
        selected_indexes.append(index)
        node = previous
    chosen = [candidates[index][0] for index in reversed(selected_indexes)]
    return {
        "invoices": chosen,
        "total_amount": Decimal(target) / Decimal(100),
    }


def report_total_amount(report):
    return sum(
        (Decimal(str(invoice.amount_in_figures if invoice.amount_in_figures is not None else invoice.total_amount or 0)) for invoice in report.invoices),
        Decimal("0.00"),
    )


def report_response(report):
    return {
        "id": report.id,
        "name": report.name,
        "source_job_id": report.source_job_id,
        "file_available": bool(report.file_path and Path(report.file_path).is_file()),
        "invoice_count": len(report.invoices),
        "total_amount": report_total_amount(report),
        "invoices": report.invoices,
        "created_at": report.created_at,
        "updated_at": report.updated_at,
    }


def source_path(user_id, job_id):
    if not re.fullmatch(r"[0-9a-f-]{36}", job_id) or not isinstance(user_id, int) or user_id < 1:
        raise ValueError("无效的报销单任务")
    return Path(settings.UPLOAD_DIR) / "temp" / "reimbursements" / str(user_id) / f"{job_id}.pdf"


def parse_number_tsv(tsv, column_width=None):
    lines = {}
    for token in csv.DictReader(io.StringIO(tsv), delimiter="\t"):
        text = token.get("text", "").strip()
        if not text:
            continue
        key = tuple(token[field] for field in ("block_num", "par_num", "line_num"))
        lines.setdefault(key, []).append(token)
    results = []
    for tokens in lines.values():
        ordered = sorted(tokens, key=lambda token: int(token["left"]))
        if column_width is not None:
            left = int(ordered[0]["left"])
            right = max(int(token["left"]) + int(token["width"]) for token in ordered)
            if left > column_width * 0.08 or right >= column_width - 2:
                continue
        number = "".join(token["text"] for token in ordered)
        if re.fullmatch(r"[0-9]{20}|[0-9]{8}", number):
            confidence = min(float(token["conf"]) for token in ordered)
            results.append({"invoice_num": number, "confidence": max(0, confidence)})
    return results


def extract_invoice_numbers(file_path, on_progress=None):
    deadline = time.monotonic() + settings.REIMBURSEMENT_TIMEOUT
    extracted = {}
    with fitz.open(file_path) as document, tempfile.TemporaryDirectory(prefix="reimbursement-ocr-") as temporary:
        if document.needs_pass:
            raise ValueError("报销单 PDF 已加密，请上传未加密文件")
        if not 1 <= document.page_count <= settings.REIMBURSEMENT_MAX_PAGES:
            raise ValueError(f"报销单最多支持 {settings.REIMBURSEMENT_MAX_PAGES} 页")
        if on_progress:
            on_progress(0, document.page_count)
        for page_index, page in enumerate(document):
            if time.monotonic() >= deadline:
                raise ValueError("票号识别超时，请拆分报销单后重试")
            if (
                page.rect.width > page.rect.height
                or not 500 <= page.rect.width <= 650
                or not 700 <= page.rect.height <= 900
                or not 0.65 <= page.rect.width / page.rect.height <= 0.78
            ):
                raise ValueError("目前仅支持 A4 竖版浙大报销单，请核对页面方向和版式")
            region = fitz.Rect(page.rect.width * 0.202, page.rect.height * 0.035,
                               page.rect.width * 0.375, page.rect.height * 0.95)
            native_text = page.get_text("text", clip=region)
            full_text = page.get_text("text")
            words = page.get_text("words", clip=region)
            header = next((word for word in words if "发票号码" in word[4]), None)
            candidates = []
            if native_text.strip():
                for word in words:
                    if header and word[1] <= header[3]:
                        continue
                    if word[0] - region.x0 > region.width * 0.08:
                        continue
                    for number in NUMBER_PATTERN.findall(word[4]):
                        if len(number) == 8 and "发票号码" in full_text and not header:
                            continue
                        candidates.append({"invoice_num": number, "confidence": None, "source": "text"})
            else:
                if not shutil.which("tesseract"):
                    raise ValueError("识别服务未安装 Tesseract，请联系管理员")
                image_path = Path(temporary) / "numbers.png"
                pixmap = page.get_pixmap(matrix=fitz.Matrix(300 / 72, 300 / 72), colorspace=fitz.csGRAY, clip=region)
                pixmap.save(image_path)
                environment = {**os.environ, "OMP_THREAD_LIMIT": "1"}
                result = subprocess.run([
                    "tesseract", str(image_path), "stdout", "-l", "eng", "--psm", "6",
                    "-c", "tessedit_char_whitelist=0123456789", "tsv",
                ], capture_output=True, text=True, env=environment,
                    timeout=max(1, min(30, deadline - time.monotonic())))
                if result.returncode:
                    raise ValueError("本地票号识别失败，请核对 PDF 文件或重试")
                candidates = [{**candidate, "source": "ocr"} for candidate in parse_number_tsv(result.stdout, pixmap.width)]
            for candidate in candidates:
                number = candidate["invoice_num"]
                if number in extracted:
                    item = extracted[number]
                    item["occurrences"] += 1
                    if page_index + 1 not in item["pages"]:
                        item["pages"].append(page_index + 1)
                    if candidate["confidence"] is not None:
                        item["confidence"] = min(item["confidence"] if item["confidence"] is not None else 100, candidate["confidence"])
                else:
                    extracted[number] = {**candidate, "pages": [page_index + 1], "occurrences": 1}
                if len(extracted) > 500:
                    raise ValueError("票号数量超过 500 个，请拆分报销单")
            if on_progress:
                on_progress(page_index + 1, document.page_count)
        return list(extracted.values()), document.page_count
