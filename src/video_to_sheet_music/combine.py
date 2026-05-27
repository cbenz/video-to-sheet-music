from __future__ import annotations

import re
from pathlib import Path

from reportlab.lib.pagesizes import A4, portrait
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

A4_WIDTH_PT, A4_HEIGHT_PT = portrait(A4)
PAGE_NUMBER_BOTTOM_CM = 0.6
TITLE_FONT_SIZE_PT = 18
TITLE_FONT = "Helvetica-Bold"


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


def _draw_image(
    pdf: canvas.Canvas,
    image_path: Path,
    x: float,
    y: float,
    width: float,
    height: float,
) -> None:
    pdf.drawImage(  # pyright: ignore[reportUnknownMemberType, reportUnusedCallResult]
        str(image_path),
        x,
        y,
        width=width,
        height=height,
        preserveAspectRatio=False,
        mask="auto",
    )


def _pack_pages(
    images: list[Path],
    content_w: float,
    page_h: float,
    margin_pt: float,
    title_height_pt: float,
) -> list[list[Path]]:
    """Pack images into pages. Margin applies to top, bottom and between images."""
    pages: list[list[Path]] = []
    current_page: list[Path] = []
    available_h = page_h - 2 * margin_pt

    for img_path in images:
        w_px, h_px = get_image_size_pixels(img_path)
        img_h = content_w * h_px / w_px if w_px > 0 else 0

        first_page_reserved = title_height_pt if len(pages) == 0 else 0
        usable_h = available_h - first_page_reserved

        n_in_page = len(current_page)
        needed = img_h + (margin_pt if n_in_page > 0 else 0)

        if (
            n_in_page == 0
            or _cumulative_height(current_page, content_w, margin_pt) + needed
            <= usable_h
        ):
            current_page.append(img_path)
        else:
            if current_page:
                pages.append(current_page)
            current_page = [img_path]

    if current_page:
        pages.append(current_page)

    return pages


def _cumulative_height(images: list[Path], content_w: float, gap_pt: float) -> float:
    """Total height of images (scaled to content_w) plus gaps between them."""
    if not images:
        return 0.0
    total = 0.0
    for p in images:
        w_px, h_px = get_image_size_pixels(p)
        total += content_w * h_px / w_px if w_px > 0 else 0
    total += gap_pt * (len(images) - 1)
    return total


def write_pdf(
    images: list[Path],
    output_pdf: Path,
    side_margin_cm: float,
    margin_cm: float,
    title_height_cm: float,
    title_text: str | None,
    add_page_numbers: bool,
) -> None:
    """Generate an A4 portrait PDF, packing images vertically."""
    page_w, page_h = A4_WIDTH_PT, A4_HEIGHT_PT
    side_margin_pt = cm_to_pt(side_margin_cm)
    margin_pt = cm_to_pt(margin_cm)
    title_height_pt = cm_to_pt(title_height_cm)
    if title_text:
        title_height_pt = max(title_height_pt, cm_to_pt(1.0))
    content_w = max(1.0, page_w - (2 * side_margin_pt))
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    pdf = canvas.Canvas(str(output_pdf), pagesize=(page_w, page_h), pageCompression=1)

    try:
        pages = _pack_pages(
            images,
            content_w,
            page_h,
            margin_pt,
            title_height_pt,
        )
        for page_idx, page_images in enumerate(pages):
            page_num = page_idx + 1
            _draw_pdf_page(
                pdf,
                page_images,
                page_w,
                page_h,
                content_w,
                margin_pt,
                side_margin_pt,
                title_height_pt if page_idx == 0 else 0,
                title_text if page_idx == 0 else None,
                add_page_numbers,
                page_num,
            )
            pdf.showPage()
    finally:
        pdf.save()


def _draw_pdf_page(
    pdf: canvas.Canvas,
    images: list[Path],
    page_w: float,
    page_h: float,
    content_w: float,
    margin_pt: float,
    side_margin_pt: float,
    title_height_pt: float,
    title_text: str | None,
    add_page_numbers: bool,
    page_num: int,
) -> None:
    """Draw a single page with images stacked vertically."""
    available_h = page_h - 2 * margin_pt - title_height_pt

    heights: list[float] = []
    total_h = 0.0
    for p in images:
        w_px, h_px = get_image_size_pixels(p)
        h = content_w * h_px / w_px if w_px > 0 else 0
        heights.append(h)
        total_h += h
    total_h += margin_pt * (len(images) - 1)

    # Center the block vertically in available space
    y_start = margin_pt + title_height_pt + (available_h - total_h) / 2.0

    # Title
    if title_text:
        pdf.setFont(TITLE_FONT, TITLE_FONT_SIZE_PT)
        title_y = page_h - margin_pt - TITLE_FONT_SIZE_PT
        pdf.drawCentredString(page_w / 2.0, title_y, title_text)

    # Draw images from top to bottom (PDF y=0 is bottom)
    y = page_h - y_start
    for i, p in enumerate(images):
        y -= heights[i]
        _draw_image(pdf, p, side_margin_pt, y, content_w, heights[i])
        y -= margin_pt

    if add_page_numbers:
        pdf.setFont("Helvetica", 10)
        pdf.drawCentredString(
            page_w / 2.0,
            cm_to_pt(PAGE_NUMBER_BOTTOM_CM),
            str(page_num),
        )
