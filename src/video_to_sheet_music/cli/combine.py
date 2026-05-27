from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

from ..combine import (
    A4_WIDTH_PT,
    A4_HEIGHT_PT,
    chunk_size_for_layout,
    list_input_images,
    write_pdf,
)
from ..utils import log


def build_parser(
    parser: argparse.ArgumentParser | None = None,
) -> argparse.ArgumentParser:
    if parser is None:
        parser = argparse.ArgumentParser(
            description="Combine PNG images into an A4 portrait PDF, 2 images/page by default."
        )
    parser.add_argument(
        "input",
        type=Path,
        help="Input directory containing PNG files (or a single PNG file)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("output.pdf"),
        help="Output PDF path (default: output.pdf)",
    )
    parser.add_argument(
        "--pattern",
        type=str,
        default="*.png",
        help="Glob pattern when input is a directory (default: *.png)",
    )
    parser.add_argument(
        "--layout",
        choices=["1x2", "2x1", "1x1"],
        default="1x2",
        help="Page layout on A4 portrait (default: 1x2)",
    )
    parser.add_argument(
        "--side-margin-cm",
        type=float,
        default=1.0,
        help="Left and right page margin in cm (default: 1.0)",
    )
    parser.add_argument(
        "--no-page-numbers",
        action="store_true",
        help="Disable page number rendering in the generated PDF",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print commands only")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        images = list_input_images(args.input, args.pattern)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    if not images:
        print("Error: no PNG input files found", file=sys.stderr)
        return 2

    if args.side_margin_cm < 0:
        print("Error: --side-margin-cm must be >= 0", file=sys.stderr)
        return 2
    per_page = chunk_size_for_layout(args.layout)
    page_count = math.ceil(len(images) / per_page)

    log(f"Input images: {len(images)}")
    log(f"Layout: {args.layout} ({per_page} image(s)/page)")
    log(f"Page size: {A4_WIDTH_PT:.1f}x{A4_HEIGHT_PT:.1f}pt (A4)")
    log(f"Side margin: {args.side_margin_cm} cm")
    log(f"Page numbers: {'off' if args.no_page_numbers else 'on'}")
    log(f"Expected pages: {page_count}")
    log("PDF engine: reportlab")

    try:
        if args.dry_run:
            log(f"[dry-run] write PDF to {args.output}")
        else:
            write_pdf(
                images,
                args.output,
                args.layout,
                args.side_margin_cm,
                not args.no_page_numbers,
            )
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1

    log("")
    log("Summary")
    log(f"- Images in: {len(images)}")
    log(f"- PDF pages: {page_count}")
    log(f"- Output PDF: {args.output}")
    log("- Engine used: reportlab")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
