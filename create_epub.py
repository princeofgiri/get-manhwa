#!/usr/bin/env python3
"""Convert manga folder to EPUB format with tall image splitting."""

import os
import sys
import zipfile
import argparse
from pathlib import Path
from PIL import Image, ImageEnhance
import io
from concurrent.futures import ProcessPoolExecutor, as_completed

SPLIT_RATIO = 1.8
TARGET_W = 1404
TARGET_H = 1872

MIMETYPE = b'application/epub+zip'

CONTAINER_XML = '''<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>'''

XHTML_TEMPLATE = '''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head>
  <title>{title}</title>
  <style>
    body {{ margin: 0; padding: 0; text-align: center; background: #000; }}
    img {{ width: 100%; height: auto; }}
  </style>
</head>
<body>
  <img src="../images/{image}" alt="{title}"/>
</body>
</html>'''


def get_sorted_images(chapter_dir: Path) -> list[Path]:
    extensions = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif'}
    images = [f for f in chapter_dir.iterdir()
              if f.is_file() and f.suffix.lower() in extensions]
    return sorted(images)


def find_white_gaps(img: Image.Image, min_gap_height: int = 80, brightness_threshold: int = 235) -> list[int]:
    iw, ih = img.size
    if ih < min_gap_height * 2:
        return []
    small = img.resize((1, ih), Image.LANCZOS)
    row_brights = [sum(p) / 3 for p in small.getdata()]
    small.close()

    white_ranges = []
    in_white = False
    start = 0
    for y, avg in enumerate(row_brights):
        if avg > brightness_threshold and not in_white:
            in_white = True
            start = y
        elif avg <= brightness_threshold and in_white:
            in_white = False
            if y - start >= min_gap_height:
                white_ranges.append((start, y - 1))
    if in_white and ih - start >= min_gap_height:
        white_ranges.append((start, ih - 1))

    return [(s + e) // 2 for s, e in white_ranges]


def split_tall(img: Image.Image, max_height: int = 0) -> list[Image.Image]:
    iw, ih = img.size
    sh = max_height if max_height > 0 else int(iw * 1.4)
    if ih <= sh:
        return [img]

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


def crop_whitespace(img: Image.Image, threshold: int = 240, min_content_ratio: float = 0.02) -> Image.Image:
    iw, ih = img.size
    small = img.resize((min(iw, 200), min(ih, 200)), Image.LANCZOS).convert('RGB')
    pixels = list(small.getdata())
    sw, sh = small.size

    rows = []
    for y in range(sh):
        row = pixels[y * sw:(y + 1) * sw]
        bright = sum(p[0] + p[1] + p[2] for p in row) / (len(row) * 3)
        variance = sum((sum(p) / 3 - bright) ** 2 for p in row) / len(row)
        rows.append(bright > threshold and variance < 50)

    cols = []
    for x in range(sw):
        col = [pixels[y * sw + x] for y in range(sh)]
        bright = sum(p[0] + p[1] + p[2] for p in col) / (len(col) * 3)
        variance = sum((sum(p) / 3 - bright) ** 2 for p in col) / len(col)
        cols.append(bright > threshold and variance < 50)

    top, bottom = 0, sh
    for y in range(sh):
        if not rows[y]:
            top = y
            break
    for y in range(sh - 1, -1, -1):
        if not rows[y]:
            bottom = y
            break

    left, right = 0, sw
    for x in range(sw):
        if not cols[x]:
            left = x
            break
    for x in range(sw - 1, -1, -1):
        if not cols[x]:
            right = x
            break

    margin = 3
    top = max(0, top - margin)
    bottom = min(sh - 1, bottom + margin)
    left = max(0, left - margin)
    right = min(sw - 1, right + margin)

    sx, sy = iw / sw, ih / sh
    crop_box = (int(left * sx), int(top * sy), int((right + 1) * sx), int((bottom + 1) * sy))
    crop_box = (max(0, crop_box[0]), max(0, crop_box[1]),
                min(iw, crop_box[2]), min(ih, crop_box[3]))

    cw = crop_box[2] - crop_box[0]
    ch = crop_box[3] - crop_box[1]
    if cw < iw * min_content_ratio or ch < ih * min_content_ratio:
        return img

    return img.crop(crop_box)


def img_to_jpg_bytes(img: Image.Image, quality: int = 95) -> bytes:
    buf = io.BytesIO()
    if img.mode in ('RGBA', 'P'):
        img = img.convert('RGB')
    img.save(buf, format='JPEG', quality=quality, optimize=True)
    return buf.getvalue()


def is_grayscale(img: Image.Image, threshold: int = 10) -> bool:
    small = img.resize((50, 50), Image.LANCZOS).convert('RGB')
    pixels = list(small.getdata())
    color_pixels = 0
    for r, g, b in pixels:
        if abs(r - g) > threshold or abs(g - b) > threshold or abs(r - b) > threshold:
            color_pixels += 1
    return color_pixels < len(pixels) * 0.05


def process_image_task(args):
    img_path_str, _, quality, arcname_base, target_w, target_h = args
    img_path = Path(img_path_str)
    try:
        img = Image.open(img_path).convert('RGB')
        img = ImageEnhance.Contrast(img).enhance(1.15)
    except Exception:
        return [(arcname_base + '.jpg', b'')]

    if is_grayscale(img):
        img = img.convert('L').convert('RGB')

    img = crop_whitespace(img)

    iw, ih = img.size
    if iw > 0 and ih > 0 and iw != target_w:
        scale = target_w / iw
        nw, nh = target_w, max(1, int(ih * scale))
        img = img.resize((nw, nh), Image.LANCZOS)

    strips = split_tall(img, target_h)
    results = []
    if len(strips) == 1:
        results.append((arcname_base + '.jpg', img_to_jpg_bytes(strips[0], quality)))
    else:
        for i, strip in enumerate(strips):
            results.append((f"{arcname_base}_s{i:02d}.jpg", img_to_jpg_bytes(strip, quality)))
    return results


def parse_chapter_num(name: str) -> float:
    try:
        return float(name.split('_')[-1])
    except ValueError:
        return 0.0


def create_epub(source_dir: Path, output_path: Path, chapter_start: int,
                chapter_end: int, quality: int = 95, workers: int = 4,
                dpi: int = 150):
    manga_name = source_dir.name

    all_chapters = sorted([d for d in source_dir.iterdir()
                           if d.is_dir() and d.name.startswith('Chapter')],
                          key=lambda x: parse_chapter_num(x.name))

    chapters = [d for d in all_chapters
                if chapter_start <= parse_chapter_num(d.name) <= chapter_end]

    if not chapters:
        print(f"No chapters found in range {chapter_start}-{chapter_end}")
        return False

    target_w = int(7.8 * dpi)
    target_h = int(10.4 * dpi)
    print(f"Converting {len(chapters)} chapters to EPUB ({workers} workers, {dpi} DPI = {target_w}x{target_h})...")

    tasks = []
    chapters_info = []

    for ch_dir in chapters:
        images = get_sorted_images(ch_dir)
        ch_num = ch_dir.name.split('_')[-1]
        ch_task_indices = []
        for idx, img_path in enumerate(images):
            arcname_base = f"ch{ch_num}_p{idx:04d}"
            tasks.append((str(img_path), True, quality, arcname_base, target_w, target_h))
            ch_task_indices.append(arcname_base)
        chapters_info.append((ch_num, ch_task_indices))

    all_results = {}
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(process_image_task, t): t for t in tasks}
        done = 0
        for future in as_completed(futures):
            strips = future.result()
            for arcname, data in strips:
                all_results[arcname] = data
            done += 1
            if done % 500 == 0:
                print(f"  Processing... {done}/{len(tasks)} images")

    print(f"  Building EPUB archive...")

    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('mimetype', MIMETYPE, compress_type=zipfile.ZIP_STORED)
        zf.writestr('META-INF/container.xml', CONTAINER_XML)

        manifest_lines = []
        spine_lines = []
        toc_ncx_items = []
        nav_items = []
        page_list_items = []
        page_list_ncx_items = []
        global_page = 0

        for ch_idx, (ch_num, task_indices) in enumerate(chapters_info):
            ch_title = f"Chapter {ch_num}"

            first_xhref = None
            first_page_of_chapter = 0
            for arcname_base in task_indices:
                matching = sorted([k for k in all_results if k.startswith(arcname_base)])
                for strip_name in matching:
                    global_page += 1
                    if first_page_of_chapter == 0:
                        first_page_of_chapter = global_page
                    item_id = f"ch{ch_num}_img{global_page}"
                    xhref = f"text/ch{ch_num}_p{global_page:04d}.xhtml"
                    xid = f"xhtml_{global_page}"

                    if first_xhref is None:
                        first_xhref = xhref

                    manifest_lines.append(f'    <item id="{item_id}" href="images/{strip_name}" media-type="image/jpeg"/>')
                    manifest_lines.append(f'    <item id="{xid}" href="{xhref}" media-type="application/xhtml+xml"/>')
                    spine_lines.append(f'    <itemref idref="{xid}"/>')

                    page_title = f"{ch_title} - Page {global_page}"
                    xhtml = XHTML_TEMPLATE.format(title=page_title, image=strip_name)
                    zf.writestr(f'OEBPS/{xhref}', xhtml)
                    zf.writestr(f'OEBPS/images/{strip_name}', all_results[strip_name])

            nav_items.append(f'      <li><a href="{first_xhref}">{ch_title} ({first_page_of_chapter})</a></li>')
            page_list_items.append(f'      <li><a href="{first_xhref}">{first_page_of_chapter}</a></li>')
            page_list_ncx_items.append(f'    <pageTarget id="page_{first_page_of_chapter}" value="{first_page_of_chapter}" type="normal" playOrder="{ch_idx+1}">\n      <navLabel><text>{ch_title} (p.{first_page_of_chapter})</text></navLabel>\n      <content src="{first_xhref}"/>\n    </pageTarget>')
            toc_ncx_items.append(f'    <navPoint id="navPoint-{ch_idx+1}" playOrder="{ch_idx+1}">\n      <navLabel><text>{ch_title} (p.{first_page_of_chapter})</text></navLabel>\n      <content src="{first_xhref}"/>\n    </navPoint>')

        manifest = '\n'.join(manifest_lines)
        spine = '\n'.join(spine_lines)

        nav_xhtml = f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head>
  <title>Table of Contents</title>
</head>
<body>
  <nav epub:type="toc" id="toc">
    <h1>Table of Contents</h1>
    <ol>
{chr(10).join(nav_items)}
    </ol>
  </nav>
  <nav epub:type="page-list" hidden="hidden">
    <ol>
{chr(10).join(page_list_items)}
    </ol>
  </nav>
</body>
</html>'''
        zf.writestr('OEBPS/nav.xhtml', nav_xhtml)
        manifest_lines.append('    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>')

        toc_ncx = f'''<?xml version="1.0" encoding="UTF-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head>
    <meta name="dtb:uid" content="urn:uuid:{manga_name}"/>
    <meta name="dtb:depth" content="1"/>
    <meta name="dtb:totalPageCount" content="{global_page}"/>
    <meta name="dtb:maxPageNumber" content="{global_page}"/>
  </head>
  <docTitle><text>{manga_name}</text></docTitle>
  <navMap>
{chr(10).join(toc_ncx_items)}
  </navMap>
  <pageList>
    <navLabel><text>Pages</text></navLabel>
{chr(10).join(page_list_ncx_items)}
  </pageList>
</ncx>'''
        zf.writestr('OEBPS/toc.ncx', toc_ncx)
        manifest_lines.append('    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>')

        manifest = '\n'.join(manifest_lines)

        content_opf = f'''<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="BookId" version="3.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>{manga_name}</dc:title>
    <dc:language>en</dc:language>
    <dc:identifier id="BookId">urn:uuid:{manga_name}</dc:identifier>
  </metadata>
  <manifest>
{manifest}
  </manifest>
  <spine toc="ncx">
{spine}
  </spine>
</package>'''
        zf.writestr('OEBPS/content.opf', content_opf)

    size_mb = output_path.stat().st_size / (1024 * 1024)
    total_pages = len(spine_lines)
    print(f"✓ {output_path.name} ({total_pages} pages, {size_mb:.1f} MB)")
    return True


def main():
    parser = argparse.ArgumentParser(description='Convert manga folder to EPUB')
    parser.add_argument('source', help='Source manga directory')
    parser.add_argument('-o', '--output', help='Output EPUB path')
    parser.add_argument('--start', type=int, default=0, help='Start chapter (default: 0)')
    parser.add_argument('--end', type=int, default=99999, help='End chapter (default: 99999)')
    parser.add_argument('--quality', type=int, default=95, help='JPG quality (1-100, default: 95)')
    parser.add_argument('--dpi', type=int, default=150, help='Target DPI for 7.8" screen (default: 150)')
    parser.add_argument('--workers', type=int, default=os.cpu_count() or 4, help='Parallel workers')

    args = parser.parse_args()
    source_dir = Path(args.source)

    if not source_dir.is_dir():
        print(f"Error: {source_dir} is not a directory")
        sys.exit(1)

    manga_name = source_dir.name
    output_dir = source_dir.parent

    if args.end < args.start:
        print("Error: --end must be >= --start")
        sys.exit(1)

    range_name = f"{manga_name}_{args.start}-{args.end}" if args.start > 0 or args.end < 99999 else manga_name
    output_path = Path(args.output) if args.output else output_dir / f"{range_name}.epub"

    create_epub(source_dir, output_path, args.start, args.end,
                quality=args.quality, workers=args.workers, dpi=args.dpi)


if __name__ == '__main__':
    main()
