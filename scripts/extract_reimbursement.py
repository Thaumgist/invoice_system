"""Local extraction prototype for ZJU reimbursement confirmation PDFs."""

import argparse
import csv
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

from PIL import Image, ImageOps


COLUMNS = {
    "invoice_code_raw": (0.051, 0.197),
    "invoice_num": (0.202, 0.375),
    "invoice_type": (0.377, 0.479),
    "invoice_date": (0.480, 0.584),
    "invoice_content": (0.586, 0.846),
    "invoice_amount": (0.848, 0.948),
}


def run(command):
    environment = {**os.environ, "OMP_THREAD_LIMIT": "1"}
    return subprocess.run(command, check=True, capture_output=True, env=environment).stdout.decode("utf-8")


def ocr(image_path, language="chi_sim", mode=6, whitelist=None, tsv=False):
    command = ["tesseract", str(image_path), "stdout", "-l", language, "--psm", str(mode)]
    if whitelist:
        command.extend(["-c", "tessedit_char_whitelist=" + whitelist])
    if tsv:
        command.append("tsv")
    return run(command).strip()


def crop_column(page_image, name, top, bottom):
    left, right = COLUMNS[name]
    cropped = page_image.crop((int(left * page_image.width), int(top), int(right * page_image.width), int(bottom)))
    return ImageOps.expand(cropped, border=12, fill="white")


def ocr_lines(image_path, mode=13):
    with Image.open(image_path) as source:
        image = source.convert("L")
    ink = image.point(lambda value: 255 if value < 160 else 0)
    occupied = [line for line in range(image.height) if ink.crop((0, line, image.width, line + 1)).getbbox()]
    groups = []
    for line in occupied:
        if not groups or line - groups[-1][-1] > 8:
            groups.append([])
        groups[-1].append(line)
    texts = []
    for index, group in enumerate(groups):
        if group[-1] - group[0] < 6:
            continue
        box = ink.crop((0, group[0], image.width, group[-1] + 1)).getbbox()
        segment = image.crop((box[0], group[0], box[2], group[-1] + 1))
        path = image_path.with_name(f"{image_path.stem}-line-{index}.png")
        ImageOps.expand(segment, border=12, fill="white").save(path)
        texts.append(ocr(path, mode=mode))
    return "\n".join(texts)


def inspect_pdf(input_path):
    text = run(["pdftotext", "-layout", str(input_path), "-"])
    result = {"source_file": input_path.name, "native_text_characters": len(text.strip())}
    try:
        import pikepdf
        with pikepdf.Pdf.open(input_path) as document:
            pages = []
            for page in document.pages:
                operators = [str(item.operator) for item in pikepdf.parse_content_stream(page)]
                pages.append({
                    "fonts": len(page.Resources.get("/Font", {})),
                    "text_operators": sum(operator in {"Tj", "TJ", "'", '"'} for operator in operators),
                    "path_operators": sum(operator in {"m", "l", "c", "f", "f*"} for operator in operators),
                })
            result.update({"pages": pages, "attachments": len(document.attachments)})
    except ImportError:
        result["structure_probe"] = "Install pikepdf for detailed content-stream inspection"
    return result


def number_anchors(page_image, directory):
    cropped = crop_column(page_image, "invoice_num", 0, page_image.height)
    path = directory / "number-column.png"
    cropped.save(path)
    result = ocr(path, language="eng", whitelist="0123456789", tsv=True)
    lines = {}
    for token in csv.DictReader(io.StringIO(result), delimiter="\t"):
        text = token.get("text", "").strip()
        if not text:
            continue
        key = tuple(token[field] for field in ("block_num", "par_num", "line_num"))
        lines.setdefault(key, []).append(token)
    anchors = []
    for tokens in lines.values():
        number = "".join(token["text"] for token in sorted(tokens, key=lambda token: int(token["left"])))
        if not re.fullmatch(r"\d{20}|\d{8}", number):
            continue
        top = min(int(token["top"]) for token in tokens) - 12
        bottom = max(int(token["top"]) + int(token["height"]) for token in tokens) - 12
        if not 0.035 * page_image.height < top < 0.95 * page_image.height:
            continue
        anchors.append({"number": number, "center": (top + bottom) / 2, "height": bottom - top})
    return sorted(anchors, key=lambda anchor: anchor["center"])


def extract_row(page_image, anchor, top, bottom, directory, page_number, row_index):
    raw = {}
    alternate_content = ""
    for name in COLUMNS:
        path = directory / f"row-{row_index:02d}-{name}.png"
        if name in ("invoice_num", "invoice_date", "invoice_amount", "invoice_code_raw"):
            field_top = anchor["center"] - anchor["height"] * 0.8
            field_bottom = anchor["center"] + anchor["height"] * 0.8
        else:
            field_top, field_bottom = top, bottom
        crop_column(page_image, name, field_top, field_bottom).save(path)
        if name in ("invoice_num", "invoice_date", "invoice_amount"):
            raw[name] = ocr(path, language="eng", mode=7, whitelist="0123456789.-")
        else:
            raw[name] = ocr_lines(path)
            if name == "invoice_content":
                alternate_content = ocr_lines(path, mode=7)
    number = re.sub(r"\s", "", raw["invoice_num"])
    invoice_date = re.sub(r"\s", "", raw["invoice_date"]).replace("—", "-").replace("–", "-")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", invoice_date):
        return None
    try:
        date.fromisoformat(invoice_date)
    except ValueError:
        return None
    invoice_type = re.sub(r"\s", "", raw["invoice_type"]).replace("（", "(").replace("）", ")")
    invoice_type = invoice_type.replace("〈", "(").replace("〉", ")")
    invoice_content = " ".join(raw["invoice_content"].splitlines()).strip()
    invoice_content = re.sub(r"(?<=[\u4e00-\u9fff]) +(?=[\u4e00-\u9fff])", "", invoice_content)
    amount_text = re.sub(r"\s", "", raw["invoice_amount"])
    amount = str(Decimal(amount_text).quantize(Decimal("0.01"))) if re.fullmatch(r"\d+(?:\.\d{1,2})?", amount_text) else None
    code_raw = re.sub(r"\s", "", raw["invoice_code_raw"])
    warnings = []
    if re.sub(r"\s", "", raw["invoice_content"]) != re.sub(r"\s", "", alternate_content):
        warnings.append("invoice_content_ocr_disagreement")
    if number != anchor["number"]:
        warnings.append("invoice_number_ocr_disagreement")
    if not re.fullmatch(r"\d{20}|\d{8}", number):
        warnings.append("invalid_invoice_number_length")
    if amount is None:
        warnings.append("invalid_amount")
    if not invoice_content:
        warnings.append("missing_content")
    if invoice_type not in ("电子发票(普通发票)", "电子发票(铁路电子客票)"):
        warnings.append("unrecognized_invoice_type")
    if code_raw != "数电票" and not re.fullmatch(r"\d{10}|\d{12}", code_raw):
        warnings.append("unrecognized_invoice_code_label")
    return {
        "page": page_number,
        "row_on_page": row_index,
        "invoice_code": code_raw if re.fullmatch(r"\d{10}|\d{12}", code_raw) else None,
        "invoice_code_raw": code_raw,
        "invoice_num": number,
        "invoice_type": invoice_type,
        "invoice_date": invoice_date,
        "invoice_content": invoice_content,
        "invoice_amount": amount,
        "warnings": warnings,
        "review_status": "unreviewed",
        "source_bbox_pixels": [int(0.048 * page_image.width), int(top), int(0.953 * page_image.width), int(bottom)],
        "raw_ocr": raw,
        "alternate_content_ocr": alternate_content,
    }


def extract_pdf(input_path, output_dir, work_dir):
    text = run(["pdftotext", "-layout", str(input_path), "-"])
    output_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)
    prefix = work_dir / "page"
    run(["pdftoppm", "-r", "300", "-gray", "-png", str(input_path), str(prefix)])
    rows = []
    page_counts = []
    candidate_counts = []
    images = sorted(work_dir.glob("page-*.png"), key=lambda path: int(path.stem.split("-")[-1]))
    for page_number, image_path in enumerate(images, start=1):
        directory = work_dir / f"page-{page_number}"
        directory.mkdir(exist_ok=True)
        with Image.open(image_path) as image:
            page_image = image.convert("L")
        anchors = number_anchors(page_image, directory)
        candidate_counts.append(len(anchors))
        candidates = []
        with ThreadPoolExecutor(max_workers=4) as executor:
            for index, anchor in enumerate(anchors):
                top = (anchors[index - 1]["center"] + anchor["center"]) / 2 if index else anchor["center"] - anchor["height"] * 2.7
                bottom = (anchors[index + 1]["center"] + anchor["center"]) / 2 if index + 1 < len(anchors) else anchor["center"] + anchor["height"] * 4.2
                candidates.append(executor.submit(extract_row, page_image, anchor, top, bottom, directory, page_number, index + 1))
            page_rows = [future.result() for future in candidates]
        page_counts.append(sum(row is not None for row in page_rows))
        rows.extend(row for row in page_rows if row is not None)
    total = sum((Decimal(row["invoice_amount"]) for row in rows if row["invoice_amount"] is not None), Decimal("0.00"))
    result = {
        "source_file": input_path.name,
        "method": "local_tesseract_column_ocr",
        "template": "zju_reimbursement_confirmation_a4_portrait",
        "native_text_characters": len(text.strip()),
        "page_count": len(page_counts),
        "rows_per_page": page_counts,
        "number_candidates_per_page": candidate_counts,
        "invoice_count": len(rows),
        "invoice_amount_sum": str(total.quantize(Decimal("0.01"))),
        "review_status": "unreviewed",
        "requires_human_review": True,
        "warnings": ["Template-specific prototype; unmatched rows and alternative layouts may be missed"],
        "invoices": rows,
    }
    destination = output_dir / input_path.stem
    destination.with_suffix(".json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    fields = ["page", "row_on_page", "invoice_code", "invoice_code_raw", "invoice_num", "invoice_type", "invoice_date", "invoice_content", "invoice_amount", "warnings", "review_status"]
    with destination.with_suffix(".csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, "warnings": ";".join(row["warnings"])})
    print(json.dumps({key: value for key, value in result.items() if key != "invoices"}, ensure_ascii=False))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path, nargs="+")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument("--probe-only", action="store_true")
    arguments = parser.parse_args()
    if arguments.probe_only:
        for input_path in arguments.pdf:
            print(json.dumps(inspect_pdf(input_path), ensure_ascii=False, indent=2))
        return
    if arguments.output_dir is None:
        parser.error("--output-dir is required for OCR extraction")
    with tempfile.TemporaryDirectory(prefix="reimbursement-") as temporary:
        base = arguments.work_dir or Path(temporary)
        for input_path in arguments.pdf:
            extract_pdf(input_path, arguments.output_dir, base / input_path.stem)


if __name__ == "__main__":
    main()
