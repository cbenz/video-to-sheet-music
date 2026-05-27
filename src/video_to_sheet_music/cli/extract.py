from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from ..extract import (
    detect_crop,
    extract_frames_at_times,
    filter_dark_images,
    get_scene_change_times,
    parse_crop_spec,
    remove_page_number_candidates,
    trim_image,
)
from ..utils import list_pngs, log, require_tools


def build_parser(
    parser: argparse.ArgumentParser | None = None,
) -> argparse.ArgumentParser:
    if parser is None:
        parser = argparse.ArgumentParser(
            description=(
                "Extract distinct slideshow frames to PNG, optionally auto-crop black borders "
                "and trim white margins."
            )
        )
    parser.add_argument("video", type=Path, help="Input video file")
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=None,
        help="Directory where PNG images are written (default: <video_dir>/output_images)",
    )
    parser.add_argument(
        "--scene-threshold",
        type=float,
        default=0.10,
        help="ffmpeg scene threshold in [0,1] (default: 0.10)",
    )
    parser.add_argument(
        "--crop",
        type=str,
        default=None,
        help="Manual crop spec W:H:X:Y (overrides auto cropdetect)",
    )
    parser.add_argument(
        "--no-auto-crop",
        action="store_true",
        help="Disable automatic black border crop detection",
    )
    parser.add_argument(
        "--fuzz",
        type=str,
        default="5%",
        help="ImageMagick fuzz value for trim (default: 5%%)",
    )
    parser.add_argument(
        "--no-trim",
        action="store_true",
        help="Skip white margin trimming",
    )
    parser.add_argument(
        "--min-retained-area",
        type=float,
        default=0.25,
        help=(
            "Trim guard: keep original if trimmed area ratio is below this value "
            "(default: 0.25)"
        ),
    )
    parser.add_argument(
        "--cropdetect-frames",
        type=int,
        default=300,
        help="Number of initial frames used for cropdetect (default: 300)",
    )
    parser.add_argument(
        "--debounce",
        type=float,
        default=0.5,
        help=(
            "Seconds to wait after a scene change before capturing the frame (default: 0.5). "
            "Allows fades/transitions to settle before extraction."
        ),
    )
    parser.add_argument(
        "--min-brightness",
        type=float,
        default=0.0,
        help=(
            "Safety net: remove images whose mean brightness is below this value in [0,1] "
            "(default: 0.0, disabled). With --debounce, rarely needed."
        ),
    )
    parser.add_argument(
        "--no-brightness-filter",
        action="store_true",
        help="Skip brightness filtering",
    )
    parser.add_argument(
        "--remove-page-numbers",
        action="store_true",
        help=(
            "Detect and erase small non-white blobs isolated by white space "
            "(useful for page numbers), then re-trim affected images"
        ),
    )
    parser.add_argument(
        "--pn-max-area-ratio",
        type=float,
        default=0.003,
        help="Max blob area ratio considered as a page number (default: 0.003)",
    )
    parser.add_argument(
        "--pn-white-halo-threshold",
        type=float,
        default=0.97,
        help="Minimum mean whiteness for top/left/right halo in [0,1] (default: 0.97)",
    )
    parser.add_argument(
        "--pn-padding-px",
        type=int,
        default=8,
        help="Padding in pixels around erased page-number blob (default: 8)",
    )
    parser.add_argument(
        "--no-clean",
        action="store_true",
        help="Do not delete output directory before extraction",
    )
    parser.add_argument("--verbose", action="store_true", help="Verbose logs")
    parser.add_argument("--dry-run", action="store_true", help="Print commands only")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        require_tools(["ffmpeg", "magick"])
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    if not args.video.exists():
        print(f"Error: video not found: {args.video}", file=sys.stderr)
        return 2

    if not (0.0 <= args.scene_threshold <= 1.0):
        print("Error: --scene-threshold must be in [0,1]", file=sys.stderr)
        return 2

    if args.min_retained_area <= 0 or args.min_retained_area > 1:
        print("Error: --min-retained-area must be in (0,1]", file=sys.stderr)
        return 2
    if args.pn_max_area_ratio <= 0 or args.pn_max_area_ratio >= 0.1:
        print("Error: --pn-max-area-ratio must be in (0,0.1)", file=sys.stderr)
        return 2
    if not (0.0 <= args.pn_white_halo_threshold <= 1.0):
        print("Error: --pn-white-halo-threshold must be in [0,1]", file=sys.stderr)
        return 2
    if args.pn_padding_px < 0:
        print("Error: --pn-padding-px must be >= 0", file=sys.stderr)
        return 2

    crop: str | None = None
    if args.crop is not None:
        try:
            parse_crop_spec(args.crop)
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 2
        crop = args.crop
    elif not args.no_auto_crop:
        crop = detect_crop(
            args.video,
            args.cropdetect_frames,
            dry_run=args.dry_run,
            verbose=args.verbose,
        )

    if args.output_dir is None:
        args.output_dir = args.video.parent / "output_images"

    if not args.no_clean and args.output_dir.exists():
        log(f"Cleaning output dir: {args.output_dir}")
        if not args.dry_run:
            shutil.rmtree(args.output_dir)

    log(f"Input video: {args.video}")
    log(f"Output dir: {args.output_dir}")
    log(f"Scene threshold: {args.scene_threshold}")
    log(f"Debounce: {args.debounce}s")
    log(f"Crop: {crop if crop else 'none'}")

    try:
        scene_times = get_scene_change_times(
            args.video,
            args.scene_threshold,
            crop,
            dry_run=args.dry_run,
            verbose=args.verbose,
        )
        log(f"Scene changes found: {len(scene_times)}")
        extracted = extract_frames_at_times(
            args.video,
            args.output_dir,
            scene_times,
            args.debounce,
            crop,
            dry_run=args.dry_run,
            verbose=args.verbose,
        )
    except subprocess.CalledProcessError as exc:
        print(exc.stderr or str(exc), file=sys.stderr)
        return exc.returncode or 1

    if not list_pngs(args.output_dir):
        log("No PNG extracted.")
        return 0

    dark_removed = 0
    if not args.no_brightness_filter:
        try:
            dark_removed = filter_dark_images(
                list_pngs(args.output_dir),
                args.min_brightness,
                dry_run=args.dry_run,
                verbose=args.verbose,
            )
        except subprocess.CalledProcessError as exc:
            print(f"Brightness filter failed: {exc.stderr or exc}", file=sys.stderr)
            return 1

    trimmed = 0
    if not args.no_trim:
        for img in list_pngs(args.output_dir):
            try:
                if trim_image(
                    img,
                    args.fuzz,
                    args.min_retained_area,
                    dry_run=args.dry_run,
                    verbose=args.verbose,
                ):
                    trimmed += 1
            except subprocess.CalledProcessError as exc:
                print(f"Trim failed for {img}: {exc.stderr or exc}", file=sys.stderr)
                return 1

    pn_cleaned = 0
    pn_retrimmed = 0
    if args.remove_page_numbers:
        for img in list_pngs(args.output_dir):
            try:
                changed = remove_page_number_candidates(
                    img,
                    max_area_ratio=args.pn_max_area_ratio,
                    white_halo_threshold=args.pn_white_halo_threshold,
                    padding_px=args.pn_padding_px,
                    dry_run=args.dry_run,
                    verbose=args.verbose,
                )
            except subprocess.CalledProcessError as exc:
                print(
                    f"Page-number cleanup failed for {img}: {exc.stderr or exc}",
                    file=sys.stderr,
                )
                return 1
            if not changed:
                continue
            pn_cleaned += 1
            if args.no_trim:
                continue
            try:
                if trim_image(
                    img,
                    args.fuzz,
                    args.min_retained_area,
                    dry_run=args.dry_run,
                    verbose=args.verbose,
                ):
                    pn_retrimmed += 1
            except subprocess.CalledProcessError as exc:
                print(f"Re-trim failed for {img}: {exc.stderr or exc}", file=sys.stderr)
                return 1

    final_count = len(list_pngs(args.output_dir)) if not args.dry_run else extracted
    log("")
    log("Summary")
    log(f"- Extracted PNG: {extracted}")
    log(f"- Dark removed: {dark_removed}")
    log(f"- Trimmed PNG: {trimmed}")
    log(f"- Page-number cleaned: {pn_cleaned}")
    log(f"- Re-trim after cleanup: {pn_retrimmed}")
    log(f"- Final PNG: {final_count}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
