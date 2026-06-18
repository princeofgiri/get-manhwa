#!/usr/bin/env bash
#
# Universal Manga Downloader for roliascan.com
#
# Usage:
#   ./download.sh https://roliascan.com/manga/red-storm/
#   ./download.sh https://roliascan.com/manga/one-piece/
#   ./download.sh https://roliascan.com/manga/solo-leveling/ ./MyOutput/
#   ./download.sh https://roliascan.com/manga/one-piece/ --workers 4

cd "$(dirname "$0")"
exec python3 download.py "$@"
