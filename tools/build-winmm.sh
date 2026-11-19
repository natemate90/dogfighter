#!/bin/bash
set -euo pipefail
[ $# -eq 2 ] || { echo "usage: $0 <llvm-mingw dir> <output dir>" >&2; exit 2; }
TC="$1/bin"
OUT="$2"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/src"
CC="$TC/i686-w64-mingw32-clang"
AR="$TC/i686-w64-mingw32-ar"
WINDRES="$TC/i686-w64-mingw32-windres"
B="$(mktemp -d "${TMPDIR:-/tmp}/winmm-build.XXXXXX")"
mkdir -p "$OUT" "$B/inc/ogg"

sed -e 's/@INCLUDE_INTTYPES_H@/1/;s/@INCLUDE_STDINT_H@/1/;s/@INCLUDE_SYS_TYPES_H@/1/' \
    -e 's/@SIZE16@/int16_t/;s/@USIZE16@/uint16_t/;s/@SIZE32@/int32_t/;s/@USIZE32@/uint32_t/' \
    -e 's/@SIZE64@/int64_t/;s/@USIZE64@/uint64_t/' \
    "$SRC/ogg-1.3.6/include/ogg/config_types.h.in" > "$B/inc/ogg/config_types.h"
INC=(-I"$B/inc" -I"$SRC/ogg-1.3.6/include" -I"$SRC/vorbis-1.3.7/include" -I"$SRC/vorbis-1.3.7/lib")
CFLAGS=(-O2 -std=gnu99 -w "${INC[@]}")

objs=()
for f in "$SRC/ogg-1.3.6/src/"{bitwise,framing}.c; do
  o="$B/ogg_$(basename "$f" .c).o"; "$CC" "${CFLAGS[@]}" -c "$f" -o "$o"; objs+=("$o")
done
for n in mdct smallft block envelope window lsp lpc analysis synthesis psy info floor1 floor0 res0 mapping0 registry codebook sharedbook lookup bitrate vorbisfile; do
  o="$B/vorbis_$n.o"; "$CC" "${CFLAGS[@]}" -c "$SRC/vorbis-1.3.7/lib/$n.c" -o "$o"; objs+=("$o")
done
"$AR" rcs "$B/libvorbisfile.a" "${objs[@]}"

W="$SRC/ogg-winmm"
sed "s/__REV__/09859f0/g;s/__FILE__/ogg-winmm/g" "$W/ogg-winmm.rc.in" > "$B/ogg-winmm.rc"
"$WINDRES" -O coff -o "$B/ogg-winmm.rc.o" "$B/ogg-winmm.rc"
"$CC" -std=gnu99 -O2 -shared -s -w -D_DEBUG "${INC[@]}" \
  -Wl,--enable-stdcall-fixup \
  -o "$OUT/winmm.dll" \
  "$W/ogg-winmm.c" "$W/player.c" "$W/stubs.c" "$W/ogg-winmm.def" "$B/ogg-winmm.rc.o" \
  -L"$B" -lvorbisfile -lwinmm -static
rm -rf "$B"
file "$OUT/winmm.dll"
