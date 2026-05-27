from __future__ import annotations

import math
import re
from pathlib import Path

from reportlab.lib.pagesizes import A4, portrait
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from .utils import log

A4_WIDTH_PT, A4_HEIGHT_PT = portrait(A4)
TOP_MARGIN_CM = 1.0
SINGLE_IMAGE_TOP_MARGIN_CM = 2.0
PAGE_NUMBER_BOTTOM_CM = 0.6


def list_input_images(input_path: Path, pattern: str) -> list[Path]:
    if input_path.is_file():
        if input_path.suffix.lower() != ".png":
            raise RuntimeError(f"Input file is not PNG: {input_path}")
        return [input_path]

    if not input_path.is_dir():
        raise RuntimeError(f"Input path not found: {input_path}")

    def key(path: Path) -> tuple[str, int]:
        m = re.search(r"(\d+)", path.stem)
        return (path.stem, int(m.group(1)) if m else -1)

    return sorted(input_path.glob(pattern), key=key)


def cm_to_pt(cm: float) -> float:
    return (cm / 2.54) * 72.0


def get_image_size_pixels(path: Path) -> tuple[int, int]:
    return ImageReader(str(path)).getSize()


def fit_size(
    src_w: float, src_h: float, max_w: float, max_h: float
) -> tuple[float, float]:
    scale = min(max_w / src_w, max_h / src_h)
    return src_w * scale, src_h * scale


def chunk_size_for_layout(layout: str) -> int:
    if layout in {"1x2", "2x1"}:
        return 2
    return 1


def write_pdf(
    images: list[Path],
    output_pdf: Path,
    layout: str,
    side_margin_cm: float,
    add_page_numbers: bool,
) -> None:
    page_w, page_h = A4_WIDTH_PT, A4_HEIGHT_PT
    side_margin_pt = cm_to_pt(side_margin_cm)
    top_margin_pt = cm_to_pt(TOP_MARGIN_CM)
    single_image_top_margin_pt = cm_to_pt(SINGLE_IMAGE_TOP_MARGIN_CM)
    content_w = max(1.0, page_w - (2 * side_margin_pt))
    per_page = chunk_size_for_layout(layout)
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    pdf = canvas.Canvas(str(output_pdf), pagesize=(page_w, page_h), pageCompression=1)

    try:
        for idx in range(0, len(images), per_page):
            batch = images[idx : idx + per_page]
            page_num = (idx // per_page) + 1

            if layout == "1x2":
                if len(batch) == 2:
                    w1_px, h1_px = get_image_size_pixels(batch[0])
                    w2_px, h2_px = get_image_size_pixels(batch[1])
                    h1 = content_w * h1_px / w1_px
                    h2 = content_w * h2_px / w2_px
                    gap = max(top_margin_pt, (page_h - h1 - h2) / 3.0)
                    pdf.drawImage(
                        str(batch[0]),
                        side_margin_pt,
                        page_h - gap - h1,
                        width=content_w,
                        height=h1,
                        preserveAspectRatio=False,
                        mask="auto",
                    )
                    pdf.drawImage(
                        str(batch[1]),
                        side_margin_pt,
                        gap,
                        width=content_w,
                        height=h2,
                        preserveAspectRatio=False,
                        mask="auto",
                    )
                else:
                    w_px, h_px = get_image_size_pixels(batch[0])
                    height = content_w * h_px / w_px
                    y = page_h - single_image_top_margin_pt - height
                    pdf.drawImage(
                        str(batch[0]),
                        side_margin_pt,
                        y,
                        width=content_w,
                        height=height,
                        preserveAspectRatio=False,
                        mask="auto",
                    )
            elif layout == "2x1":
                slot_w = content_w / 2.0
                if len(batch) == 2:
                    w1_px, h1_px = get_image_size_pixels(batch[0])
                    w2_px, h2_px = get_image_size_pixels(batch[1])
                    w1, h1 = fit_size(w1_px, h1_px, slot_w, page_h)
                    w2, h2 = fit_size(w2_px, h2_px, slot_w, page_h)
                    gap = max(0.0, (content_w - w1 - w2) / 3.0)
                    pdf.drawImage(
                        str(batch[0]),
                        side_margin_pt + gap,
                        (page_h - h1) / 2.0,
                        width=w1,
                        height=h1,
                        preserveAspectRatio=False,
                        mask="auto",
                    )
                    pdf.drawImage(
                        str(batch[1]),
                        side_margin_pt + (2.0 * gap) + w1,
                        (page_h - h2) / 2.0,
                        width=w2,
                        height=h2,
                        preserveAspectRatio=False,
                        mask="auto",
                    )
                else:
                    w_px, h_px = get_image_size_pixels(batch[0])
                    width, height = fit_size(w_px, h_px, content_w, page_h)
                    pdf.drawImage(
                        str(batch[0]),
                        side_margin_pt + (content_w - width) / 2.0,
                        (page_h - height) / 2.0,
                        width=width,
                        height=height,
                        preserveAspectRatio=False,
                        mask="auto",
                    )
            else:
                w_px, h_px = get_image_size_pixels(batch[0])
                width, height = fit_size(w_px, h_px, content_w, page_h)
                pdf.drawImage(
                    str(batch[0]),
                    side_margin_pt + (content_w - width) / 2.0,
                    (page_h - height) / 2.0,
                    width=width,
                    height=height,
                    preserveAspectRatio=False,
                    mask="auto",
                )

            if add_page_numbers:
                pdf.setFont("Helvetica", 10)
                pdf.drawCentredString(
                    page_w / 2.0,
                    cm_to_pt(PAGE_NUMBER_BOTTOM_CM),
                    str(page_num),
                )

            pdf.showPage()
    finally:
        pdf.save()
