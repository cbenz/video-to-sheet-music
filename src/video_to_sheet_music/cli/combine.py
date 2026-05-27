from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ..combine import (
    A4_WIDTH_PT,
    A4_HEIGHT_PT,
    list_input_images,
    write_pdf,
)
from ..utils import log


def build_parser(
    parser: argparse.ArgumentParser | None = None,
) -> argparse.ArgumentParser:
    if parser is None:
        parser = argparse.ArgumentParser(
            description="Combine PNG images into an A4 portrait PDF, "
            "packing them vertically with homogeneous margins."
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
        "--side-margin-cm",
        type=float,
        default=1.0,
        help="Left and right page margin in cm (default: 1.0)",
    )
    parser.add_argument(
        "--margin-cm",
        type=float,
        default=1.0,
        help="Top/bottom margin and gap between images in cm (default: 1.0, minimum: 1.0)",
    )
    parser.add_argument(
        "--title-height-cm",
        type=float,
        default=0.0,
        help="Reserve blank space at top of first page for a title, in cm (default: 0)",
    )
    parser.add_argument(
        "--title-text",
        type=str,
        default=None,
        help="Title text to write at top of first page",
    )
    parser.add_argument(
        "--no-page-numbers",
        action="store_true",
        help="Disable page number rendering",
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
    if args.margin_cm < 1.0:
        print("Error: --margin-cm must be >= 1.0", file=sys.stderr)
        return 2
    if args.title_height_cm < 0:
        print("Error: --title-height-cm must be >= 0", file=sys.stderr)
        return 2

    log(f"Input images: {len(images)}")
    log(f"Page size: {A4_WIDTH_PT:.1f}x{A4_HEIGHT_PT:.1f}pt (A4)")
    log(f"Side margin: {args.side_margin_cm} cm")
    log(f"Margin (top/bottom/gap): {args.margin_cm} cm")
    if args.title_height_cm > 0:
        log(f"Title height: {args.title_height_cm} cm")
    if args.title_text:
        log(f"Title text: {args.title_text}")
    log(f"Page numbers: {'off' if args.no_page_numbers else 'on'}")

    try:
        if args.dry_run:
            log(f"[dry-run] write PDF to {args.output}")
        else:
            write_pdf(
                images,
                args.output,
                args.side_margin_cm,
                args.margin_cm,
                args.title_height_cm,
                args.title_text,
                not args.no_page_numbers,
            )
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1

    log("")
    log("Summary")
    log(f"- Images in: {len(images)}")
    log(f"- Output: {args.output}")
    log("- Format: pdf")
    log("- Engine: reportlab")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
