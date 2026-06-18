#!/usr/bin/env python3
"""
Red Storm Manhwa → Single PDF ebook (memory-efficient)
- Creates per-chapter temp PDFs, then merges streaming
- Target: 1072x1448 (6.8" Kindle/Kobo)
- Chapter separators + page numbers
- Tall image splitting
"""

import os
import sys
import shutil
import tempfile
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfWriter

INPUT_DIR = Path("./Red-Storm")
OUTPUT_PDF = Path("./Red-Storm_Complete.pdf")
TMP_DIR = Path("./_pdf_tmp")
TARGET_W, TARGET_H = 1072, 1448
SPLIT_RATIO = 1.8
MARGIN = 30
BG_COLOR = (15, 15, 15)
TEXT_COLOR = (200, 200, 200)
ACCENT_COLOR = (255, 100, 100)

def get_font(size, bold=True):
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/TTF/DejaVuSans.ttf",
    ]
    for p in paths:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()

def get_chapters():
    chapters = []
    for p in sorted(INPUT_DIR.iterdir()):
        if p.is_dir() and p.name.startswith("Chapter_"):
            ch_num = p.name.replace("Chapter_", "")
            chapters.append((ch_num, p))
    def nat_key(item):
        try:
            return float(item[0])
        except ValueError:
            return 999999
    chapters.sort(key=nat_key)
    return chapters

def fit_image_to_page(img):
    page = Image.new("RGB", (TARGET_W, TARGET_H), BG_COLOR)
    iw, ih = img.size
    scale = min((TARGET_W - 2 * MARGIN) / iw, (TARGET_H - 2 * MARGIN) / ih)
    new_w, new_h = int(iw * scale), int(ih * scale)
    resized = img.resize((new_w, new_h), Image.LANCZOS)
    x, y = (TARGET_W - new_w) // 2, (TARGET_H - new_h) // 2
    page.paste(resized, (x, y))
    return page

def make_chapter_separator(ch_num, image_count, chapter_idx, total_chapters):
    page = Image.new("RGB", (TARGET_W, TARGET_H), BG_COLOR)
    draw = ImageDraw.Draw(page)
    title_font = get_font(64, bold=True)
    info_font = get_font(36, bold=False)
    small_font = get_font(28, bold=False)

    ch_label = f"Chapter {ch_num}"
    bbox = draw.textbbox((0, 0), ch_label, font=title_font)
    draw.text(((TARGET_W - (bbox[2] - bbox[0])) // 2, TARGET_H // 2 - 120), ch_label, fill=ACCENT_COLOR, font=title_font)

    line_y = TARGET_H // 2 - 20
    draw.line([(TARGET_W // 4, line_y), (TARGET_W * 3 // 4, line_y)], fill=(80, 80, 80), width=2)

    info1 = f"{image_count} images"
    bbox1 = draw.textbbox((0, 0), info1, font=info_font)
    draw.text(((TARGET_W - (bbox1[2] - bbox1[0])) // 2, line_y + 30), info1, fill=TEXT_COLOR, font=info_font)

    info2 = f"Chapter {chapter_idx + 1} of {total_chapters}"
    bbox2 = draw.textbbox((0, 0), info2, font=info_font)
    draw.text(((TARGET_W - (bbox2[2] - bbox2[0])) // 2, line_y + 80), info2, fill=TEXT_COLOR, font=info_font)

    title_text = "RED STORM"
    bbox3 = draw.textbbox((0, 0), title_text, font=small_font)
    draw.text(((TARGET_W - (bbox3[2] - bbox3[0])) // 2, 60), title_text, fill=(120, 120, 120), font=small_font)
    return page

def add_page_number(page, page_num, chapter_num):
    draw = ImageDraw.Draw(page)
    font = get_font(22, bold=False)
    text = f"p.{page_num}  |  Ch.{chapter_num}"
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x, y = TARGET_W - tw - 30, TARGET_H - th - 20
    draw.rectangle([x - 8, y - 5, x + tw + 8, y + th + 5], fill=(20, 20, 20))
    draw.text((x, y), text, fill=(180, 180, 180), font=font)
    return page

def split_tall_image(img):
    iw, ih = img.size
    if ih <= iw * SPLIT_RATIO:
        return [img]
    strip_h = int(iw * 1.4)
    strips = []
    y = 0
    while y < ih:
        end = min(y + strip_h, ih)
        strips.append(img.crop((0, y, iw, end)))
        y = end
    return strips

def save_chapter_pdf(ch_num, ch_path, chapter_idx, total_chapters, global_page_start, tmp_dir):
    """Create a temp PDF for one chapter, return (pages_added, next_global_page)."""
    images = sorted([
        f for f in ch_path.iterdir()
        if f.suffix.lower() in ('.webp', '.jpg', '.jpeg', '.png')
    ])

    pages = []
    gp = global_page_start

    sep = make_chapter_separator(ch_num, len(images), chapter_idx, total_chapters)
    pages.append(sep)
    gp += 1

    for img_path in images:
        img = Image.open(img_path).convert("RGB")
        strips = split_tall_image(img)
        for strip in strips:
            content_page = fit_image_to_page(strip)
            content_page = add_page_number(content_page, gp, ch_num)
            pages.append(content_page)
            gp += 1
        img.close()

    # Save this chapter's pages as a temp PDF
    tmp_pdf = tmp_dir / f"ch_{ch_num}.pdf"
    if pages:
        pages[0].save(tmp_pdf, "PDF", save_all=True, append_images=pages[1:], resolution=150)
    # Free memory
    pages.clear()

    return gp - global_page_start, gp

def main():
    TMP_DIR.mkdir(exist_ok=True)

    chapters = get_chapters()
    total = len(chapters)
    print(f"Found {total} chapters. Processing per-chapter PDFs...")

    global_page = 0
    pdf_files = []

    for idx, (ch_num, ch_path) in enumerate(chapters):
        count, global_page = save_chapter_pdf(ch_num, ch_path, idx, total, global_page, TMP_DIR)
        tmp_pdf = TMP_DIR / f"ch_{ch_num}.pdf"
        pdf_files.append(tmp_pdf)
        print(f"  Chapter {ch_num}: {count} pages → global p.{global_page}", flush=True)

    print(f"\nTotal pages: {global_page}. Merging PDFs...")

    writer = PdfWriter()
    for i, pdf_file in enumerate(pdf_files):
        writer.append(str(pdf_file))
        if (i + 1) % 50 == 0:
            print(f"  Merged {i + 1}/{len(pdf_files)}...", flush=True)

    OUTPUT_PDF.unlink(missing_ok=True)
    with open(OUTPUT_PDF, "wb") as f:
        writer.write(f)

    writer.close()
    size_mb = OUTPUT_PDF.stat().st_size / (1024 * 1024)
    print(f"\nDone! {OUTPUT_PDF} ({size_mb:.1f} MB)")

    # Cleanup
    shutil.rmtree(TMP_DIR)
    print("Temp files cleaned up.")

if __name__ == "__main__":
    main()
