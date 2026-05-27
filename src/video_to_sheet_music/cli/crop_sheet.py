"""CLI for ``crop-sheet`` subcommand."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ..crop_sheet import crop_to_sheet_music
from ..utils import list_pngs, log


def build_parser(
    parser: argparse.ArgumentParser | None = None,
) -> argparse.ArgumentParser:
    if parser is None:
        parser = argparse.ArgumentParser(
            description="Detect and crop the sheet-music region in split-screen frames."
        )
    parser.add_argument(
        "input_dir",
        type=Path,
        help="Directory containing extracted PNG frames",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=None,
        help=(
            "Directory for cropped PNGs (default: <input_dir>/cropped). "
            "Use '.' or the same as input_dir to overwrite in place."
        ),
    )
    parser.add_argument(
        "--min-staff-line-ratio",
        type=float,
        default=0.30,
        help="Min dark-run length as fraction of image width (default: 0.30)",
    )
    parser.add_argument(
        "--dark-threshold",
        type=int,
        default=128,
        help="Pixel value below which a pixel is considered dark, for both detection and margin expansion (default: 128)",
    )
    parser.add_argument(
        "--cluster-gap",
        type=int,
        default=20,
        help="Max vertical gap in px to stay in same staff cluster (default: 20)",
    )
    parser.add_argument(
        "--padding",
        type=int,
        default=10,
        help="Extra padding px around detected region (default: 10)",
    )
    parser.add_argument("--verbose", action="store_true", help="Verbose logs")
    parser.add_argument("--dry-run", action="store_true", help="Print actions only")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    input_dir: Path = args.input_dir
    if not input_dir.is_dir():
        print(f"Error: not a directory: {input_dir}", file=sys.stderr)
        return 2

    images = list_pngs(input_dir)
    if not images:
        print(f"No PNG images found in {input_dir}", file=sys.stderr)
        return 0

    output_dir: Path
    if args.output_dir is None:
        output_dir = input_dir / "cropped"
        in_place = False
    elif (
        str(args.output_dir) == "." or args.output_dir.resolve() == input_dir.resolve()
    ):
        output_dir = input_dir
        in_place = True
    else:
        output_dir = args.output_dir
        in_place = False

    if not in_place:
        output_dir.mkdir(parents=True, exist_ok=True)

    log(f"Input:  {input_dir} ({len(images)} PNGs)")
    log(f"Output: {output_dir}" + (" (in-place)" if in_place else ""))
    log("")

    kwargs = {
        "min_staff_line_ratio": args.min_staff_line_ratio,
        "dark_threshold": args.dark_threshold,
        "cluster_gap": args.cluster_gap,
        "padding_px": args.padding,
    }

    cropped = 0
    skipped = 0
    for img in images:
        if args.dry_run:
            bbox = None  # We don't have a dry-run mode for detection
            log(f"Would process: {img.name}")
            continue

        out = img if in_place else output_dir / img.name
        success = crop_to_sheet_music(img, out, **kwargs)
        if success:
            cropped += 1
            if args.verbose:
                log(f"  ✓ cropped: {img.name}")
        else:
            skipped += 1
            if args.verbose:
                log(f"  ✗ no staff lines detected: {img.name} (kept as-is)")
            # Keep the original even when not in-place
            if not in_place:
                import shutil

                shutil.copy2(img, out)

    log("")
    log(f"Cropped: {cropped}")
    log(f"Skipped (no detection): {skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
