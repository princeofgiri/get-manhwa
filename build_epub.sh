#!/bin/bash
# Convert manga to EPUB format
# Usage: ./build_epub.sh [source-dir] [--start N] [--end N] [--workers N]

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SOURCE_DIR="${1:-.}"
shift 2>/dev/null || true

python3 "$SCRIPT_DIR/create_epub.py" "$SOURCE_DIR" --workers 8 "$@"
