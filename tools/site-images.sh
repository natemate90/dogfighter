#!/bin/sh
set -eu
cd "$(dirname "$0")/../site/img"

shrink() {
  magick "$1" -resize "$2x" -strip -quality 75 -define webp:method=6 "$3"
  echo "$3 $(wc -c < "$3" | tr -d ' ') bytes"
}

for name in menu loading kids-room living-room sofa explosion backyard; do
  shrink "game/$name-1600.webp" 400 "game/$name-400.webp"
  shrink "game/$name-1600.webp" 720 "game/$name-720.webp"
done
for name in scramble airfield; do
  shrink "$name.webp" 320 "$name-320.webp"
  shrink "$name.webp" 640 "$name-640.webp"
done
