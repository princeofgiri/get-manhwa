#!/usr/bin/env python3
"""
Add clickable links to TOC pages using PyMuPDF (fitz).
Coordinates scaled to actual PDF page size.
"""
import re
import fitz
from pathlib import Path

INPUT_PDF = Path("./Red-Storm_Complete.pdf")
OUTPUT_PDF = Path("./Red-Storm_Complete_links.pdf")
TOC_PAGES = 16
TARGET_W, TARGET_H = 1072, 1448
PAGES_PER_TOC = 30

def parse_chapter_pages(log_path):
    chapters = []
    seen = set()
    with open(log_path) as f:
        for line in f:
            m = re.search(r'Chapter (\S+): (\d+) pages.*global p\.(\d+)', line)
            if m:
                ch = m.group(1)
                pages = int(m.group(2))
                end = int(m.group(3))
                start = end - pages + 1
                if ch not in seen:
                    seen.add(ch)
                    chapters.append((ch, pages, start, end))
    chapters.sort(key=lambda x: float(x[0]))
    return chapters

def add_links():
    chapters = parse_chapter_pages("pdf_log.txt")
    print(f"Parsed {len(chapters)} chapters")

    doc = fitz.open(str(INPUT_PDF))

    # Get actual PDF page size to compute scale
    page0 = doc[0]
    pdf_w = page0.mediabox.width
    pdf_h = page0.mediabox.height
    sx = pdf_w / TARGET_W
    sy = pdf_h / TARGET_H
    print(f"PDF page: {pdf_w:.1f}x{pdf_h:.1f} pts, scale: {sx:.4f}x{sy:.4f}")

    print("Adding clickable links to TOC pages...")

    total_links = 0
    for toc_page_idx in range(TOC_PAGES):
        batch_start = toc_page_idx * PAGES_PER_TOC
        batch_end = min(batch_start + PAGES_PER_TOC, len(chapters))
        batch = chapters[batch_start:batch_end]

        page = doc[toc_page_idx]
        y_start = 165
        row_height = 40

        for ch, num_pages, start_pg, end_pg in batch:
            target_page_idx = (start_pg - 1) + TOC_PAGES

            # Scale coordinates from image pixels to PDF points
            rect = fitz.Rect(
                60 * sx,
                y_start * sy,
                (TARGET_W - 60) * sx,
                (y_start + 35) * sy
            )

            link = {
                "kind": fitz.LINK_GOTO,
                "page": target_page_idx,
                "from": rect,
            }
            page.insert_link(link)
            total_links += 1

            y_start += row_height

    print(f"Added {total_links} links. Saving...")
    doc.save(str(OUTPUT_PDF))
    doc.close()

    size_mb = OUTPUT_PDF.stat().st_size / (1024 * 1024)
    print(f"Done! {OUTPUT_PDF} ({size_mb:.1f} MB)")

if __name__ == "__main__":
    add_links()
