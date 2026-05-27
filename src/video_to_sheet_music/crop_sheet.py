"""Detect and crop the sheet-music region in split-screen video frames.

Strategy (no AI, pure image analysis):
1. Musical staff lines are the only long, thin, horizontal dark features.
2. Detect rows containing long dark runs → staff line candidates.
3. Cluster nearby candidate rows (staff lines are ~6-12 px apart).
4. Largest cluster → vertical extent of the sheet music.
5. Within that band, find horizontal extent via dark columns.
6. Expand bounding box outward until white margins are reached.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image


def _longest_true_run(row: np.ndarray) -> int:
    """Return the length of the longest contiguous run of True values in a 1-D boolean array."""
    # Pad with False to catch runs at edges
    padded = np.concatenate(([False], row, [False]))
    edges = np.diff(padded.astype(np.int8))
    starts = np.where(edges == 1)[0]
    ends = np.where(edges == -1)[0]
    if len(starts) == 0:
        return 0
    return int((ends - starts).max())


def detect_staff_line_rows(dark: np.ndarray, min_run_px: int) -> set[int]:
    """Return the set of row indices that contain a dark run >= min_run_px."""
    result: set[int] = set()
    for y in range(dark.shape[0]):
        if _longest_true_run(dark[y]) >= min_run_px:
            result.add(y)
    return result


def cluster_rows(rows: set[int], max_gap: int) -> list[list[int]]:
    """Cluster sorted row indices, splitting when gap > max_gap."""
    if not rows:
        return []
    sorted_rows = sorted(rows)
    clusters: list[list[int]] = []
    current = [sorted_rows[0]]
    for r in sorted_rows[1:]:
        if r - current[-1] <= max_gap:
            current.append(r)
        else:
            clusters.append(current)
            current = [r]
    clusters.append(current)
    return clusters


def _filter_staff_clusters(
    clusters: list[list[int]],
    min_density: float = 0.03,
    max_density: float = 0.50,
) -> list[list[int]]:
    """Keep only clusters whose row density is characteristic of staff lines.

    Continuous dark bars (e.g. split-screen divider) have density ≈ 1.0.
    Isolated noise has density ≈ 0.
    """
    result: list[list[int]] = []
    for c in clusters:
        span = c[-1] - c[0] + 1
        density = len(c) / span
        if min_density <= density <= max_density:
            result.append(c)
    return result


def _edge_is_clean(
    binary: np.ndarray, x_left: int, x_right: int, y_top: int, y_bot: int, side: str
) -> bool:
    """Check that the given edge of the bbox does not intersect any black pixel."""
    if side == "top":
        return not np.any(binary[y_top, x_left:x_right])
    elif side == "bottom":
        return not np.any(binary[y_bot - 1, x_left:x_right])
    elif side == "left":
        return not np.any(binary[y_top:y_bot, x_left])
    elif side == "right":
        return not np.any(binary[y_top:y_bot, x_right - 1])


def expand_to_white(
    arr: np.ndarray,
    x: int,
    y: int,
    w: int,
    h: int,
    dark_threshold: int,
) -> tuple[int, int, int, int]:
    """Expand the bounding box outward, one pixel at a time, until every edge
    lands on a pixel line that is entirely white (no black pixel).

    The image is binarized: pixels < *dark_threshold* become black (content),
    the rest become white (background).  The expansion stops as soon as an edge
    is clean — it does not overshoot into a second content region.
    """
    img_h, img_w = arr.shape
    binary = arr < dark_threshold  # True = black / content

    x_left, x_right = x, x + w
    y_top, y_bot = y, y + h

    # Expand up
    while y_top > 0 and not _edge_is_clean(
        binary, x_left, x_right, y_top - 1, y_bot, "top"
    ):
        y_top -= 1
    # Expand down
    while y_bot < img_h and not _edge_is_clean(
        binary, x_left, x_right, y_top, y_bot + 1, "bottom"
    ):
        y_bot += 1
    # Expand left
    while x_left > 0 and not _edge_is_clean(
        binary, x_left - 1, x_right, y_top, y_bot, "left"
    ):
        x_left -= 1
    # Expand right
    while x_right < img_w and not _edge_is_clean(
        binary, x_left, x_right + 1, y_top, y_bot, "right"
    ):
        x_right += 1

    return (x_left, y_top, x_right - x_left, y_bot - y_top)


def detect_sheet_music_region(
    image_path: Path,
    *,
    min_staff_line_ratio: float = 0.30,
    dark_threshold: int = 128,
    cluster_gap: int = 20,
    padding_px: int = 10,
) -> tuple[int, int, int, int] | None:
    """Return (x, y, w, h) of the sheet-music region, or None if undetected.

    Parameters
    ----------
    image_path:
        Path to the PNG frame.
    min_staff_line_ratio:
        Minimum dark-run length as a fraction of image width to count as a staff line.
    dark_threshold:
        Pixel value (0-255) below which a pixel is considered "dark".
        Used for both staff-line detection and margin expansion.
    cluster_gap:
        Maximum vertical gap (px) between two detected staff-line rows to stay in the
        same cluster. Staff lines within a system are typically 6-12 px apart.

    padding_px:
        Extra padding added to the final crop on all sides.
    """
    img = Image.open(image_path).convert("L")
    arr = np.array(img, dtype=np.float64)
    img_h, img_w = arr.shape
    min_run_px = max(50, int(img_w * min_staff_line_ratio))

    # 1. Detect staff-line candidate rows
    dark = arr < dark_threshold
    staff_rows = detect_staff_line_rows(dark, min_run_px)

    if not staff_rows:
        return None

    # 2. Cluster rows, then filter by density.
    #    Real staff lines have gaps (~5 lines per ~40 px → density ≈ 0.12).
    #    Continuous dark bars (divider, UI) have density ≈ 1.0 → reject.
    #    Isolated noise rows have very low density → reject.
    clusters = cluster_rows(staff_rows, cluster_gap)
    valid = _filter_staff_clusters(clusters)

    if not valid:
        return None

    # 3. Take the vertical range covering all valid clusters.
    #    They all belong to the sheet-music region.
    all_rows = sorted({r for c in valid for r in c})
    y_min = all_rows[0]
    y_max = all_rows[-1]

    # 4. Horizontal extent within the staff band
    band = dark[y_min : y_max + 1, :]
    col_has_dark = np.any(band, axis=0)
    dark_cols = np.where(col_has_dark)[0]
    if len(dark_cols) == 0:
        return None
    x_min = dark_cols[0]
    x_max = dark_cols[-1]

    # 5. Expand to white margins (binarize + binary search)
    x, y, w, h = expand_to_white(
        arr,
        x_min,
        y_min,
        x_max - x_min + 1,
        y_max - y_min + 1,
        dark_threshold,
    )

    # 6. Add padding (clamped to image bounds)
    x = max(0, int(x) - padding_px)
    y = max(0, int(y) - padding_px)
    w = min(img_w - x, int(w) + 2 * padding_px)
    h = min(img_h - y, int(h) + 2 * padding_px)

    return (x, y, w, h)


def crop_to_sheet_music(
    image_path: Path,
    output_path: Path | None = None,
    **kwargs,
) -> bool:
    """Crop *image_path* to its sheet-music region.

    Parameters
    ----------
    image_path:
        Input PNG.
    output_path:
        Where to write the cropped PNG.  Defaults to overwriting *image_path*.
    **kwargs:
        Forwarded to :func:`detect_sheet_music_region`.

    Returns
    -------
    True if the region was detected and cropping was performed, False otherwise.
    """
    bbox = detect_sheet_music_region(image_path, **kwargs)
    if bbox is None:
        return False

    img = Image.open(image_path)
    cropped = img.crop((bbox[0], bbox[1], bbox[0] + bbox[2], bbox[1] + bbox[3]))
    target = output_path or image_path
    cropped.save(target, "PNG")
    return True
