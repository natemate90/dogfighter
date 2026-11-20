#!/bin/bash
set -Eeuo pipefail

usage() {
  cat <<'EOF'
Usage: ./setup.sh [path/to/Dogfighter.bin]

Builds everything the game needs from your own Airfix Dogfighter CD image.
The image must be a raw .bin (2352-byte sectors); it defaults to ./Dogfighter.bin.
Run it again after an error: finished steps are skipped.
EOF
}

case "${1:-}" in -h|--help) usage; exit 0 ;; esac
[ $# -le 1 ] || { usage >&2; exit 2; }

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE="${1:-$HERE/Dogfighter.bin}"
DL="$HERE/downloads"
WORK="$HERE/build/setup-work"
TOOLCHAIN_NAME=llvm-mingw-20261117-ucrt-macos-universal
TOOLCHAIN="$HERE/toolchain/$TOOLCHAIN_NAME"
OGG_WINMM_COMMIT=09859f0cedf074c705fd56d29056d254e667a17d
TRACKS="02 03 04 05 06 07 08 09 10 11"

die() { printf '\nsetup: %s\n' "$*" >&2; exit 1; }
step() { printf '\n==> %s\n' "$*"; }
trap 'die "a step failed (line $LINENO). Fix the error above, then run ./setup.sh again."' ERR
trap 'rm -rf "$WORK"' EXIT

check_requirements() {
  [ "$(uname -s)" = Darwin ] || die "This needs macOS."
  [ "$(uname -m)" = arm64 ] || [ "$(sysctl -n hw.optional.arm64 2>/dev/null || true)" = 1 ] ||
    die "This needs a Mac with Apple Silicon (M1 or later)."
  /usr/bin/arch -x86_64 /usr/bin/true 2>/dev/null ||
    die "Rosetta 2 is missing. Install it with: softwareupdate --install-rosetta --agree-to-license"
  { xcode-select -p >/dev/null 2>&1 && xcrun --find clang >/dev/null 2>&1; } ||
    die "The Xcode Command Line Tools are missing. Install them with: xcode-select --install"
  python3 -c 'import sys; sys.exit(sys.version_info < (3, 6))' 2>/dev/null ||
    die "python3 (3.6 or later) is missing. It comes with the Xcode Command Line Tools: xcode-select --install"
  local tool
  for tool in curl shasum tar xxd; do
    command -v "$tool" >/dev/null || die "$tool is missing; it normally ships with macOS."
  done
}

check_image() {
  [ -f "$IMAGE" ] || die "CD image not found: $IMAGE
Make a raw image of your own disc first (see README.md), or pass its path: ./setup.sh path/to/Dogfighter.bin"
  local size
  size="$(stat -f %z "$IMAGE")"
  if [ $((size % 2352)) -ne 0 ]; then
    [ $((size % 2048)) -eq 0 ] &&
      die "$IMAGE looks like an .iso. It has no music; make a raw .bin/.cue image instead."
    die "$IMAGE is not a raw CD image (its size is not a multiple of 2352 bytes)."
  fi
  [ "$(head -c 12 "$IMAGE" | xxd -p)" = 00ffffffffffffffffffff00 ] ||
    die "$IMAGE does not start with a data track. Is it the Airfix Dogfighter CD?"
}

check_space() {
  local free_kb
  free_kb="$(df -Pk "$HERE" | awk 'NR == 2 { print $4 }')"
  [ "$free_kb" -ge $((3 * 1024 * 1024)) ] || die "Setup needs about 3 GB of free disk space."
}

sha_ok() { [ "$(shasum -a 256 "$1" | cut -d' ' -f1)" = "$2" ]; }

fetch() {
  local name="$1" url="$2" sha="$3" file="$DL/$1"
  if [ -f "$file" ] && sha_ok "$file" "$sha"; then return; fi
  mkdir -p "$DL"
  echo "Downloading $name"
  curl -fL --retry 3 --progress-bar -o "$file.part" "$url" || die "Download failed: $url"
  sha_ok "$file.part" "$sha" || {
    rm -f "$file.part"
    die "$name does not match its pinned SHA-256 checksum. Delete downloads/ and try again; if it keeps failing, the file on the server has changed."
  }
  mv "$file.part" "$file"
}

unpack() {
  local archive="$1" inner="$2" dest="$3"
  rm -rf "$WORK"
  mkdir -p "$WORK" "$(dirname "$dest")"
  tar -xf "$archive" -C "$WORK"
  mv "$WORK/$inner" "$dest"
  rm -rf "$WORK"
}

get_wine() {
  [ -x "$HERE/wine/bin/wine" ] && return
  step "Wine 11.0 (Gcenx build)"
  fetch wine-stable-11.0_1-osx64.tar.xz \
    https://github.com/Gcenx/macOS_Wine_builds/releases/download/11.0_1/wine-stable-11.0_1-osx64.tar.xz \
    b50dc50ec7f41d58b115a6b685d4d1315ba3c797bd3aa0f49213f2703cb82388
  rm -rf "$HERE/wine"
  unpack "$DL/wine-stable-11.0_1-osx64.tar.xz" "Wine Stable.app/Contents/Resources/wine" "$HERE/wine"
  xattr -dr com.apple.quarantine "$HERE/wine" 2>/dev/null || true
}

get_toolchain() {
  [ -x "$TOOLCHAIN/bin/i686-w64-mingw32-clang" ] && return
  step "llvm-mingw (builds the small Windows helpers)"
  fetch "$TOOLCHAIN_NAME.tar.xz" \
    "https://github.com/mstorsjo/llvm-mingw/releases/download/20261117/$TOOLCHAIN_NAME.tar.xz" \
    98d340bbb8d46b09ad6886ffba88bd9d5415e131c316de48e6bd7647377446aa
  rm -rf "$TOOLCHAIN"
  unpack "$DL/$TOOLCHAIN_NAME.tar.xz" "$TOOLCHAIN_NAME" "$TOOLCHAIN"
}

get_sources() {
  if [ ! -d "$HERE/src/ogg-1.3.6" ]; then
    step "libogg 1.3.6"
    fetch libogg-1.3.6.tar.gz https://github.com/xiph/ogg/archive/refs/tags/v1.3.6.tar.gz \
      95b643da661155d79db9de2fca55daed3a8d491039829def246aacb3d9201c81
    unpack "$DL/libogg-1.3.6.tar.gz" ogg-1.3.6 "$HERE/src/ogg-1.3.6"
  fi
  if [ ! -d "$HERE/src/vorbis-1.3.7" ]; then
    step "libvorbis 1.3.7"
    fetch libvorbis-1.3.7.tar.gz https://github.com/xiph/vorbis/archive/refs/tags/v1.3.7.tar.gz \
      270c76933d0934e42c5ee0a54a36280e2d87af1de3cc3e584806357e237afd13
    unpack "$DL/libvorbis-1.3.7.tar.gz" vorbis-1.3.7 "$HERE/src/vorbis-1.3.7"
  fi
  if [ ! -d "$HERE/src/ogg-winmm" ]; then
    step "ogg-winmm (plays the CD music from .ogg files)"
    fetch ogg-winmm-09859f0.tar.gz \
      "https://github.com/dippy-dipper/ogg-winmm/archive/$OGG_WINMM_COMMIT.tar.gz" \
      aa8c260fedb2aacc4f3c79899645039ab08a36f3a2ef4005de1f9a245bcc1fb2
    unpack "$DL/ogg-winmm-09859f0.tar.gz" "ogg-winmm-$OGG_WINMM_COMMIT" "$HERE/src/ogg-winmm"
  fi
}

make_cd() {
  [ -f "$HERE/cd/.windows-label" ] && return
  check_image
  step "Copying the CD's data track to cd/"
  rm -rf "$WORK" "$HERE/cd"
  mkdir -p "$WORK/cd"
  python3 -I "$HERE/tools/scan.py" "$IMAGE" "$WORK/data.iso"
  tar -xf "$WORK/data.iso" -C "$WORK/cd"
  [ -f "$WORK/cd/data1.hdr" ] && [ -f "$WORK/cd/data2.cab" ] ||
    die "The data track has no data1.hdr or data2.cab. Is this the Airfix Dogfighter CD?"
  chmod -R u+w "$WORK/cd"
  printf 'Dogfighter\n' >"$WORK/cd/.windows-label"
  mv "$WORK/cd" "$HERE/cd"
  rm -rf "$WORK"
}

install_game() {
  step "Installing the English game files in game/"
  python3 -I "$HERE/tools/iscab.py" "$HERE/cd" "$HERE/game"
  [ -f "$HERE/game/Dogfighter.exe" ] && [ -f "$HERE/game/Resource.up" ] ||
    die "game/ is incomplete after unpacking the cabs."
  mkdir -p "$HERE/game/User/Rosters" "$HERE/game/User/Save/Levels" "$HERE/game/User/Save/Photos" \
    "$HERE/game/User/Save/Stickers" "$HERE/game/ScreenShots"
}

rip_music() {
  local t missing=0
  for t in $TRACKS; do [ -f "$HERE/music/Track$t.ogg" ] || missing=1; done
  if [ "$missing" = 1 ]; then
    check_image
    step "Ripping the CD music to music/ (a few minutes)"
    "$HERE/tools/rip-music.sh" "$IMAGE" "$HERE/music"
  fi
  ln -sfn ../music "$HERE/game/Music"
}

build_helpers() {
  if [ ! -f "$HERE/build/winmm.dll" ]; then
    step "Building winmm.dll (CD music player)"
    "$HERE/tools/build-winmm.sh" "$TOOLCHAIN" "$HERE/build"
  fi
  cmp -s "$HERE/build/winmm.dll" "$HERE/game/winmm.dll" || cp "$HERE/build/winmm.dll" "$HERE/game/winmm.dll"
  local helper
  for helper in focusfix focushook windiag crashlog; do
    [ -n "$(find "$HERE/build" -name "$helper.*" -newer "$HERE/src/focusfix/$helper.c" 2>/dev/null)" ] && continue
    step "Building the window helper and its diagnostics"
    "$HERE/tools/build-focusfix.sh" "$TOOLCHAIN"
    break
  done
}

path_hint() {
  local dir
  [ -z "$(command -v dogfighter 2>/dev/null || true)" ] || return 0
  case ":$PATH:" in
    *":/opt/homebrew/bin:"*) dir=/opt/homebrew/bin ;;
    *":$HOME/.local/bin:"*) dir="$HOME/.local/bin" ;;
    *) return 0 ;;
  esac
  echo "To start it from anywhere as 'dogfighter', run:"
  echo "  ln -s \"$HERE/dogfighter\" \"$dir/dogfighter\""
}

check_requirements
[ -x "$HERE/wine/bin/wine" ] && [ -f "$HERE/game/Resource.up" ] || check_space
get_wine
get_toolchain
get_sources
make_cd
install_game
rip_music
build_helpers

printf '\nSetup is done. Start the game with: ./dogfighter\n'
path_hint
