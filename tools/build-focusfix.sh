#!/bin/bash
set -euo pipefail
[ $# -eq 1 ] || { echo "usage: $0 <llvm-mingw dir>" >&2; exit 2; }
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CC="$1/bin/i686-w64-mingw32-clang"
mkdir -p "$ROOT/build"
"$CC" -std=gnu99 -O2 -s -Wall -mwindows \
  -o "$ROOT/build/focusfix.exe" "$ROOT/src/focusfix/focusfix.c"
"$CC" -std=gnu99 -O2 -s -Wall -shared \
  -o "$ROOT/build/focushook.dll" "$ROOT/src/focusfix/focushook.c"
file "$ROOT/build/focusfix.exe" "$ROOT/build/focushook.dll"
