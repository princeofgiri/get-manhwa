#!/usr/bin/env python3
"""
Red Storm Manhwa PDF Builder
Usage: python3 build_pdf.py <dpi>
  dpi: 150 or 300
"""

import os
import sys
import shutil
import statistics
import argparse
import multiprocessing as mp
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
import fitz
from create_epub import find_white_gaps

INPUT_DIR = Path(os.environ.get("INPUT_DIR", "./Red-Storm")).resolve()
TMP_DIR = Path(f"./_build_tmp")
SPLIT_RATIO = 1.8
BG_COLOR = (245, 245, 245)
TEXT_COLOR = (20, 20, 20)
ACCENT_COLOR = (180, 40, 40)
JPEG_QUALITY = 80
PAGES_PER_TOC = 30
SKIP_ADS = True

FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

def gf(s, b=True):
    p = FONT_BOLD if b else FONT_REG
    return ImageFont.truetype(p, s) if os.path.exists(p) else ImageFont.load_default()

def is_ad_page(img_path):
    """Detect promo/ad/credit pages from scan groups."""
    try:
        img = Image.open(img_path).convert("RGB")
        w, h = img.size
        small = img.resize((30, 30))
        pixels = list(small.getdata())

        avg_b = sum(sum(p) / 3 for p in pixels) / len(pixels)

        # Dark promo: low brightness, low variance, small image
        if avg_b < 110 and variance < 800 and w < 800:
            img.close()
            return True
        # Dark solid promo (low variance = few colors = promo, not manga)
        if avg_b < 80 and solid > 85 and variance < 2000 and w < 800:
            img.close()
            return True
        # White/spacer promo: very high solid, small
        if solid > 95 and variance < 500 and max(w, h) < 1300:
            img.close()
            return True
        # Dark solid promo
        if avg_b < 80 and solid > 70 and w < 800:
            img.close()
            return True
        # White/spacer promo: very high solid
        if solid > 90 and max(w, h) < 1300:
            img.close()
            return True

        # Colorful promo: landscape + colorful (not grayscale manga)
        if w > h * 1.2 and w < 1200:
            colorful = sum(1 for p in pixels if max(abs(p[0] - p[1]), abs(p[0] - p[2]), abs(p[1] - p[2])) > 30)
            if colorful / len(pixels) * 100 > 25:
                img.close()
                return True

        img.close()
    except Exception:
        pass
    return False

def get_chapters():
    chs = []
    for p in sorted(INPUT_DIR.iterdir()):
        if p.is_dir() and p.name.startswith("Chapter_"):
            chs.append((p.name.replace("Chapter_", ""), p))
    chs.sort(key=lambda x: float(x[0]))
    return chs

def split_tall(img):
    iw, ih = img.size
    if ih <= iw * SPLIT_RATIO:
        return [img]

    sh = int(iw * 1.4)
    gaps = find_white_gaps(img)
    if not gaps:
        strips, y = [], 0
        while y < ih:
            strips.append(img.crop((0, y, iw, min(y + sh, ih))))
            y += sh
        return strips

    min_height = int(sh * 0.7)
    split_points = [0]
    y = sh
    while y < ih:
        remaining_total = ih - split_points[-1]
        if remaining_total <= sh * 1.5:
            break
        search_range = int(sh * 0.45)
        best, best_score = y, float('inf')
        prev = split_points[-1]
        remaining = ih - prev
        mid = prev + remaining // 2
        for gap_center in gaps:
            if gap_center <= prev + 50 or gap_center >= ih - 20:
                continue
            dist = abs(gap_center - y)
            if dist > search_range:
                continue
            if gap_center - prev < min_height:
                continue
            next_strip_min = ih - gap_center
            if next_strip_min < min_height:
                continue
            balance = abs(gap_center - mid)
            score = balance + dist * 0.5
            if score < best_score:
                best, best_score = gap_center, score
        split_points.append(best)
        y = best + sh
    split_points.append(ih)

    if len(split_points) > 2 and (split_points[-1] - split_points[-2]) < min_height:
        split_points.pop(-2)

    return [img.crop((0, split_points[i], iw, split_points[i + 1]))
            for i in range(len(split_points) - 1)]

def process_chapter(args):
    ch_num, ch_path_str, idx, total, gp_start, tw, th, margin, grayscale = args
    ch_path = Path(ch_path_str)
    images = sorted([f for f in ch_path.iterdir() if f.suffix.lower() in ('.webp', '.jpg', '.jpeg', '.png')])

    # Filter out ad/promo pages
    if SKIP_ADS:
        filtered = [f for f in images if not is_ad_page(f)]
        skipped_ads = len(images) - len(filtered)
        if skipped_ads > 0:
            images = filtered

    pages = []
    gp = gp_start

    sep = Image.new("RGB", (tw, th), BG_COLOR)
    d = ImageDraw.Draw(sep)
    tf = gf(max(18, tw // 20), True)
    inf = gf(max(10, tw // 35), False)
    sf = gf(max(8, tw // 45), False)
    label = f"Chapter {ch_num}"
    bb = d.textbbox((0, 0), label, font=tf)
    d.text(((tw - (bb[2] - bb[0])) // 2, th // 2 - th // 13), label, fill=ACCENT_COLOR, font=tf)
    ly = th // 2 - th // 50
    d.line([(tw // 4, ly), (tw * 3 // 4, ly)], fill=(180, 180, 180), width=max(1, tw // 500))
    for txt, dy in [(f"{len(images)} pages", th // 70), (f"Chapter {idx + 1} of {total}", th // 30)]:
        b = d.textbbox((0, 0), txt, font=inf)
        d.text(((tw - (b[2] - b[0])) // 2, ly + dy), txt, fill=TEXT_COLOR, font=inf)
    pages.append(sep)
    gp += 1

    for img_path in images:
        try:
            img = Image.open(img_path).convert("RGB")
            img = ImageEnhance.Contrast(img).enhance(1.15)
            if grayscale:
                img = img.convert("L").convert("RGB")
        except Exception:
            continue
        for strip in split_tall(img):
            page = Image.new("RGB", (tw, th), BG_COLOR)
            iw, ih = strip.size
            if iw <= 0 or ih <= 0:
                continue
            scale = min((tw - 2 * margin) / iw, (th - 2 * margin) / ih)
            nw, nh = max(1, int(iw * scale)), max(1, int(ih * scale))
            page.paste(strip.resize((nw, nh), Image.LANCZOS), ((tw - nw) // 2, (th - nh) // 2))
            draw = ImageDraw.Draw(page)
            fn = gf(max(8, tw // 60), False)
            txt = f"p.{gp} | Ch.{ch_num}"
            bb = draw.textbbox((0, 0), txt, font=fn)
            twt, tht = bb[2] - bb[0], bb[3] - bb[1]
            px, py = tw - twt - max(5, tw // 70), th - tht - max(3, th // 100)
            draw.rectangle([px - 4, py - 3, px + twt + 4, py + tht + 3], fill=(220, 220, 220))
            draw.text((px, py), txt, fill=(80, 80, 80), font=fn)
            pages.append(page)
            gp += 1
        img.close()

    tmp_pdf = TMP_DIR / f"ch_{ch_num}.pdf"
    if pages:
        pages[0].save(tmp_pdf, "PDF", save_all=True, append_images=pages[1:], resolution=150, quality=JPEG_QUALITY)
    pages.clear()
    return (ch_num, str(tmp_pdf), gp - gp_start)

def build(dpi, grayscale=False):
    if dpi not in (150, 300):
        print(f"Usage: python3 build_pdf.py <150|300>")
        sys.exit(1)

    if dpi == 300:
        TARGET_W, TARGET_H = 1404, 1872
    else:
        TARGET_W, TARGET_H = 702, 936

    MARGIN = max(15, TARGET_W // 47)
    MANGA_NAME = INPUT_DIR.name
    suffix = "_gray" if grayscale else ""
    OUTPUT_PDF = Path(f"./{MANGA_NAME}_{dpi}dpi{suffix}.pdf")
    TMP_DIR.mkdir(exist_ok=True)

    chapters = get_chapters()
    total = len(chapters)
    nw = min(mp.cpu_count(), 12)
    print(f"Building {dpi} DPI: {TARGET_W}x{TARGET_H}, {total} chapters, {nw} workers, grayscale={grayscale}")

    gp = 0
    args_list = []
    for idx, (cn, cp) in enumerate(chapters):
        n = len([f for f in cp.iterdir() if f.suffix.lower() in ('.webp', '.jpg', '.jpeg', '.png')])
        args_list.append((cn, str(cp), idx, total, gp, TARGET_W, TARGET_H, MARGIN, grayscale))
        gp += 1 + n

    with mp.Pool(nw) as pool:
        results = []
        for r in pool.imap_unordered(process_chapter, args_list):
            results.append(r)
            if len(results) % 50 == 0:
                print(f"  {len(results)}/{total} chapters done", flush=True)
    print(f"  All {total} chapters done")

    print("Merging...")
    final = fitz.open()
    pdf_w = TARGET_W * 72 / dpi
    pdf_h = TARGET_H * 72 / dpi
    sx = pdf_w / TARGET_W
    sy = pdf_h / TARGET_H

    toc_count = (total + PAGES_PER_TOC - 1) // PAGES_PER_TOC
    for ti in range(toc_count):
        batch = chapters[ti * PAGES_PER_TOC:(ti + 1) * PAGES_PER_TOC]
        img = Image.new("RGB", (TARGET_W, TARGET_H), BG_COLOR)
        d = ImageDraw.Draw(img)
        hf = gf(max(12, TARGET_W // 15), True)
        itf = gf(max(8, TARGET_W // 23), False)
        sf = gf(max(6, TARGET_W // 30), False)
        hdr = "TABLE OF CONTENTS"
        hb = d.textbbox((0, 0), hdr, font=hf)
        d.text(((TARGET_W - (hb[2] - hb[0])) // 2, max(20, TARGET_H // 35)), hdr, fill=ACCENT_COLOR, font=hf)
        tt = "RED STORM"
        tb = d.textbbox((0, 0), tt, font=sf)
        d.text(((TARGET_W - (tb[2] - tb[0])) // 2, max(40, TARGET_H // 15)), tt, fill=(150, 150, 150), font=sf)
        sep_y = max(55, TARGET_H // 12)
        d.line([(MARGIN, sep_y), (TARGET_W - MARGIN, sep_y)], fill=(180, 180, 180), width=1)
        y = sep_y + max(10, TARGET_H // 60)
        row = max(15, TARGET_H // 35)
        for cn, _ in batch:
            ct = f"Chapter {cn}"
            d.text((max(30, TARGET_W // 25), y), ct, fill=TEXT_COLOR, font=itf)
            bp = d.textbbox((0, 0), ct, font=itf)
            pt = f"p.{y // row + 1}"
            bb = d.textbbox((0, 0), pt, font=itf)
            px = TARGET_W - max(30, TARGET_W // 25) - (bb[2] - bb[0])
            d.text((px, y), pt, fill=(120, 120, 120), font=itf)
            y += row
        img.save(TMP_DIR / f"toc_{ti}.pdf", "PDF", resolution=150, quality=JPEG_QUALITY)
        img.close()

    for i in range(toc_count):
        sub = fitz.open(str(TMP_DIR / f"toc_{i}.pdf"))
        final.insert_pdf(sub)
        sub.close()

    toc_offset = toc_count
    results_sorted = sorted(results, key=lambda r: float(r[0]))
    for ch_num, pdf_path, count in results_sorted:
        sub = fitz.open(pdf_path)
        final.insert_pdf(sub)
        sub.close()

    bookmark = []
    pg = toc_offset + 1
    for ch_num, _, count in results_sorted:
        bookmark.append([1, f"Chapter {ch_num}", pg])
        pg += count
    final.set_toc(bookmark)

    pgc = toc_offset
    for ti in range(toc_count):
        batch = chapters[ti * PAGES_PER_TOC:(ti + 1) * PAGES_PER_TOC]
        page = final[ti]
        y = sep_y + max(10, TARGET_H // 60)
        for j, (cn, _) in enumerate(batch):
            if pgc < final.page_count:
                rect = fitz.Rect(max(30, TARGET_W // 25) * sx, y * sy, (TARGET_W - max(30, TARGET_W // 25)) * sx, (y + row - 3) * sy)
                page.insert_link({"kind": fitz.LINK_GOTO, "page": pgc, "from": rect})
            idx_r = next((i for i, r in enumerate(results_sorted) if r[0] == cn), None)
            if idx_r is not None:
                pgc += results_sorted[idx_r][2]
            y += row

    print("Saving...")
    OUTPUT_PDF.unlink(missing_ok=True)
    final.save(str(OUTPUT_PDF))
    final.close()
    shutil.rmtree(TMP_DIR)
    size_mb = OUTPUT_PDF.stat().st_size / (1024 * 1024)
    print(f"Done! {OUTPUT_PDF} ({size_mb:.1f} MB)")

if __name__ == "__main__":
    mp.set_start_method("fork")
    parser = argparse.ArgumentParser(description="Build manga PDF")
    parser.add_argument("dpi", type=int, choices=[150, 300], help="Output DPI (150 or 300)")
    parser.add_argument("--grayscale", "-g", action="store_true", help="Convert images to grayscale (smaller file)")
    args = parser.parse_args()
    build(args.dpi, grayscale=args.grayscale)
