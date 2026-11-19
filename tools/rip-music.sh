#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
V="$ROOT/src/vorbis-1.3.7"
O="$ROOT/src/ogg-1.3.6"
B="$(mktemp -d "${TMPDIR:-/tmp}/oggenc.XXXXXX")"
SDK=/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk

mkdir -p "$B/inc/ogg"
sed -e 's/@INCLUDE_[A-Z_]*@/1/g;s/@SIZE16@/int16_t/;s/@USIZE16@/uint16_t/;s/@SIZE32@/int32_t/;s/@USIZE32@/uint32_t/' \
    -e 's/@SIZE64@/int64_t/;s/@USIZE64@/uint64_t/' "$O/include/ogg/config_types.h.in" > "$B/inc/ogg/config_types.h"
sed 's/vorbis_encode_init_vbr(&vi,2,44100,0.1)/vorbis_encode_init_vbr(\&vi,2,44100,0.5)/' "$V/examples/encoder_example.c" > "$B/enc.c"
grep -q '44100,0.5)' "$B/enc.c"
libs=()
for n in mdct smallft block envelope window lsp lpc analysis synthesis psy info floor1 floor0 res0 mapping0 registry codebook sharedbook lookup bitrate vorbisenc; do
  libs+=("$V/lib/$n.c")
done
clang -isysroot "$SDK" -O2 -w -I"$B/inc" -I"$O/include" -I"$V/include" -I"$V/lib" -o "$B/oggenc-min" \
  "$B/enc.c" "$O/src/bitwise.c" "$O/src/framing.c" "${libs[@]}" -lm

python3 -I "$ROOT/tools/rip_tracks.py" "$ROOT/Dogfighter.bin" "$B/oggenc-min" "$ROOT/music" \
  88557-107346 107522-127042 127202-143971 144126-150104 150262-154751 \
  154902-168286 168469-183443 183604-204288 204451-219548 219714-237821
rm -rf "$B"
