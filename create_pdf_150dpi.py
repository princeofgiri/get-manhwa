#!/usr/bin/env python3
"""
Red Storm → 150 DPI PDF
- Target: 702x936 (150 DPI for Allwinner WAVE 7.8")
- Multiprocessing
"""
import os, shutil
import multiprocessing as mp
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
import fitz

INPUT_DIR = Path("./Red-Storm").resolve()
OUTPUT_PDF = Path("./Red-Storm_150dpi.pdf")
TMP_DIR = Path("./_150dpi_tmp")
TARGET_W, TARGET_H = 702, 936
SPLIT_RATIO = 1.8
MARGIN = 15
BG_COLOR = (245, 245, 245)
TEXT_COLOR = (20, 20, 20)
ACCENT_COLOR = (180, 40, 40)
JPEG_QUALITY = 80
PAGES_PER_TOC = 30

FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

def gf(s, b=True):
    p = FONT_BOLD if b else FONT_REG
    return ImageFont.truetype(p, s) if os.path.exists(p) else ImageFont.load_default()

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
    strips, y = [], 0
    while y < ih:
        strips.append(img.crop((0, y, iw, min(y + sh, ih))))
        y += sh
    return strips

def process_chapter(args):
    ch_num, ch_path_str, idx, total, gp_start = args
    ch_path = Path(ch_path_str)
    images = sorted([f for f in ch_path.iterdir() if f.suffix.lower() in ('.webp', '.jpg', '.jpeg', '.png')])

    pages = []
    gp = gp_start

    # Separator
    sep = Image.new("RGB", (TARGET_W, TARGET_H), BG_COLOR)
    d = ImageDraw.Draw(sep)
    tf = gf(36, True); inf = gf(20, False); sf = gf(16, False)
    label = f"Chapter {ch_num}"
    bb = d.textbbox((0, 0), label, font=tf)
    d.text(((TARGET_W - (bb[2] - bb[0])) // 2, TARGET_H // 2 - 70), label, fill=ACCENT_COLOR, font=tf)
    ly = TARGET_H // 2 - 10
    d.line([(TARGET_W // 4, ly), (TARGET_W * 3 // 4, ly)], fill=(180, 180, 180), width=1)
    for txt, dy in [(f"{len(images)} pages", 15), (f"Chapter {idx + 1} of {total}", 40)]:
        b = d.textbbox((0, 0), txt, font=inf)
        d.text(((TARGET_W - (b[2] - b[0])) // 2, ly + dy), txt, fill=TEXT_COLOR, font=inf)
    pages.append(sep)
    gp += 1

    for img_path in images:
        img = Image.open(img_path).convert("RGB")
        img = ImageEnhance.Contrast(img).enhance(1.15)
        for strip in split_tall(img):
            page = Image.new("RGB", (TARGET_W, TARGET_H), BG_COLOR)
            iw, ih = strip.size
            scale = min((TARGET_W - 2 * MARGIN) / iw, (TARGET_H - 2 * MARGIN) / ih)
            nw, nh = max(1, int(iw * scale)), max(1, int(ih * scale))
            page.paste(strip.resize((nw, nh), Image.LANCZOS), ((TARGET_W - nw) // 2, (TARGET_H - nh) // 2))
            # Page number
            draw = ImageDraw.Draw(page)
            fn = gf(12, False)
            txt = f"p.{gp} | Ch.{ch_num}"
            bb = draw.textbbox((0, 0), txt, font=fn)
            tw = bb[2] - bb[0]; th = bb[3] - bb[1]
            px, py = TARGET_W - tw - 10, TARGET_H - th - 8
            draw.rectangle([px-4, py-3, px+tw+4, py+th+3], fill=(220, 220, 220))
            draw.text((px, py), txt, fill=(80, 80, 80), font=fn)
            pages.append(page)
            gp += 1
        img.close()

    tmp_pdf = TMP_DIR / f"ch_{ch_num}.pdf"
    if pages:
        pages[0].save(tmp_pdf, "PDF", save_all=True, append_images=pages[1:], resolution=150, quality=JPEG_QUALITY)
    pages.clear()
    return (ch_num, str(tmp_pdf), gp - gp_start)

def main():
    TMP_DIR.mkdir(exist_ok=True)
    chapters = get_chapters()
    total = len(chapters)
    nw = min(mp.cpu_count(), 12)
    print(f"{total} chapters. Target: {TARGET_W}x{TARGET_H} @ 150 DPI, {nw} workers")

    # Estimate page counts
    gp = 0
    args_list = []
    for idx, (cn, cp) in enumerate(chapters):
        n = len([f for f in cp.iterdir() if f.suffix.lower() in ('.webp', '.jpg', '.jpeg', '.png')])
        args_list.append((cn, str(cp), idx, total, gp))
        gp += 1 + n

    with mp.Pool(nw) as pool:
        results = []
        for r in pool.imap_unordered(process_chapter, args_list):
            results.append(r)
            if len(results) % 50 == 0:
                print(f"  {len(results)}/{total} done", flush=True)
    print(f"  All {total} chapters done")

    print("Merging...")
    final = fitz.open()
    pdf_w = TARGET_W * 72 / 150
    pdf_h = TARGET_H * 72 / 150
    sx = pdf_w / TARGET_W
    sy = pdf_h / TARGET_H

    # TOC
    toc_count = (total + PAGES_PER_TOC - 1) // PAGES_PER_TOC
    for ti in range(toc_count):
        batch = chapters[ti*PAGES_PER_TOC:(ti+1)*PAGES_PER_TOC]
        img = Image.new("RGB", (TARGET_W, TARGET_H), BG_COLOR)
        d = ImageDraw.Draw(img)
        hf = gf(24, True); itf = gf(15, False); sf = gf(12, False)
        hdr = "TABLE OF CONTENTS"
        hb = d.textbbox((0, 0), hdr, font=hf)
        d.text(((TARGET_W-(hb[2]-hb[0]))//2, 20), hdr, fill=ACCENT_COLOR, font=hf)
        tt = "RED STORM"
        tb = d.textbbox((0, 0), tt, font=sf)
        d.text(((TARGET_W-(tb[2]-tb[0]))//2, 55), tt, fill=(150,150,150), font=sf)
        d.line([(30,72),(TARGET_W-30,72)], fill=(180,180,180), width=1)
        y = 85
        for cn, _ in batch:
            ct = f"Chapter {cn}"
            d.text((40, y), ct, fill=TEXT_COLOR, font=itf)
            bp = d.textbbox((0,0), ct, font=itf)
            pt = f"p.{y//20+1}"
            bb = d.textbbox((0,0), pt, font=itf)
            px = TARGET_W-40-(bb[2]-bb[0])
            d.text((px, y), pt, fill=(120,120,120), font=itf)
            y += 21
        img.save(TMP_DIR / f"toc_{ti}.pdf", "PDF", resolution=150, quality=JPEG_QUALITY)
        img.close()

    for i in range(toc_count):
        sub = fitz.open(str(TMP_DIR / f"toc_{i}.pdf"))
        final.insert_pdf(sub)
        sub.close()

    toc_offset = toc_count
    for ch_num, pdf_path, count in sorted(results, key=lambda r: float(r[0])):
        sub = fitz.open(pdf_path)
        final.insert_pdf(sub)
        sub.close()

    # Bookmarks
    bookmark = []
    pg = toc_offset + 1
    results_sorted = sorted(results, key=lambda r: float(r[0]))
    for ch_num, _, count in results_sorted:
        bookmark.append([1, f"Chapter {ch_num}", pg])
        pg += count
    final.set_toc(bookmark)

    # Links
    pgc = toc_offset
    for ti in range(toc_count):
        batch = chapters[ti*PAGES_PER_TOC:(ti+1)*PAGES_PER_TOC]
        page = final[ti]
        y = 85
        for j, (cn, _) in enumerate(batch):
            if pgc < final.page_count:
                rect = fitz.Rect(40*sx, y*sy, (TARGET_W-40)*sx, (y+18)*sy)
                page.insert_link({"kind": fitz.LINK_GOTO, "page": pgc, "from": rect})
            idx_in_results = next(i for i, r in enumerate(results_sorted) if r[0] == cn)
            pgc += results_sorted[idx_in_results][2]
            y += 21

    print("Saving...")
    final.save(str(OUTPUT_PDF))
    final.close()
    shutil.rmtree(TMP_DIR)
    size_mb = OUTPUT_PDF.stat().st_size / (1024*1024)
    print(f"Done! {OUTPUT_PDF} ({size_mb:.1f} MB)")

if __name__ == "__main__":
    mp.set_start_method("fork")
    main()
