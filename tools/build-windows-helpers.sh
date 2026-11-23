#!/bin/bash
set -euo pipefail
[ $# -eq 1 ] || { echo "usage: $0 <llvm-mingw dir>" >&2; exit 2; }
TC="$1"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/src"
OUT="$ROOT/dist/windows-helpers"
export SOURCE_DATE_EPOCH=0
for dir in ogg-1.3.6 vorbis-1.3.7 ogg-winmm; do
  [ -d "$SRC/$dir" ] || { echo "src/$dir is missing. Run ./setup.sh first; it fetches the pinned sources." >&2; exit 1; }
done
B="$(mktemp -d "${TMPDIR:-/tmp}/windows-helpers.XXXXXX")"
trap 'rm -rf "$B"' EXIT
rm -rf "$OUT"
mkdir -p "$OUT"

"$ROOT/tools/build-winmm.sh" "$TC" "$OUT"
"$ROOT/tools/build-focusfix.sh" "$TC"
cp "$ROOT/build/focusfix.exe" "$ROOT/build/focushook.dll" "$ROOT/build/joylist.exe" "$OUT/"

V="$SRC/vorbis-1.3.7"
O="$SRC/ogg-1.3.6"
mkdir -p "$B/inc/ogg"
sed -e 's/@INCLUDE_[A-Z_]*@/1/g;s/@SIZE16@/int16_t/;s/@USIZE16@/uint16_t/;s/@SIZE32@/int32_t/;s/@USIZE32@/uint32_t/' \
    -e 's/@SIZE64@/int64_t/;s/@USIZE64@/uint64_t/' "$O/include/ogg/config_types.h.in" > "$B/inc/ogg/config_types.h"
sed 's/vorbis_encode_init_vbr(&vi,2,44100,0.1)/vorbis_encode_init_vbr(\&vi,2,44100,0.5)/' "$V/examples/encoder_example.c" > "$B/enc.c"
grep -q '44100,0.5)' "$B/enc.c"
libs=()
for n in mdct smallft block envelope window lsp lpc analysis synthesis psy info floor1 floor0 res0 mapping0 registry codebook sharedbook lookup bitrate vorbisenc; do
  libs+=("$V/lib/$n.c")
done
"$TC/bin/i686-w64-mingw32-clang" -O2 -s -w -I"$B/inc" -I"$O/include" -I"$V/include" -I"$V/lib" -o "$OUT/oggenc-min.exe" \
  "$B/enc.c" "$O/src/bitwise.c" "$O/src/framing.c" "${libs[@]}"

{
  echo "These files are built from the sources named below, by tools/build-windows-helpers.sh."
  echo "They hold no game data."
  echo
  echo "focusfix.exe, focushook.dll, joylist.exe: src/focusfix in natemate90/dogfighter."
  echo "winmm.dll: ogg-winmm (dippy-dipper/ogg-winmm at 09859f0) with libogg 1.3.6 and libvorbis 1.3.7."
  echo "oggenc-min.exe: libvorbis 1.3.7 examples/encoder_example.c, quality 0.5, with libogg 1.3.6."
  echo "All are built with llvm-mingw 20261117, whose mingw-w64 runtime is linked in."
  echo
  echo "== ogg-winmm =="
  sed -n '2,14p' "$SRC/ogg-winmm/ogg-winmm.c" | sed 's/^ \* \{0,1\}//'
  echo
  echo "== libogg =="
  cat "$O/COPYING"
  echo
  echo "== libvorbis =="
  cat "$V/COPYING"
  echo
  echo "== mingw-w64 runtime =="
  cat "$ROOT/tools/mingw-w64-runtime-licence.txt"
} > "$OUT/THIRD-PARTY-NOTICES.txt"

(cd "$OUT" && shasum -a 256 winmm.dll focusfix.exe focushook.dll joylist.exe oggenc-min.exe THIRD-PARTY-NOTICES.txt > SHA256SUMS)
file "$OUT"/*.exe "$OUT"/*.dll
cat "$OUT/SHA256SUMS"
