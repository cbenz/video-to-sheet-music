# Video to Sheet Music

Convert a slideshow video into a printable A4 PDF — extract distinct frames as clean PNGs, then lay them out on pages.

## How It Works

A single CLI with two subcommands forms a simple pipeline:

1. **`video-to-sheet-music extract-images`** — Detects scene changes in a video, extracts key frames, and cleans them up (auto-crop, trim white borders, deduplicate).
2. **`video-to-sheet-music combine-images`** — Assembles the resulting PNGs into an A4 portrait PDF with configurable layouts.

## Installation

```bash
git clone <repo-url> && cd video-to-sheet-music
uv sync
uv tool install .
```

Or install globally from the project directory:

```bash
uv tool install .
```

The `video-to-sheet-music` command will then be available system-wide.

## Prerequisites

- [FFmpeg](https://ffmpeg.org/) (extraction)
- [ImageMagick](https://imagemagick.org/) (`magick` command, required for both scripts)

## Usage

### 1. Extract Distinct Frames

```bash
video-to-sheet-music extract-images "video.mkv" -o output_images
```

With custom options:

```bash
video-to-sheet-music extract-images "video.mkv" \
  -o output_images \
  --scene-threshold 0.10 \
  --fuzz 5% \
  --debounce 0.5
```

| Option | Description |
|---|---|
| `--crop W:H:X:Y` | Manual crop region |
| `--no-auto-crop` | Disable automatic crop detection |
| `--no-trim` | Disable white border trimming |
| `--no-dedup` | Disable perceptual deduplication |
| `--dry-run` | Print commands without executing |

### 2. Manual Touch-Up (Optional)

Before generating the PDF, you can review, rename, or delete PNGs in the output folder.

### 3. Combine into an A4 PDF

```bash
video-to-sheet-music combine-images output_images -o output.pdf --layout 1x2
```

| Layout | Description |
|---|---|
| `1x2` (default) | Two images stacked vertically per page |
| `2x1` | Two images side by side |
| `1x1` | One image per page |

Additional options:

| Option | Description |
|---|---|
| `--pattern 'frame_*.png'` | Filter files by glob pattern |
| `--side-margin-cm 1.0` | Left/right page margin in cm |
| `--no-page-numbers` | Disable page numbering |
| `--dry-run` | Print commands without executing |

## Typical Pipeline

```bash
video-to-sheet-music extract-images "video.mkv" -o output_images
# optional manual touch-up of PNGs
video-to-sheet-music combine-images output_images -o transcription.pdf --layout 1x2
```

## Development

```bash
uv sync          # Install dependencies and the package in editable mode
uv run -- <cmd>  # Run a command in the project environment
```

## License

This project is provided as-is for personal use.
