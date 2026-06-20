# Get Manhwa

Download manga/manhwa from roliascan.com and build them into single PDF files optimized for e-ink readers.

## Requirements

- Python 3 with Pillow, PyMuPDF (fitz)
- DejaVu fonts (`ttf-dejavu` / `font-dejavu`)

No external dependencies for downloading (uses only Python stdlib). Build script auto-installs Pillow and PyMuPDF if missing.

## Quick Start

```bash
# 1. Download manga
./download.sh https://roliascan.com/manga/one-piece/

# 2. Build PDF
./build.sh 150 ./One-Piece/
```

## Download

```bash
./download.sh <manga-url> [output-dir] [--workers N]
```

Examples:
```bash
./download.sh https://roliascan.com/manga/red-storm/
./download.sh https://roliascan.com/manga/one-piece/
./download.sh https://roliascan.com/manga/solo-leveling/ ./solo-leveling/
./download.sh https://roliascan.com/manga/one-piece/ --workers 4
```

- **Parallel download** — default 8 workers, configurable with `--workers`
- Downloads all chapters (images per chapter folder)
- Skips already downloaded chapters
- Supports `.webp`, `.jpg`, `.jpeg`, `.png`
- Retry with backoff on failures

## Build PDF

```bash
./build.sh [dpi] [source-dir]
```

| Command | Description |
|---|---|
| `./build.sh` | Build both 150 and 300 DPI from `./Red-Storm/` |
| `./build.sh 150` | Build 150 DPI only (smaller file, ~2GB) |
| `./build.sh 300` | Build 300 DPI only (native resolution, ~6GB) |
| `./build.sh 150 ./One-Piece/` | Build 150 DPI from custom source dir |
| `./build.sh all ./Solo-Leveling/` | Build both from custom source dir |

### Output Resolutions

| DPI | Resolution | Screen Size | Typical Size |
|---|---|---|---|
| 150 | 702x936 | 7.8" e-ink | ~2 GB |
| 300 | 1404x1872 | 7.8" e-ink | ~6 GB |

### PDF Features

- **Clickable Table of Contents** — tap a chapter to jump directly
- **PDF Bookmarks** — sidebar navigation in any PDF reader
- **Chapter Separator Pages** — visual break between chapters
- **Page Numbers** — every page numbered with chapter reference
- **Tall Image Splitting** — long images auto-split into readable pages
- **E-ink Optimized** — contrast enhanced for e-ink displays
- **Multiprocessing** — builds at full CPU speed (12 workers)

## Build EPUB

```bash
python3 create_epub.py <source-dir> [options]
```

| Command | Description |
|---|---|
| `python3 create_epub.py ./One-Piece/` | All chapters into one EPUB |
| `python3 create_epub.py ./One-Piece/ --start 10 --end 20` | Range of chapters |
| `python3 create_epub.py ./One-Piece/ --by-chapter` | One EPUB per chapter |
| `python3 create_epub.py ./One-Piece/ --by-chapter --dpi 300` | Per-chapter at 300 DPI |
| `python3 create_epub.py ./One-Piece/ --workers 8` | Use 8 parallel workers |

### EPUB Options

| Flag | Description |
|---|---|
| `--by-chapter` | Create one EPUB per chapter in `<manga>-epub/` folder |
| `--start N` | Start chapter number |
| `--end N` | End chapter number |
| `--dpi N` | Target DPI (default: 150) |
| `--quality N` | JPG quality 1-100 (default: 95) |
| `--workers N` | Parallel workers (default: CPU count) |

### EPUB Features

- **Tall Image Splitting** — long images auto-split into readable pages
- **E-ink Optimized** — contrast enhanced, whitespace cropped
- **Clickable Table of Contents** — chapter navigation
- **Per-Chapter Mode** — individual EPUBs for easy transfer

## Tested With

- Allwinner WAVE 7.8" e-ink color reader (1872x1404, 300 DPI)
- Red Storm (462 chapters)

## File Structure

```
get-manhwa/
├── download.sh           # Download wrapper (calls download.py)
├── download.py           # Parallel manga downloader (multiprocess)
├── build.sh              # PDF build wrapper
├── build_pdf.py          # PDF builder (Python, multiprocess)
├── create_epub.py        # EPUB builder (Python, multiprocess)
├── Red-Storm/            # Downloaded images
│   ├── Chapter_0/
│   │   ├── 001.webp
│   │   └── ...
│   └── Chapter_461/
├── Red-Storm-epub/       # Per-chapter EPUBs (--by-chapter)
│   ├── Chapter_1.epub
│   └── ...
├── Red-Storm_Complete.pdf
├── Red-Storm_150dpi.pdf
└── Red-Storm_300dpi.pdf
```
