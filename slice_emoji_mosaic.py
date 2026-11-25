#!/usr/bin/env python3
"""Slice an image, GIF, or short video (<=3s) into seamless 100x100 Telegram custom emoji tiles.

Prevents dark seams between tiles by edge-smearing boundary RGB pixels into transparent
padding (alpha=0) instead of leaving transparent black rgba(0, 0, 0, 0).

Requirements:
  - Python 3.10+
  - Pillow (`pip install pillow`) for static PNG tiles
  - FFmpeg with libvpx-vp9 (`ffmpeg`) for animated WebM VP9 tiles
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

TILE_SIZE = 100


def slice_static_image(input_path: Path, output_dir: Path, cols: int, rows: int, padding: int) -> list[Path]:
    from PIL import Image

    if not 0 <= padding <= 10:
        raise ValueError("padding must be between 0 and 10 pixels")
    if cols * rows > 100:
        raise ValueError("Telegram supports at most 100 custom_emoji entities per message")

    inner = TILE_SIZE - 2 * padding
    img = Image.open(input_path).convert("RGBA")
    resized = img.resize((cols * inner, rows * inner), Image.Resampling.LANCZOS)

    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[Path] = []
    idx = 0
    for r in range(rows):
        for c in range(cols):
            tile = resized.crop((c * inner, r * inner, (c + 1) * inner, (r + 1) * inner))
            if padding > 0:
                canvas = Image.new("RGBA", (TILE_SIZE, TILE_SIZE), (0, 0, 0, 0))
                # Paste inner tile
                canvas.paste(tile, (padding, padding))
                # Edge-smear top/bottom/left/right RGB with alpha=0 to prevent dark seams on GPU downscaling
                px = canvas.load()
                for x in range(padding, padding + inner):
                    top_rgb = px[x, padding][:3]
                    bot_rgb = px[x, padding + inner - 1][:3]
                    for y in range(padding):
                        px[x, y] = (*top_rgb, 0)
                    for y in range(padding + inner, TILE_SIZE):
                        px[x, y] = (*bot_rgb, 0)
                for y in range(TILE_SIZE):
                    src_y = min(max(y, padding), padding + inner - 1)
                    left_rgb = px[padding, src_y][:3]
                    right_rgb = px[padding + inner - 1, src_y][:3]
                    for x in range(padding):
                        px[x, y] = (*left_rgb, 0)
                    for x in range(padding + inner, TILE_SIZE):
                        px[x, y] = (*right_rgb, 0)
                out_tile = canvas
            else:
                out_tile = tile

            out_path = output_dir / f"tile_{idx:03d}.png"
            out_tile.save(out_path, format="PNG", optimize=True)
            results.append(out_path)
            idx += 1
    return results


def build_vp9_filter(crop_w: int, crop_h: int, crop_x: int, crop_y: int, padding: int) -> str:
    inner = TILE_SIZE - 2 * padding
    base = f"crop={crop_w}:{crop_h}:{crop_x}:{crop_y},scale={inner}:{inner}:flags=lanczos,format=rgba"
    if padding <= 0:
        return f"{base},format=yuva420p"
    hi = TILE_SIZE - padding
    return (
        f"{base},"
        f"pad={TILE_SIZE}:{TILE_SIZE}:{padding}:{padding}:color=black@0,"
        f"fillborders=left={padding}:right={padding}:top={padding}:bottom={padding}:mode=smear,"
        f"geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':"
        f"a='if(lt(X,{padding})+gte(X,{hi})+lt(Y,{padding})+gte(Y,{hi}),0,alpha(X,Y))',"
        f"format=yuva420p"
    )


def probe_dimensions(input_path: Path) -> tuple[int, int]:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise RuntimeError("ffprobe not found in PATH")
    res = subprocess.run(
        [ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x", str(input_path)],
        capture_output=True, text=True, check=True,
    )
    w_str, h_str = res.stdout.strip().split("x", 1)
    return int(w_str), int(h_str)


def slice_video(input_path: Path, output_dir: Path, cols: int, rows: int, padding: int, crf: int = 32) -> list[Path]:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found in PATH")
    if cols * rows > 100:
        raise ValueError("Telegram supports at most 100 custom_emoji entities per message")

    src_w, src_h = probe_dimensions(input_path)
    tile_w = src_w // cols
    tile_h = src_h // rows
    if tile_w < 2 or tile_h < 2:
        raise ValueError("Source video is too small for the requested grid")

    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[Path] = []
    idx = 0
    for r in range(rows):
        for c in range(cols):
            vf = build_vp9_filter(tile_w, tile_h, c * tile_w, r * tile_h, padding)
            out_path = output_dir / f"tile_{idx:03d}.webm"
            cmd = [
                ffmpeg, "-y", "-i", str(input_path),
                "-an", "-t", "3", "-r", "30",
                "-vf", vf,
                "-c:v", "libvpx-vp9", "-b:v", "0", "-crf", str(crf),
                "-auto-alt-ref", "0", "-threads", "2",
                str(out_path),
            ]
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            results.append(out_path)
            idx += 1
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Slice media into seamless 100x100 Telegram custom emoji tiles.")
    parser.add_argument("input", type=Path, help="Input image, GIF, or short video")
    parser.add_argument("-o", "--output", type=Path, default=Path("tiles_out"), help="Output directory")
    parser.add_argument("--cols", type=int, default=5, help="Grid columns (1..10)")
    parser.add_argument("--rows", type=int, default=5, help="Grid rows (1..10)")
    parser.add_argument("--padding", type=int, default=3, help="Transparent edge-smeared padding px (0..6)")
    args = parser.parse_args()

    ext = args.input.suffix.lower()
    if ext in {".gif", ".mp4", ".webm", ".mov", ".mkv"}:
        tiles = slice_video(args.input, args.output, args.cols, args.rows, args.padding)
    else:
        tiles = slice_static_image(args.input, args.output, args.cols, args.rows, args.padding)
    print(f"Generated {len(tiles)} seamless 100x100 tiles in {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
