"""Build docs/EXECUTIVE_SUMMARY.pdf from docs/summary/executive_summary.html.

Usage (from the repository root):

    python docs/summary/build_pdf.py
    python docs/summary/build_pdf.py --preview          # also writes a PNG preview
    python docs/summary/build_pdf.py --figure "docs/img/seed_stats.png::학습 시드별 진입 건수"

--figure may be repeated (one or two figures fit). It rewrites the block between
<!-- FIGURES:BEGIN --> and <!-- FIGURES:END --> in the HTML, so the change stays in
the source file. Paths are relative to the repository root.

Renderer: Microsoft Edge headless. The script fails if the PDF is not exactly one page
(checked with poppler `pdfinfo` when it is on PATH).
"""

from __future__ import annotations

import argparse
import html
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DOCS = HERE.parent
HTML = HERE / "executive_summary.html"
PDF = DOCS / "EXECUTIVE_SUMMARY.pdf"
PREVIEW = HERE / "preview"

EDGE_CANDIDATES = [
    Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Microsoft/Edge/Application/msedge.exe",
    Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Microsoft/Edge/Application/msedge.exe",
]

BLOCK = re.compile(r"(<!-- FIGURES:BEGIN -->)(.*?)(<!-- FIGURES:END -->)", re.S)


def find_edge() -> Path:
    for p in EDGE_CANDIDATES:
        if p.exists():
            return p
    found = shutil.which("msedge")
    if found:
        return Path(found)
    sys.exit("msedge.exe not found")


def rewrite_figures(specs: list[str]) -> None:
    repo = DOCS.parent
    items = []
    for spec in specs:
        path, _, caption = spec.partition("::")
        img = (repo / path).resolve()
        if not img.exists():
            sys.exit(f"figure not found: {img}")
        rel = os.path.relpath(img, HERE).replace("\\", "/")
        cap = html.escape(caption or img.stem)
        # Charts must not be cropped: show the whole image, capped in height to keep one page.
        style = "height:auto;max-height:62mm;object-fit:contain;background:#fff"
        items.append(
            f'    <figure><img src="{rel}" alt="{cap}" style="{style}"><figcaption>{cap}</figcaption></figure>'
        )
    cols = "1fr 1fr" if len(items) > 1 else "1fr"
    block = (
        f'\n  <div class="figs" style="grid-template-columns:{cols}">\n'
        + "\n".join(items)
        + "\n  </div>\n"
    )
    text = HTML.read_text(encoding="utf-8")
    if not BLOCK.search(text):
        sys.exit("FIGURES markers missing in HTML")
    HTML.write_text(BLOCK.sub(lambda m: m.group(1) + block + m.group(3), text), encoding="utf-8")


def build() -> None:
    edge = find_edge()
    url = HTML.as_uri()
    cmd = [
        str(edge),
        "--headless",
        "--disable-gpu",
        "--no-pdf-header-footer",
        "--run-all-compositor-stages-before-draw",
        "--virtual-time-budget=5000",
        f"--print-to-pdf={PDF}",
        url,
    ]
    subprocess.run(cmd, check=True, capture_output=True, timeout=120)
    if not PDF.exists():
        sys.exit("PDF was not written")
    print(f"wrote {PDF}")


def check_pages() -> None:
    pdfinfo = shutil.which("pdfinfo")
    if not pdfinfo:
        print("pdfinfo not on PATH; page count not checked")
        return
    out = subprocess.run([pdfinfo, str(PDF)], capture_output=True, text=True, check=True).stdout
    pages = int(re.search(r"Pages:\s+(\d+)", out).group(1))
    print(f"pages: {pages}")
    if pages != 1:
        sys.exit("expected exactly one page; shorten the content or adjust the CSS")


def preview() -> None:
    tool = shutil.which("pdftoppm")
    if not tool:
        print("pdftoppm not on PATH; no preview")
        return
    PREVIEW.mkdir(exist_ok=True)
    subprocess.run([tool, "-png", "-r", "110", str(PDF), str(PREVIEW / "page")], check=True)
    print(f"preview in {PREVIEW}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--figure", action="append", default=[], help="PATH::CAPTION, repeatable")
    ap.add_argument("--preview", action="store_true")
    args = ap.parse_args()
    if args.figure:
        rewrite_figures(args.figure)
    build()
    check_pages()
    if args.preview:
        preview()


if __name__ == "__main__":
    main()
