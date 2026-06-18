#!/usr/bin/env python3
"""
Add TOC page + PDF bookmarks to existing Red Storm PDF.
"""
import re
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, DictionaryObject, NameObject, NumberObject, TextStringObject

INPUT_PDF = Path("./Red-Storm_Complete.pdf")
OUTPUT_PDF = Path("./Red-Storm_Complete_toc.pdf")
TARGET_W, TARGET_H = 1072, 1448
BG_COLOR = (15, 15, 15)

def get_font(size, bold=True):
    paths = {
        True: ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
               "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"],
        False: ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/usr/share/fonts/TTF/DejaVuSans.ttf"],
    }
    for p in paths[bold]:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()

import os

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

def create_toc_pages(chapters, num_toc_pages):
    """Create multi-page TOC with chapter list, ~30 chapters per page."""
    pages_per_toc = 30
    toc_pages = []

    for page_idx in range(0, len(chapters), pages_per_toc):
        batch = chapters[page_idx:page_idx + pages_per_toc]
        page = Image.new("RGB", (TARGET_W, TARGET_H), BG_COLOR)
        draw = ImageDraw.Draw(page)

        header_font = get_font(44, bold=True)
        item_font = get_font(28, bold=False)
        small_font = get_font(22, bold=False)

        # Header
        hdr = "TABLE OF CONTENTS"
        bbox = draw.textbbox((0, 0), hdr, font=header_font)
        draw.text(((TARGET_W - (bbox[2] - bbox[0])) // 2, 40), hdr, fill=(255, 100, 100), font=header_font)

        title = "RED STORM"
        bbox2 = draw.textbbox((0, 0), title, font=small_font)
        draw.text(((TARGET_W - (bbox2[2] - bbox2[0])) // 2, 100), title, fill=(120, 120, 120), font=small_font)

        # Separator
        draw.line([(60, 140), (TARGET_W - 60, 140)], fill=(60, 60, 60), width=1)

        y = 165
        for ch, num_pages, start_pg, end_pg in batch:
            ch_text = f"Chapter {ch}"
            adjusted_start = start_pg + num_toc_pages
            pg_text = f"p. {adjusted_start}"

            draw.text((80, y), ch_text, fill=(200, 200, 200), font=item_font)
            bbox_pg = draw.textbbox((0, 0), pg_text, font=item_font)
            draw.text((TARGET_W - 80 - (bbox_pg[2] - bbox_pg[0]), y), pg_text, fill=(140, 140, 140), font=item_font)

            # Dotted line between
            dots_x = draw.textbbox((0, 0), ch_text, font=item_font)[2] + 20
            dots_end = TARGET_W - 80 - (bbox_pg[2] - bbox_pg[0]) - 15
            for dx in range(int(dots_x), int(dots_end), 12):
                draw.rectangle([dx, y + 14, dx + 4, y + 16], fill=(60, 60, 60))

            y += 40

        # Page footer
        page_num = f"TOC {page_idx // pages_per_toc + 1}"
        bbox_pn = draw.textbbox((0, 0), page_num, font=small_font)
        draw.text(((TARGET_W - (bbox_pn[2] - bbox_pn[0])) // 2, TARGET_H - 50),
                  page_num, fill=(100, 100, 100), font=small_font)

        toc_pages.append(page)

    return toc_pages

def add_toc_and_bookmarks():
    import shutil

    chapters = parse_chapter_pages("pdf_log.txt")
    print(f"Parsed {len(chapters)} chapters from log")

    # Create TOC pages - first estimate how many TOC pages we need
    print("Creating TOC pages...")
    estimated_toc_pages = (len(chapters) + 29) // 30
    toc_pages = create_toc_pages(chapters, estimated_toc_pages)
    num_toc_pages = len(toc_pages)
    print(f"  {num_toc_pages} TOC pages created")
    # Recreate with accurate offset now that we know the real count
    toc_pages = create_toc_pages(chapters, num_toc_pages)
    num_toc_pages = len(toc_pages)

    # Save TOC as temp PDF
    num_toc_pages = len(toc_pages)
    tmp_toc = Path("./_toc_tmp.pdf")
    if toc_pages:
        toc_pages[0].save(tmp_toc, "PDF", save_all=True, append_images=toc_pages[1:], resolution=150)
    toc_pages.clear()

    # Read original PDF - skip existing TOC pages
    print("Reading original PDF...")
    reader = PdfReader(str(INPUT_PDF))
    total_raw = len(reader.pages)
    print(f"  {total_raw} raw pages")

    # Original content was 36769 pages. If input has more, the extras are old TOC pages.
    KNOWN_CONTENT_PAGES = 36769
    skip = max(0, total_raw - KNOWN_CONTENT_PAGES)
    if skip > 0:
        print(f"  Skipping {skip} existing TOC pages")
    total_pages = total_raw - skip

    # Create output: TOC pages + original pages
    print("Building output PDF with TOC + bookmarks...")
    writer = PdfWriter()

    # Add TOC pages first
    toc_reader = PdfReader(str(tmp_toc))
    for page in toc_reader.pages:
        writer.add_page(page)

    # Add all original pages (skip existing TOC)
    for i, page in enumerate(reader.pages):
        if i < skip:
            continue
        writer.add_page(page)
        added = i - skip + 1
        if added % 5000 == 0:
            print(f"  Added {added}/{total_pages} pages...", flush=True)

    # Add bookmarks (outlines)
    print("Adding bookmarks...")
    # start_pg is 1-indexed from original PDF, add TOC offset, convert to 0-indexed for pypdf
    for ch, num_pages, start_pg, end_pg in chapters:
        adjusted_page = (start_pg - 1) + num_toc_pages
        writer.add_outline_item(
            title=f"Chapter {ch}",
            page_number=adjusted_page,
        )

    # Write output
    print(f"Writing {OUTPUT_PDF}...")
    OUTPUT_PDF.unlink(missing_ok=True)
    with open(OUTPUT_PDF, "wb") as f:
        writer.write(f)

    size_mb = OUTPUT_PDF.stat().st_size / (1024 * 1024)
    print(f"\nDone! {OUTPUT_PDF} ({size_mb:.1f} MB)")
    print(f"Total pages: {total_pages + num_toc_pages} (TOC: {num_toc_pages} + content: {total_pages})")

    # Cleanup
    tmp_toc.unlink(missing_ok=True)

if __name__ == "__main__":
    add_toc_and_bookmarks()
