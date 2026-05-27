from __future__ import annotations

import re
import shutil
import subprocess
from collections.abc import Iterable
from pathlib import Path

CROP_RE = re.compile(r"crop=(\d+):(\d+):(\d+):(\d+)")
SIZE_RE = re.compile(r"^(\d+)x(\d+)$")


def log(msg: str) -> None:
    print(msg)


def shlex_quote(s: str) -> str:
    if re.match(r"^[A-Za-z0-9_./:=,%+-]+$", s):
        return s
    return "'" + s.replace("'", "'\\''") + "'"


def run_command(
    cmd: list[str], *, dry_run: bool = False, verbose: bool = False
) -> subprocess.CompletedProcess[str]:
    printable = " ".join(shlex_quote(part) for part in cmd)
    log(f"$ {printable}")
    if dry_run:
        return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")
    return subprocess.run(
        cmd,
        check=True,
        text=True,
        capture_output=not verbose,
    )


def require_tools(tools: Iterable[str]) -> None:
    missing = [tool for tool in tools if shutil.which(tool) is None]
    if missing:
        raise RuntimeError(f"Missing required tools: {', '.join(missing)}")


def list_pngs(folder: Path) -> list[Path]:
    def key(path: Path) -> tuple[str, int]:
        m = re.search(r"(\d+)", path.stem)
        return (path.stem, int(m.group(1)) if m else -1)

    return sorted(folder.glob("*.png"), key=key)


def get_image_size(path: Path) -> tuple[int, int]:
    proc = subprocess.run(
        ["magick", str(path), "-format", "%wx%h", "info:"],
        check=True,
        text=True,
        capture_output=True,
    )
    s = proc.stdout.strip()
    m = SIZE_RE.match(s)
    if not m:
        raise RuntimeError(f"Unexpected image size output for {path}: {s}")
    return int(m.group(1)), int(m.group(2))
