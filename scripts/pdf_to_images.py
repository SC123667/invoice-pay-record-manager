#!/usr/bin/env python3
"""Convert PDF pages to image files using PyMuPDF.

Usage:
    python pdf_to_images.py input.pdf [output_dir] [--dpi 200]

Requires: pip install pymupdf
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    import fitz  # type: ignore
except ImportError:  # pragma: no cover - runtime requirement
    print("PyMuPDF (fitz) is not installed. Run `pip install pymupdf` first.", file=sys.stderr)
    sys.exit(1)

SUPPORTED_SUFFIXES = {".pdf"}
DEFAULT_DPI = 200


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert PDF pages to images using PyMuPDF")
    parser.add_argument("pdf", type=Path, help="Path to the source PDF file")
    parser.add_argument(
        "output",
        nargs="?",
        type=Path,
        help="Directory to store generated images (defaults to <pdf_stem>_images next to the PDF)",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=DEFAULT_DPI,
        help="Rendering resolution in DPI (default: %(default)s)",
    )
    parser.add_argument(
        "--suffix",
        choices=["png", "jpg"],
        default="png",
        help="Output image format (default: %(default)s)",
    )
    return parser.parse_args()


def ensure_pdf(path: Path) -> Path:
    path = path.expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"PDF文件不存在: {path}")
    if path.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise ValueError(f"暂不支持的文件类型: {path.suffix}")
    return path


def prepare_output_dir(pdf_path: Path, output: Path | None) -> Path:
    if output is None:
        output = pdf_path.with_name(f"{pdf_path.stem}_images")
    output = output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    return output


def pdf_to_images(pdf_path: Path, output_dir: Path, dpi: int, suffix: str) -> list[Path]:
    doc = fitz.open(pdf_path)
    if doc.page_count == 0:
        raise RuntimeError("PDF不包含任何页面，无法转换")

    zoom = dpi / 72.0
    matrix = fitz.Matrix(zoom, zoom)
    generated: list[Path] = []

    for index, page in enumerate(doc, start=1):
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        output_file = output_dir / f"{pdf_path.stem}_page{index:03d}.{suffix}"
        pix.save(output_file)
        generated.append(output_file)

    return generated


def main() -> int:
    try:
        args = parse_args()
        pdf_path = ensure_pdf(args.pdf)
        output_dir = prepare_output_dir(pdf_path, args.output)
        images = pdf_to_images(pdf_path, output_dir, args.dpi, args.suffix)
    except Exception as exc:  # pragma: no cover - CLI feedback
        print(f"转换失败: {exc}", file=sys.stderr)
        return 1

    print(f"已生成 {len(images)} 张图片，存储在: {output_dir}")
    for path in images:
        print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
