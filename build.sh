#!/usr/bin/env bash
#
# PDF Builder
#
# Usage:
#   ./build.sh                           # Build both 150/300 DPI from ./Red-Storm/
#   ./build.sh 150                       # Build 150 DPI only
#   ./build.sh 300                       # Build 300 DPI only
#   ./build.sh 150 ./One-Piece/          # Build 150 DPI from ./One-Piece/
#   ./build.sh 150 --grayscale           # Build 150 DPI grayscale
#   ./build.sh 150 ./One-Piece/ -g       # Build 150 DPI grayscale from custom dir

set -e
cd "$(dirname "$0")"

echo "=== PDF Builder ==="
echo ""

# Check dependencies
python3 -c "from PIL import Image; import fitz" 2>/dev/null || {
    echo "Installing dependencies..."
    pip install --break-system-packages Pillow PyMuPDF 2>/dev/null || \
    pip install Pillow PyMuPDF 2>/dev/null
}

# Parse args: ./build.sh [dpi] [source-dir] [--grayscale|-g]
DPI="all"
SOURCE_DIR="./Red-Storm"
GRAYSCALE=""

for arg in "$@"; do
    case "$arg" in
        150|300) DPI="$arg" ;;
        --grayscale|-g) GRAYSCALE="--grayscale" ;;
        -*) echo "Unknown option: $arg"; exit 1 ;;
        *)
            if [ -d "$arg" ]; then
                SOURCE_DIR="$arg"
            else
                echo "Error: Directory '$arg' not found"
                exit 1
            fi
            ;;
    esac
done

if [ ! -d "$SOURCE_DIR" ]; then
    echo "Error: Source directory '$SOURCE_DIR' not found"
    echo "Download manga first with: ./download.sh <url>"
    exit 1
fi

echo "Source: $SOURCE_DIR"
if [ -n "$GRAYSCALE" ]; then
    echo "Mode: Grayscale"
fi
echo ""

if [ "$DPI" = "all" ] || [ "$DPI" = "150" ]; then
    echo "--- Building 150 DPI (702x936) ---"
    INPUT_DIR="$SOURCE_DIR" python3 build_pdf.py 150 $GRAYSCALE
    echo ""
fi

if [ "$DPI" = "all" ] || [ "$DPI" = "300" ]; then
    echo "--- Building 300 DPI (1404x1872) ---"
    INPUT_DIR="$SOURCE_DIR" python3 build_pdf.py 300 $GRAYSCALE
    echo ""
fi

echo "=== Build Complete ==="
ls -lh ${SOURCE_DIR##*/}_*.pdf 2>/dev/null
