#!/usr/bin/env python3
"""
Red Storm → E-ink optimized PDF (multiprocess)
- Target: 1404x1872 (Allwinner WAVE 7.8" e-ink, 300 DPI)
- multiprocessing for chapter generation
- TOC + bookmarks + clickable links
"""

import os
import re
import shutil
import multiprocessing as mp
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
import fitz

INPUT_DIR = Path("./Red-Storm").resolve()
OUTPUT_PDF = Path("./Red-Storm_Eink.pdf")
TMP_DIR = Path("./_eink_tmp")
TARGET_W, TARGET_H = 1404, 1872
SPLIT_RATIO = 1.8
MARGIN = 30
BG_COLOR = (245, 245, 245)
TEXT_COLOR = (20, 20, 20)
ACCENT_COLOR = (180, 40, 40)
JPEG_QUALITY = 85
CONTRAST_FACTOR = 1.15
PAGES_PER_TOC = 30

FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

def get_font(size, bold=True):
    p = FONT_BOLD if bold else FONT_REG
    if os.path.exists(p):
        return ImageFont.truetype(p, size)
    return ImageFont.load_default()

def get_chapters():
    chapters = []
    for p in sorted(INPUT_DIR.iterdir()):
        if p.is_dir() and p.name.startswith("Chapter_"):
            ch_num = p.name.replace("Chapter_", "")
            chapters.append((ch_num, p))
    chapters.sort(key=lambda x: float(x[0]))
    return chapters

def make_separator(ch_num, image_count, chapter_idx, total):
    page = Image.new("RGB", (TARGET_W, TARGET_H), BG_COLOR)
    draw = ImageDraw.Draw(page)
    tf = get_font(72, True)
    inf = get_font(40, False)
    sf = get_font(32, False)
    label = f"Chapter {ch_num}"
    bb = draw.textbbox((0, 0), label, font=tf)
    draw.text(((TARGET_W - (bb[2] - bb[0])) // 2, TARGET_H // 2 - 140), label, fill=ACCENT_COLOR, font=tf)
    ly = TARGET_H // 2 - 20
    draw.line([(TARGET_W // 4, ly), (TARGET_W * 3 // 4, ly)], fill=(180, 180, 180), width=2)
    for txt, dy in [(f"{image_count} pages", 30), (f"Chapter {chapter_idx + 1} of {total}", 80)]:
        b = draw.textbbox((0, 0), txt, font=inf)
        draw.text(((TARGET_W - (b[2] - b[0])) // 2, ly + dy), txt, fill=TEXT_COLOR, font=inf)
    tt = "RED STORM"
    b3 = draw.textbbox((0, 0), tt, font=sf)
    draw.text(((TARGET_W - (b3[2] - b3[0])) // 2, 80), tt, fill=(150, 150, 150), font=sf)
    return page

def add_page_number(page, pnum, ch):
    draw = ImageDraw.Draw(page)
    font = get_font(24, False)
    text = f"p.{pnum}  |  Ch.{ch}"
    bb = draw.textbbox((0, 0), text, font=font)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    x, y = TARGET_W - tw - 30, TARGET_H - th - 20
    draw.rectangle([x - 8, y - 5, x + tw + 8, y + th + 5], fill=(220, 220, 220))
    draw.text((x, y), text, fill=(80, 80, 80), font=font)
    return page

def split_tall(img):
    iw, ih = img.size
    if ih <= iw * SPLIT_RATIO:
        return [img]
    sh = int(iw * 1.4)
    strips, y = [], 0
    while y < ih:
        strips.append(img.crop((0, y, iw, min(y + sh, ih))))
        y += sh
    return strips

def process_chapter(args):
    """Process one chapter in a worker process. Returns (ch_num, pdf_path, page_count)."""
    ch_num, ch_path_str, chapter_idx, total, global_page_start = args
    ch_path = Path(ch_path_str)
    tmp_dir = TMP_DIR

    images = sorted([f for f in ch_path.iterdir() if f.suffix.lower() in ('.webp', '.jpg', '.jpeg', '.png')])

    pages = []
    gp = global_page_start

    sep = make_separator(ch_num, len(images), chapter_idx, total)
    pages.append(sep)
    gp += 1

    for img_path in images:
        img = Image.open(img_path).convert("RGB")
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(CONTRAST_FACTOR)
        for strip in split_tall(img):
            page = Image.new("RGB", (TARGET_W, TARGET_H), BG_COLOR)
            iw, ih = strip.size
            scale = min((TARGET_W - 2 * MARGIN) / iw, (TARGET_H - 2 * MARGIN) / ih)
            nw, nh = int(iw * scale), int(ih * scale)
            resized = strip.resize((nw, nh), Image.LANCZOS)
            page.paste(resized, ((TARGET_W - nw) // 2, (TARGET_H - nh) // 2))
            page = add_page_number(page, gp, ch_num)
            pages.append(page)
            gp += 1
        img.close()

    tmp_pdf = tmp_dir / f"ch_{ch_num}.pdf"
    if pages:
        pages[0].save(tmp_pdf, "PDF", save_all=True, append_images=pages[1:],
                      resolution=300, quality=JPEG_QUALITY)
    pages.clear()
    return (ch_num, str(tmp_pdf), gp - global_page_start, global_page_start)

def main():
    TMP_DIR.mkdir(exist_ok=True)
    chapters = get_chapters()
    total = len(chapters)
    num_workers = min(mp.cpu_count(), 12)
    print(f"Found {total} chapters. Target: {TARGET_W}x{TARGET_H} @ 300 DPI")
    print(f"Using {num_workers} workers (CPU count: {mp.cpu_count()})")

    # Calculate global page starts
    args_list = []
    gp = 0
    for idx, (ch_num, ch_path) in enumerate(chapters):
        n_images = len([f for f in ch_path.iterdir() if f.suffix.lower() in ('.webp', '.jpg', '.jpeg', '.png')])
        page_count = 1 + n_images  # separator + images (approx)
        args_list.append((ch_num, str(ch_path), idx, total, gp))
        gp += page_count

    print(f"Estimated {gp} pages. Processing with {num_workers} workers...")

    results = [None] * len(args_list)
    with mp.Pool(num_workers) as pool:
        for i, result in enumerate(pool.imap_unordered(process_chapter, args_list)):
            ch_num, pdf_path, count, start_pg = result
            results[i] = (ch_num, pdf_path, count, start_pg)
            print(f"  Done: Chapter {ch_num} ({count} pages)", flush=True)

    print(f"\nAll chapters done. Merging...")
    final = fitz.open()

    pdf_w = TARGET_W * 72 / 300
    pdf_h = TARGET_H * 72 / 300

    # Create TOC pages
    print("Creating TOC pages...")
    toc_page_count = (total + PAGES_PER_TOC - 1) // PAGES_PER_TOC
    for toc_idx in range(toc_page_count):
        batch_start = toc_idx * PAGES_PER_TOC
        batch_end = min(batch_start + PAGES_PER_TOC, total)
        batch = chapters[batch_start:batch_end]
        toc_img = Image.new("RGB", (TARGET_W, TARGET_H), BG_COLOR)
        draw = ImageDraw.Draw(toc_img)
        hdr_font = get_font(48, True)
        item_font = get_font(30, False)
        small_font = get_font(24, False)

        hdr = "TABLE OF CONTENTS"
        hb = draw.textbbox((0, 0), hdr, font=hdr_font)
        draw.text(((TARGET_W - (hb[2] - hb[0])) // 2, 40), hdr, fill=ACCENT_COLOR, font=hdr_font)
        tt = "RED STORM"
        tb = draw.textbbox((0, 0), tt, font=small_font)
        draw.text(((TARGET_W - (tb[2] - tb[0])) // 2, 105), tt, fill=(150, 150, 150), font=small_font)
        draw.line([(60, 145), (TARGET_W - 60, 145)], fill=(180, 180, 180), width=1)
        y = 170
        for ch_num, _ in batch:
            ch_text = f"Chapter {ch_num}"
            draw.text((80, y), ch_text, fill=TEXT_COLOR, font=item_font)
            b_pg = draw.textbbox((0, 0), ch_text, font=item_font)
            dots_x = b_pg[2] + 20
            pg_text = f"p. {y // 40 + 1}"
            bbox_pg = draw.textbbox((0, 0), pg_text, font=item_font)
            pg_x = TARGET_W - 80 - (bbox_pg[2] - bbox_pg[0])
            draw.text((pg_x, y), pg_text, fill=(120, 120, 120), font=item_font)
            for dx in range(int(dots_x), int(pg_x) - 15, 12):
                draw.rectangle([dx, y + 14, dx + 4, y + 16], fill=(180, 180, 180))
            y += 42
        toc_img.save(TMP_DIR / f"toc_{toc_idx}.pdf", "PDF", resolution=300, quality=JPEG_QUALITY)
        toc_img.close()

    # Insert TOC pages
    for i in range(toc_page_count):
        sub = fitz.open(str(TMP_DIR / f"toc_{i}.pdf"))
        final.insert_pdf(sub)
        sub.close()

    toc_offset = toc_page_count

    # Insert chapter pages in order
    for ch_num, pdf_path, count, start_pg in results:
        sub = fitz.open(pdf_path)
        final.insert_pdf(sub)
        sub.close()

    # Bookmarks
    print("Adding bookmarks...")
    bookmark_toc = []
    pg = toc_offset + 1
    for ch_num, pdf_path, count, start_pg in results:
        bookmark_toc.append([1, f"Chapter {ch_num}", pg])
        pg += count
    final.set_toc(bookmark_toc)

    # Clickable TOC links
    print("Adding clickable links...")
    sx = pdf_w / TARGET_W
    sy = pdf_h / TARGET_H
    pg_counter = toc_offset
    for toc_idx in range(toc_page_count):
        batch_start = toc_idx * PAGES_PER_TOC
        batch_end = min(batch_start + PAGES_PER_TOC, total)
        batch = chapters[batch_start:batch_end]
        page = final[toc_idx]
        y_start = 170
        for ch_num, _ in batch:
            target = pg_counter
            if target < final.page_count:
                rect = fitz.Rect(80 * sx, y_start * sy, (TARGET_W - 80) * sx, (y_start + 35) * sy)
                page.insert_link({"kind": fitz.LINK_GOTO, "page": target, "from": rect})
            r = next((r for r in results if r[0] == ch_num), None)
            pg_counter += r[2] if r else 0
            y_start += 42

    print("Saving...")
    OUTPUT_PDF.unlink(missing_ok=True)
    final.save(str(OUTPUT_PDF))
    final.close()

    shutil.rmtree(TMP_DIR)
    size_mb = OUTPUT_PDF.stat().st_size / (1024 * 1024)
    print(f"\nDone! {OUTPUT_PDF} ({size_mb:.1f} MB)")

if __name__ == "__main__":
    mp.set_start_method("fork")
    main()
