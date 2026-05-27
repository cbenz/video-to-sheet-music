from __future__ import annotations

import re
import subprocess
from collections import Counter
from pathlib import Path
from tempfile import NamedTemporaryFile

from .utils import CROP_RE, get_image_size, log, run_command

PTS_TIME_RE = re.compile(r"\bpts_time:([0-9]+(?:\.[0-9]+)?)")
COMPONENT_RE = re.compile(
    r"^\s*(\d+):\s+(\d+)x(\d+)\+(\d+)\+(\d+)\s+"
    r"[0-9.]+,[0-9.]+\s+(\d+)\s+gray\(([0-9]+)\)"
)


def parse_crop_spec(spec: str) -> tuple[int, int, int, int]:
    m = re.fullmatch(r"(\d+):(\d+):(\d+):(\d+)", spec)
    if not m:
        raise ValueError("Crop must match W:H:X:Y")
    return tuple(int(v) for v in m.groups())


def detect_crop(
    video: Path, cropdetect_frames: int, *, dry_run: bool, verbose: bool
) -> str | None:
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-i",
        str(video),
        "-vf",
        "cropdetect=24:16:0",
        "-frames:v",
        str(cropdetect_frames),
        "-f",
        "null",
        "-",
    ]
    if dry_run:
        log("Auto cropdetect enabled (dry-run: crop not resolved)")
        return None

    proc = subprocess.run(cmd, check=True, text=True, capture_output=True)
    matches = CROP_RE.findall(proc.stderr)
    if not matches:
        return None

    counter = Counter(matches)
    w, h, x, y = counter.most_common(1)[0][0]
    crop = f"{w}:{h}:{x}:{y}"
    if verbose:
        log(f"Auto cropdetect selected: {crop} ({counter[(w, h, x, y)]} hits)")
    return crop


def get_scene_change_times(
    video: Path,
    scene_threshold: float,
    crop: str | None,
    *,
    dry_run: bool,
    verbose: bool,
) -> list[float]:
    filters: list[str] = []
    if crop:
        filters.append(f"crop={crop}")
    filters.append(f"select='gt(scene\\,{scene_threshold})'")
    filters.append("showinfo")
    vf = ",".join(filters)

    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-i",
        str(video),
        "-vf",
        vf,
        "-fps_mode",
        "vfr",
        "-f",
        "null",
        "-",
    ]
    if dry_run:
        from .utils import shlex_quote

        printable = " ".join(shlex_quote(p) for p in cmd)
        log(f"$ {printable}")
        return []

    proc = subprocess.run(cmd, check=True, text=True, capture_output=True)
    times = [float(m.group(1)) for m in PTS_TIME_RE.finditer(proc.stderr)]
    log(f"Scene changes at: {[f'{t:.2f}s' for t in times]}")
    return times


def extract_frames_at_times(
    video: Path,
    output_dir: Path,
    scene_times: list[float],
    debounce_secs: float,
    crop: str | None,
    *,
    dry_run: bool,
    verbose: bool,
) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)

    filters: list[str] = []
    if crop:
        filters.append(f"crop={crop}")

    extracted = 0
    for i, t in enumerate(scene_times):
        target = t + debounce_secs
        output_path = output_dir / f"frame_{i + 1:04d}.png"
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-y",
            "-ss",
            f"{target:.3f}",
            "-i",
            str(video),
            "-frames:v",
            "1",
        ]
        if filters:
            cmd += ["-vf", ",".join(filters)]
        cmd.append(str(output_path))
        run_command(cmd, dry_run=dry_run, verbose=verbose)
        if not dry_run:
            extracted += 1

    return extracted if not dry_run else len(scene_times)


def trim_image(
    path: Path, fuzz: str, min_retained_area: float, *, dry_run: bool, verbose: bool
) -> bool:
    if dry_run:
        run_command(
            ["magick", str(path), "-fuzz", fuzz, "-trim", "+repage", str(path)],
            dry_run=True,
            verbose=verbose,
        )
        return False

    before_w, before_h = get_image_size(path)
    before_area = before_w * before_h

    with NamedTemporaryFile(delete=False, suffix=".png", dir=path.parent) as tmp:
        tmp_path = Path(tmp.name)

    try:
        subprocess.run(
            ["magick", str(path), "-fuzz", fuzz, "-trim", "+repage", str(tmp_path)],
            check=True,
            text=True,
            capture_output=not verbose,
        )
        after_w, after_h = get_image_size(tmp_path)
        after_area = after_w * after_h
        ratio = (after_area / before_area) if before_area else 1.0
        if ratio < min_retained_area:
            if verbose:
                log(
                    f"Trim rollback for {path.name}: retained area ratio {ratio:.3f} "
                    f"< {min_retained_area:.3f}"
                )
            return False
        tmp_path.replace(path)
        return True
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def mean_brightness(path: Path) -> float:
    proc = subprocess.run(
        ["magick", str(path), "-colorspace", "Gray", "-format", "%[fx:mean]", "info:"],
        check=True,
        text=True,
        capture_output=True,
    )
    return float(proc.stdout.strip())


def filter_dark_images(
    images: list[Path], min_brightness: float, *, dry_run: bool, verbose: bool
) -> int:
    removed = 0
    for img in images:
        brightness = mean_brightness(img)
        if brightness < min_brightness:
            log(
                f"Brightness filter: remove {img.name} (mean={brightness:.4f} < {min_brightness:.4f})"
            )
            if not dry_run:
                img.unlink(missing_ok=True)
            removed += 1
    return removed


def _load_gray8(path: Path, img_w: int, img_h: int) -> bytes:
    proc = subprocess.run(
        ["magick", str(path), "-colorspace", "Gray", "-depth", "8", "gray:-"],
        check=True,
        capture_output=True,
    )
    expected = img_w * img_h
    data = proc.stdout
    if len(data) != expected:
        raise RuntimeError(
            f"Unexpected gray buffer size for {path}: got {len(data)}, expected {expected}"
        )
    return data


def _region_mean_gray_from_buffer(
    gray: bytes, img_w: int, img_h: int, x: int, y: int, w: int, h: int
) -> float | None:
    if w <= 0 or h <= 0:
        return None

    x0 = max(0, x)
    y0 = max(0, y)
    x1 = min(img_w, x + w)
    y1 = min(img_h, y + h)
    if x1 <= x0 or y1 <= y0:
        return None

    total = 0
    count = (x1 - x0) * (y1 - y0)
    for yy in range(y0, y1):
        row_start = yy * img_w
        for xx in range(x0, x1):
            total += gray[row_start + xx]

    return (total / count) / 255.0


def _component_rects(path: Path) -> list[tuple[int, int, int, int, int]]:
    proc = subprocess.run(
        [
            "magick",
            str(path),
            "-colorspace",
            "Gray",
            "-threshold",
            "85%",
            "-negate",
            "-define",
            "connected-components:area-threshold=1",
            "-define",
            "connected-components:verbose=true",
            "-connected-components",
            "8",
            "null:",
        ],
        check=True,
        text=True,
        capture_output=True,
    )
    out: list[tuple[int, int, int, int, int]] = []
    cc_output = "\n".join(part for part in [proc.stdout, proc.stderr] if part)
    for line in cc_output.splitlines():
        m = COMPONENT_RE.match(line)
        if not m:
            continue
        comp_id = int(m.group(1))
        if comp_id == 0:
            continue
        w = int(m.group(2))
        h = int(m.group(3))
        x = int(m.group(4))
        y = int(m.group(5))
        area = int(m.group(6))
        out.append((x, y, w, h, area))
    return out


def remove_page_number_candidates(
    path: Path,
    *,
    max_area_ratio: float,
    white_halo_threshold: float,
    padding_px: int,
    dry_run: bool,
    verbose: bool,
) -> bool:
    img_w, img_h = get_image_size(path)
    gray = _load_gray8(path, img_w, img_h)
    img_area = img_w * img_h
    min_area = max(8, int(img_area * 0.00001))
    max_area = max(min_area, int(img_area * max_area_ratio))
    halo = 16
    bottom_start = int(img_h * 0.72)
    max_blob_width = max(20, int(img_w * 0.08))
    max_blob_height = max(20, int(img_h * 0.12))

    candidates: list[tuple[int, int, int, int]] = []
    for x, y, w, h, area in _component_rects(path):
        if area < min_area or area > max_area:
            continue
        if y < bottom_start:
            continue
        if w > max_blob_width or h > max_blob_height:
            continue

        left_x = max(0, x - halo)
        left_y = max(0, y)
        left_w = min(halo, x)
        left_h = min(h, img_h - left_y)

        right_x = min(img_w, x + w)
        right_y = max(0, y)
        right_w = min(halo, img_w - right_x)
        right_h = min(h, img_h - right_y)

        left_mean = _region_mean_gray_from_buffer(
            gray, img_w, img_h, left_x, left_y, left_w, left_h
        )
        right_mean = _region_mean_gray_from_buffer(
            gray, img_w, img_h, right_x, right_y, right_w, right_h
        )
        if left_mean is None or right_mean is None:
            continue

        if left_mean >= white_halo_threshold and right_mean >= white_halo_threshold:
            x0 = max(0, x - padding_px)
            y0 = max(0, y - padding_px)
            x1 = min(img_w - 1, x + w + padding_px)
            y1 = min(img_h - 1, y + h + padding_px)
            candidates.append((x0, y0, x1, y1))

    if not candidates:
        return False

    bottom_y = max(r[1] for r in candidates)
    row_tolerance = 48
    rects = [r for r in candidates if r[1] >= bottom_y - row_tolerance]
    if not rects:
        return False

    cmd = ["magick", str(path), "-fill", "white"]
    for x0, y0, x1, y1 in rects:
        cmd += ["-draw", f"rectangle {x0},{y0} {x1},{y1}"]
    cmd.append(str(path))
    run_command(cmd, dry_run=dry_run, verbose=verbose)
    if verbose:
        log(f"Page-number cleanup on {path.name}: removed {len(rects)} blob(s)")
    return True
