#!/usr/bin/env python3
"""Convert manga folder to CBZ format (ZIP archive of images)."""

import os
import sys
import zipfile
import argparse
from pathlib import Path
from PIL import Image
import io
from concurrent.futures import ProcessPoolExecutor, as_completed


def get_sorted_images(chapter_dir: Path) -> list[Path]:
    extensions = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif'}
    images = [f for f in chapter_dir.iterdir()
              if f.is_file() and f.suffix.lower() in extensions]
    return sorted(images)


def convert_to_jpg(img_path: Path, quality: int = 95) -> bytes:
    with Image.open(img_path) as img:
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')
        buf = io.BytesIO()
        img.save(buf, format='JPEG', quality=quality, optimize=True)
        return buf.getvalue()


def process_image(img_path: Path, index: int, convert: bool, quality: int):
    ext = img_path.suffix.lower()
    if convert and ext in ('.webp', '.bmp', '.gif'):
        data = convert_to_jpg(img_path, quality)
        arcname = f"{index:04d}.jpg"
    elif ext == '.png':
        data = img_path.read_bytes()
        arcname = f"{index:04d}.png"
    else:
        data = img_path.read_bytes()
        arcname = f"{index:04d}{ext}"
    return arcname, data


def _worker_create_cbz(args):
    chapter_dir_str, output_str, convert, quality = args
    chapter_dir = Path(chapter_dir_str)
    output_path = Path(output_str)

    images = get_sorted_images(chapter_dir)
    if not images:
        return False, chapter_dir.name, 0, 0.0

    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_STORED) as zf:
        for i, img_path in enumerate(images):
            arcname, data = process_image(img_path, i + 1, convert, quality)
            zf.writestr(arcname, data)

    size_mb = output_path.stat().st_size / (1024 * 1024)
    return True, chapter_dir.name, len(images), size_mb


def parse_chapter_num(name: str) -> float:
    try:
        return float(name.split('_')[-1])
    except ValueError:
        return 0.0


def _worker_convert_combined(args):
    img_path_str, page_num, ch_num, convert, quality = args
    img_path = Path(img_path_str)
    ext = img_path.suffix.lower()
    if convert and ext in ('.webp', '.bmp', '.gif'):
        data = convert_to_jpg(img_path, quality)
        arcname = f"Ch{ch_num}/{page_num:05d}.jpg"
    elif ext == '.png':
        data = img_path.read_bytes()
        arcname = f"Ch{ch_num}/{page_num:05d}.png"
    else:
        data = img_path.read_bytes()
        arcname = f"Ch{ch_num}/{page_num:05d}{ext}"
    return page_num, arcname, data


def create_combined_cbz(source_dir: Path, output_path: Path,
                        convert_webp: bool = True, quality: int = 95,
                        workers: int = 4):
    chapters = sorted([d for d in source_dir.iterdir()
                       if d.is_dir() and d.name.startswith('Chapter')],
                      key=lambda x: parse_chapter_num(x.name))

    if not chapters:
        print(f"No chapters found in {source_dir}")
        return False

    print(f"Creating combined CBZ from {len(chapters)} chapters ({workers} workers)...")

    tasks = []
    page_num = 0
    for ch_dir in chapters:
        images = get_sorted_images(ch_dir)
        ch_num = ch_dir.name.split('_')[-1]
        for img_path in images:
            page_num += 1
            tasks.append((str(img_path), page_num, ch_num, convert_webp, quality))

    total_pages = page_num
    results = {}

    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_worker_convert_combined, t): t for t in tasks}
        done = 0
        for future in as_completed(futures):
            pnum, arcname, data = future.result()
            results[pnum] = (arcname, data)
            done += 1
            if done % 500 == 0:
                print(f"  Processing... {done}/{total_pages} pages")

    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_STORED) as zf:
        for pnum in range(1, total_pages + 1):
            arcname, data = results[pnum]
            zf.writestr(arcname, data)

    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"✓ {output_path.name} ({total_pages} pages, {size_mb:.1f} MB)")
    return True


def main():
    parser = argparse.ArgumentParser(description='Convert manga folder to CBZ')
    parser.add_argument('source', help='Source manga directory')
    parser.add_argument('-o', '--output', help='Output CBZ path')
    parser.add_argument('--chapter', type=int, help='Convert single chapter only')
    parser.add_argument('--combined', action='store_true', help='Create single combined CBZ')
    parser.add_argument('--no-convert', action='store_true', help='Do not convert webp to jpg')
    parser.add_argument('--quality', type=int, default=95, help='JPG quality (1-100, default: 95)')
    parser.add_argument('--workers', type=int, default=os.cpu_count() or 4, help='Parallel workers')

    args = parser.parse_args()
    source_dir = Path(args.source)

    if not source_dir.is_dir():
        print(f"Error: {source_dir} is not a directory")
        sys.exit(1)

    manga_name = source_dir.name
    output_dir = source_dir.parent
    convert = not args.no_convert

    if args.combined:
        output_path = Path(args.output) if args.output else output_dir / f"{manga_name}.cbz"
        create_combined_cbz(source_dir, output_path, convert_webp=convert, quality=args.quality, workers=args.workers)
    elif args.chapter is not None:
        chapter_dir = source_dir / f"Chapter_{args.chapter}"
        if not chapter_dir.is_dir():
            print(f"Error: {chapter_dir} not found")
            sys.exit(1)
        output_path = Path(args.output) if args.output else output_dir / f"{manga_name}_Ch{args.chapter}.cbz"
        _worker_create_cbz((str(chapter_dir), str(output_path), convert, args.quality))
        print(f"✓ Done")
    else:
        chapters = sorted([d for d in source_dir.iterdir()
                          if d.is_dir() and d.name.startswith('Chapter')],
                         key=lambda x: parse_chapter_num(x.name))

        tasks = []
        for ch_dir in chapters:
            ch_num = ch_dir.name.split('_')[-1]
            cbz_path = output_dir / f"{manga_name}_Ch{ch_num}.cbz"
            tasks.append((str(ch_dir), str(cbz_path), convert, args.quality))

        print(f"Converting {len(tasks)} chapters to CBZ ({args.workers} workers)...")

        success = 0
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(_worker_create_cbz, t): t for t in tasks}
            for future in as_completed(futures):
                ok, name, pages, size = future.result()
                if ok:
                    success += 1
                    print(f"  ✓ {name} ({pages} pages, {size:.1f} MB)")

        print(f"\nDone! {success}/{len(tasks)} chapters converted")


if __name__ == '__main__':
    main()
