#!/bin/bash
set -euo pipefail
[ $# -eq 2 ] || { echo "usage: $0 <image.bin> <music dir>" >&2; exit 2; }
IMAGE="$1"
OUT="$2"
TRACKS_EXPECTED=10
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
V="$ROOT/src/vorbis-1.3.7"
O="$ROOT/src/ogg-1.3.6"
B="$(mktemp -d "${TMPDIR:-/tmp}/oggenc.XXXXXX")"
trap 'rm -rf "$B"' EXIT

mkdir -p "$B/inc/ogg"
sed -e 's/@INCLUDE_[A-Z_]*@/1/g;s/@SIZE16@/int16_t/;s/@USIZE16@/uint16_t/;s/@SIZE32@/int32_t/;s/@USIZE32@/uint32_t/' \
    -e 's/@SIZE64@/int64_t/;s/@USIZE64@/uint64_t/' "$O/include/ogg/config_types.h.in" > "$B/inc/ogg/config_types.h"
sed 's/vorbis_encode_init_vbr(&vi,2,44100,0.1)/vorbis_encode_init_vbr(\&vi,2,44100,0.5)/' "$V/examples/encoder_example.c" > "$B/enc.c"
grep -q '44100,0.5)' "$B/enc.c"
libs=()
for n in mdct smallft block envelope window lsp lpc analysis synthesis psy info floor1 floor0 res0 mapping0 registry codebook sharedbook lookup bitrate vorbisenc; do
  libs+=("$V/lib/$n.c")
done
xcrun clang -O2 -w -I"$B/inc" -I"$O/include" -I"$V/include" -I"$V/lib" -o "$B/oggenc-min" \
  "$B/enc.c" "$O/src/bitwise.c" "$O/src/framing.c" "${libs[@]}" -lm

tracks=()
while IFS= read -r range; do tracks+=("$range"); done < <(python3 -I "$ROOT/tools/find_tracks.py" "$IMAGE")
if [ "${#tracks[@]}" -ne "$TRACKS_EXPECTED" ]; then
  echo "Found ${#tracks[@]} music tracks in $IMAGE, expected $TRACKS_EXPECTED: ${tracks[*]}" >&2
  exit 1
fi
python3 -I "$ROOT/tools/rip_tracks.py" "$IMAGE" "$B/oggenc-min" "$OUT" "${tracks[@]}"
