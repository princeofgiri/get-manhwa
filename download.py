#!/usr/bin/env python3
"""
Universal Manga Downloader for roliascan.com (multiprocess)

Usage:
    python3 download.py https://roliascan.com/manga/one-piece/
    python3 download.py https://roliascan.com/manga/one-piece/ ./One-Piece/
    python3 download.py https://roliascan.com/manga/one-piece/ --workers 4
"""

import os
import sys
import json
import hashlib
import time
import datetime
import argparse
import urllib.request
import urllib.error
from pathlib import Path
from multiprocessing import Pool

BASE_URL = "https://roliascan.com"
RETRY = 3
TIMEOUT = 30


def generate_token():
    ts = int(time.time())
    hour = datetime.datetime.now(datetime.UTC).strftime("%Y%m%d%H")
    secret = f"mng_ch_{hour}"
    token = hashlib.md5(f"{ts}{secret}".encode()).hexdigest()[:16]
    return ts, token


def fetch_json(url, retries=RETRY):
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                return json.loads(resp.read())
        except Exception:
            if attempt < retries - 1:
                time.sleep(2)
    return None


def download_file(url, filepath, retries=RETRY):
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=TIMEOUT * 3) as resp:
                data = resp.read()
                if len(data) > 0:
                    with open(filepath, "wb") as f:
                        f.write(data)
                    return True
        except Exception:
            if attempt < retries - 1:
                time.sleep(2)
    return False


def extract_manga_id(slug):
    url = f"{BASE_URL}/manga/{slug}/"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        import re
        m = re.search(r'data-manga-id="(\d+)', html)
        if m:
            return m.group(1)
        m = re.search(r'manga-id="(\d+)', html)
        if m:
            return m.group(1)
    except Exception:
        pass
    return None


def fetch_chapter_list(manga_id):
    all_chapters = []
    offset = 0
    while True:
        ts, token = generate_token()
        url = f"{BASE_URL}/auth/manga-chapters?manga_id={manga_id}&offset={offset}&limit=500&order=ASC&_t={token}&_ts={ts}"
        data = fetch_json(url)
        if not data or not data.get("success"):
            break
        chapters = data.get("chapters", [])
        if not chapters:
            break
        all_chapters.extend(chapters)
        offset += len(chapters)
        if not data.get("has_more", False):
            break
        time.sleep(1)
    return all_chapters


def download_chapter(args):
    ch_id, ch_num, output_dir, fix_mode = args
    chapter_dir = Path(output_dir) / f"Chapter_{ch_num}"
    chapter_dir.mkdir(parents=True, exist_ok=True)

    existing = list(chapter_dir.glob("*.webp")) + list(chapter_dir.glob("*.jpg")) + list(chapter_dir.glob("*.png"))

    if fix_mode and existing:
        # Verify existing images, delete corrupt ones
        bad = []
        for f in existing:
            try:
                with open(f, "rb") as fh:
                    header = fh.read(12)
                if len(header) < 4 or f.stat().st_size < 100:
                    bad.append(f)
                elif f.suffix.lower() == ".webp" and header[:4] != b"RIFF":
                    bad.append(f)
                elif f.suffix.lower() == ".jpg" and header[:2] != b"\xff\xd8":
                    bad.append(f)
                elif f.suffix.lower() == ".png" and header[:8] != b"\x89PNG\r\n\x1a\n":
                    bad.append(f)
                else:
                    # Try opening with PIL to confirm
                    from PIL import Image
                    img = Image.open(f)
                    img.verify()
            except Exception:
                bad.append(f)
        for f in bad:
            f.unlink()
        existing = [f for f in existing if f not in bad]
        if not bad:
            return ("ok", ch_num, len(existing), len(existing))

    if existing and not fix_mode:
        return ("skip", ch_num, 0, 0)

    # Fetch image list
    ts, token = generate_token()
    url = f"{BASE_URL}/auth/chapter-content?chapter_id={ch_id}"
    data = fetch_json(url)
    if not data or not data.get("success"):
        return ("fail", ch_num, 0, 0)

    images = data.get("images", [])
    if not images:
        return ("fail", ch_num, 0, 0)

    # Download images
    ok = 0
    for idx, img_url in enumerate(images):
        ext = img_url.split("?")[0].split(".")[-1] or "jpg"
        filepath = chapter_dir / f"{idx + 1:03d}.{ext}"
        if filepath.exists() and filepath.stat().st_size > 100:
            ok += 1
            continue
        if download_file(img_url, str(filepath)):
            # Verify downloaded file
            try:
                from PIL import Image
                img = Image.open(filepath)
                img.verify()
                ok += 1
            except Exception:
                filepath.unlink(missing_ok=True)
                if download_file(img_url, str(filepath)):
                    try:
                        img = Image.open(filepath)
                        img.verify()
                        ok += 1
                    except Exception:
                        filepath.unlink(missing_ok=True)
        else:
            filepath.unlink(missing_ok=True)

    return ("ok", ch_num, ok, len(images))


def slug_from_url(url):
    import re
    m = re.search(r"/manga/([^/]+)/?", url)
    return m.group(1) if m else None


def slug_to_title(slug):
    return "-".join(w.capitalize() for w in slug.split("-"))


def main():
    parser = argparse.ArgumentParser(description="Download manga from roliascan.com")
    parser.add_argument("url", help="Manga URL (e.g., https://roliascan.com/manga/one-piece/)")
    parser.add_argument("output", nargs="?", help="Output directory (default: auto from URL)")
    parser.add_argument("--workers", "-j", type=int, default=8, help="Parallel workers (default: 8)")
    parser.add_argument("--fix", action="store_true", help="Re-download corrupt images")
    args = parser.parse_args()

    slug = slug_from_url(args.url)
    if not slug:
        print("Error: Cannot extract manga slug from URL")
        sys.exit(1)

    output_dir = args.output or f"./{slug_to_title(slug)}"

    print("=== Manga Downloader ===")
    print(f"URL:    {args.url}")
    print(f"Slug:   {slug}")
    print(f"Output: {output_dir}")
    print(f"Workers: {args.workers}")
    print()

    # Step 1: Get manga_id
    print("Fetching manga ID...")
    manga_id = extract_manga_id(slug)
    if not manga_id:
        print("Error: Could not find manga_id")
        sys.exit(1)
    print(f"Manga ID: {manga_id}")

    # Step 2: Get chapter list
    print("Fetching chapter list...")
    chapters = fetch_chapter_list(manga_id)
    print(f"Total chapters: {len(chapters)}")
    if not chapters:
        print("No chapters found!")
        sys.exit(1)

    # Sort by chapter number
    chapters.sort(key=lambda c: float(c.get("chapter", 0)))

    # Step 3: Download in parallel
    print(f"Downloading with {args.workers} workers...")
    args_list = [(ch["id"], ch["chapter"], output_dir, args.fix) for ch in chapters]

    processed = 0
    skipped = 0
    failed = 0

    with Pool(args.workers) as pool:
        for result in pool.imap_unordered(download_chapter, args_list):
            status, ch_num, ok, total = result
            if status == "skip":
                skipped += 1
            elif status == "fail":
                failed += 1
                print(f"  Chapter {ch_num}: FAILED")
            else:
                processed += 1
                print(f"  Chapter {ch_num}: {ok}/{total} images")

    print()
    print("=== Download Complete ===")
    print(f"Downloaded: {processed} | Skipped: {skipped} | Failed: {failed}")
    print(f"Location: {os.path.abspath(output_dir)}/")
    print()
    print("To build PDF:")
    print(f"  ./build.sh 150 {output_dir}")
    print(f"  ./build.sh 300 {output_dir}")


if __name__ == "__main__":
    main()
