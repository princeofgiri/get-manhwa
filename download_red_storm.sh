#!/usr/bin/env bash

MANGA_ID=10784
BASE_URL="https://roliascan.com"
OUTPUT_DIR="./Red-Storm"
DELAY=2
RETRY=3
TIMEOUT=30

mkdir -p "$OUTPUT_DIR"

TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

generate_token() {
    python3 -c "
import hashlib, time, datetime
ts = int(time.time())
hour = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d%H')
secret = 'mng_ch_' + hour
token = hashlib.md5((str(ts) + secret).encode()).hexdigest()[:16]
print(f'{ts} {token}')
"
}

curl_retry() {
    local url=$1
    local output=$2
    local attempt=1
    while [ $attempt -le $RETRY ]; do
        if curl -sL --connect-timeout $TIMEOUT --max-time $((TIMEOUT*3)) -o "$output" "$url" 2>/dev/null; then
            if [ -s "$output" ]; then
                return 0
            fi
        fi
        attempt=$((attempt + 1))
        sleep 2
    done
    return 1
}

echo "=== Red Storm Downloader ==="
echo ""

if [ -f "$OUTPUT_DIR/.chapters.json" ]; then
    ALL_CHAPTERS="$OUTPUT_DIR/.chapters.json"
    echo "Using cached chapter list..."
else
    echo "Fetching chapter list..."
    ALL_CHAPTERS="$OUTPUT_DIR/.chapters.json"
    echo "[]" > "$ALL_CHAPTERS"
    OFFSET=0
    HAS_MORE=true

    while [ "$HAS_MORE" = "true" ]; do
        TOKEN_DATA=$(generate_token)
        TS="${TOKEN_DATA%% *}"
        TOKEN="${TOKEN_DATA##* }"

        curl -sL --connect-timeout $TIMEOUT --max-time $((TIMEOUT*3)) \
            "${BASE_URL}/auth/manga-chapters?manga_id=${MANGA_ID}&offset=${OFFSET}&limit=500&order=ASC&_t=${TOKEN}&_ts=${TS}" \
            > "$TMPDIR/response.json"

        python3 -c "
import json
with open('${ALL_CHAPTERS}') as f:
    existing = json.load(f)
with open('${TMPDIR}/response.json') as f:
    data = json.load(f)
chapters = data.get('chapters', [])
existing.extend(chapters)
with open('${ALL_CHAPTERS}', 'w') as f:
    json.dump(existing, f)
print('true' if data.get('has_more', False) else 'false')
" > "$TMPDIR/has_more.txt"

        HAS_MORE=$(cat "$TMPDIR/has_more.txt")
        COUNT=$(python3 -c "import json; print(len(json.load(open('${TMPDIR}/response.json')).get('chapters',[])))")
        OFFSET=$((OFFSET + COUNT))
        echo "  Fetched $OFFSET chapters so far..."
        [ "$COUNT" -eq 0 ] && HAS_MORE=false
        sleep 1
    done
fi

TOTAL=$(python3 -c "import json; print(len(json.load(open('${ALL_CHAPTERS}'))))")
echo "Total chapters: $TOTAL"
echo ""

python3 -c "
import json
chapters = json.load(open('${ALL_CHAPTERS}'))
for ch in chapters:
    print(f\"{ch['id']}|{ch['chapter']}\")
" > "$TMPDIR/chapter_list.txt"

PROCESSED=0
SKIPPED=0
FAILED=0

while IFS='|' read -r ch_id ch_num; do
    CHAPTER_DIR="${OUTPUT_DIR}/Chapter_${ch_num}"
    mkdir -p "$CHAPTER_DIR"

    EXISTING=$(find "$CHAPTER_DIR" \( -name "*.jpg" -o -name "*.webp" -o -name "*.png" \) 2>/dev/null | wc -l)
    if [ "$EXISTING" -gt 0 ]; then
        SKIPPED=$((SKIPPED + 1))
        continue
    fi

    if ! curl_retry "${BASE_URL}/auth/chapter-content?chapter_id=${ch_id}" "$TMPDIR/images_response.json"; then
        echo "Chapter ${ch_num}: FAILED to fetch image list, skipping..."
        FAILED=$((FAILED + 1))
        continue
    fi

    python3 -c "
import json
try:
    with open('${TMPDIR}/images_response.json') as f:
        data = json.load(f)
    if data.get('success') and data.get('images'):
        for url in data['images']:
            print(url)
except: pass
" > "$TMPDIR/images.txt"

    IMAGE_COUNT=$(wc -l < "$TMPDIR/images.txt" | tr -d ' ')

    if [ "$IMAGE_COUNT" -eq 0 ]; then
        echo "Chapter ${ch_num}: No images, skipping..."
        FAILED=$((FAILED + 1))
        continue
    fi

    DL_OK=0
    IDX=1
    while IFS= read -r img_url; do
        [ -z "$img_url" ] && continue
        EXT="${img_url%%\?*}"
        EXT="${EXT##*.}"
        [ -z "$EXT" ] && EXT="jpg"
        FILENAME=$(printf "%03d.%s" "$IDX" "$EXT")
        FILEPATH="${CHAPTER_DIR}/${FILENAME}"

        if [ ! -f "$FILEPATH" ]; then
            if curl_retry "$img_url" "$FILEPATH"; then
                DL_OK=$((DL_OK + 1))
            fi
        else
            DL_OK=$((DL_OK + 1))
        fi
        IDX=$((IDX + 1))
    done < "$TMPDIR/images.txt"

    PROCESSED=$((PROCESSED + 1))
    echo "Chapter ${ch_num}: ${DL_OK}/${IMAGE_COUNT} images done [${PROCESSED}+${SKIPPED} ok, ${FAILED} fail]"
    sleep "$DELAY"

done < "$TMPDIR/chapter_list.txt"

echo ""
echo "=== Selesai ==="
echo "Downloaded: $PROCESSED | Skipped: $SKIPPED | Failed: $FAILED"
echo "Lokasi: $(pwd)/$OUTPUT_DIR/"
