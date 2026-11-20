#!/bin/bash
set -Eeuo pipefail

usage() {
  cat <<'EOF'
Usage: ./setup.sh [--language=English|French|German|Italian] [--hd-textures|--no-hd-textures] [--generative]
                  [path/to/Dogfighter.bin]

Builds everything the game needs from your own Airfix Dogfighter CD image.
On macOS 26.4 or later it also fetches Mach9, a Wine that needs no Rosetta.
The image must be a raw .bin (2352-byte sectors); it defaults to ./Dogfighter.bin.
Run it again after an error: finished steps are skipped.

--language picks the game's language. Without it, setup keeps the installed
language, or installs English the first time. Saves are kept when you switch.

At the end setup makes the larger textures that ./dogfighter uses. It
downloads two upscalers (about 100 MB) to upscale-tools/ and takes a few
minutes. If the upscalers cannot be fetched or do not run on this Mac, the
textures are made with the Mac's own filter. A finished set is not made again.
--no-hd-textures skips this step. --hd-textures is still accepted; it is the
default.

--generative also sets up the generative way for a hand-picked list of
surface textures: a Python environment and two models, about 6.6 GB in
upscale-tools/generative/. It needs Python 3.12 or later.
EOF
}

LANGUAGES="English French German Italian"

canonical_language() {
  case "$1" in
    [Ee]nglish) echo English ;;
    [Ff]rench) echo French ;;
    [Gg]erman) echo German ;;
    [Ii]talian) echo Italian ;;
    *) return 1 ;;
  esac
}

LANGUAGE=
IMAGE=
HD_TEXTURES=1
GENERATIVE=
for arg in "$@"; do
  case "$arg" in
    -h|--help) usage; exit 0 ;;
    --language=*) LANGUAGE="$(canonical_language "${arg#--language=}")" || { usage >&2; exit 2; } ;;
    --hd-textures) HD_TEXTURES=1 ;;
    --no-hd-textures) HD_TEXTURES=0 ;;
    --generative) GENERATIVE=--generative ;;
    -*) usage >&2; exit 2 ;;
    *) [ -z "$IMAGE" ] || { usage >&2; exit 2; }; IMAGE="$arg" ;;
  esac
done

[ -z "$GENERATIVE" ] || [ "$HD_TEXTURES" = 1 ] || { usage >&2; exit 2; }

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE="${IMAGE:-$HERE/Dogfighter.bin}"
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

rosetta_ok() { /usr/bin/arch -x86_64 /usr/bin/true 2>/dev/null; }

# Mach9, the Wine that needs no Rosetta, runs on macOS 26.4 and later.
# DOGFIGHTER_MACOS stands in for the real version in a test.
macos_runs_mach9() {
  local version="${DOGFIGHTER_MACOS:-$(/usr/bin/sw_vers -productVersion 2>/dev/null || true)}" major minor
  major="${version%%.*}"
  minor=0
  if [[ "$version" == *.* ]]; then minor="${version#*.}"; fi
  minor="${minor%%.*}"
  [[ "$major" =~ ^[0-9]+$ && "$minor" =~ ^[0-9]+$ ]] || return 1
  [ "$major" -gt 26 ] || { [ "$major" -eq 26 ] && [ "$minor" -ge 4 ]; }
}

check_requirements() {
  [ "$(uname -s)" = Darwin ] || die "This needs macOS."
  [ "$(uname -m)" = arm64 ] || [ "$(sysctl -n hw.optional.arm64 2>/dev/null || true)" = 1 ] ||
    die "This needs a Mac with Apple Silicon (M1 or later)."
  macos_runs_mach9 || rosetta_ok ||
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
  [ "$free_kb" -ge $(($1 * 1024 * 1024)) ] || die "Setup needs about $1 GB of free disk space."
}

sha_ok() { [ "$(shasum -a 256 "$1" | cut -d' ' -f1)" = "$2" ]; }

fetch() {
  local name="$1" url="$2" sha="$3" file="$DL/$1"
  if [ -f "$file" ] && sha_ok "$file" "$sha"; then return; fi
  mkdir -p "$(dirname "$file")"
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

get_mach9() {
  macos_runs_mach9 || return 0
  [ -x "$HERE/wine-mach9/wine/bin/wine" ] || [ -x "$HERE/wine-mach9/bin/wine" ] && return
  step "Mach9 0.4.0 (Wine that needs no Rosetta)"
  fetch mach9/wine-v0.4.0-macos-arm64.tar.xz \
    https://github.com/athei/mach9/releases/download/v0.4.0/wine-v0.4.0-macos-arm64.tar.xz \
    3b81aac9b93d5652872673b400769ec525f3bc2f1f7e2ec82c9f851d0a0db05d
  rm -rf "$HERE/wine-mach9/wine"
  unpack "$DL/mach9/wine-v0.4.0-macos-arm64.tar.xz" wine "$HERE/wine-mach9/wine"
  xattr -dr com.apple.quarantine "$HERE/wine-mach9" 2>/dev/null || true
}

# On macOS 26.4 and later this Wine is only the fallback, so it is skipped
# there when Rosetta is not installed.
get_wine() {
  [ -x "$HERE/wine/bin/wine" ] && return
  rosetta_ok || return 0
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

installed_language() {
  [ -f "$HERE/game/system.ini" ] || return 0
  LC_ALL=C awk '{ sub(/\r$/, "") } index($0, "current_language=") == 1 { print substr($0, 18); exit }' \
    "$HERE/game/system.ini"
}

set_language() {
  local ini="$HERE/game/system.ini" tmp
  tmp="$(mktemp "$ini.XXXXXX")"
  LC_ALL=C awk -v v="$LANGUAGE" '
    { cr = sub(/\r$/, "") ? "\r" : "" }
    index($0, "current_language=") == 1 { next }
    { print $0 cr }
    $0 == "[setup]" { print "current_language=" v cr }' "$ini" >"$tmp"
  mv "$tmp" "$ini"
  [ "$(installed_language)" = "$LANGUAGE" ] || die "game/system.ini has no [setup] section."
}

install_game() {
  local was other
  was="$(canonical_language "$(installed_language)" || true)"
  LANGUAGE="${LANGUAGE:-${was:-English}}"
  step "Installing the $LANGUAGE game files in game/"
  [ "$was" = "$LANGUAGE" ] || rm -f "$HERE/game/readme.txt"
  python3 -I "$HERE/tools/iscab.py" "$HERE/cd" "$HERE/game" "$LANGUAGE"
  [ -f "$HERE/game/Dogfighter.exe" ] && [ -f "$HERE/game/Resource.up" ] &&
    [ -f "$HERE/game/$LANGUAGE.up" ] && [ -f "$HERE/game/$LANGUAGE.loc" ] ||
    die "game/ is incomplete after unpacking the cabs."
  for other in $LANGUAGES; do
    [ "$other" = "$LANGUAGE" ] || rm -f "$HERE/game/$other.up" "$HERE/game/$other.loc"
  done
  [ "$(installed_language)" = "$LANGUAGE" ] || set_language
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

make_hd_textures() {
  [ "$HD_TEXTURES" = 1 ] || return 0
  local tool="$HERE/tools/upscale-textures.py"
  step "Larger textures (the first time this downloads two upscalers, about 100 MB)"
  if [ -n "$GENERATIVE" ]; then
    python3 -I "$tool" --fetch-tools --generative
  elif ! python3 -I "$tool" --fetch-tools; then
    echo "The upscalers could not be fetched. The textures are made with the Mac's own filter."
  fi
  python3 -I "$tool" && return
  echo "The upscalers did not work on this Mac. The textures are made with the Mac's own filter instead."
  python3 -I "$tool" --upscaler vimage && return
  echo "The larger textures could not be made. The game uses its own; the next ./setup.sh tries again."
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
if macos_runs_mach9 && [ ! -d "$HERE/wine-mach9" ]; then
  check_space 5
elif [ ! -x "$HERE/wine/bin/wine" ] || [ ! -f "$HERE/game/Resource.up" ]; then
  check_space 3
fi
get_mach9
get_wine
get_toolchain
get_sources
make_cd
install_game
rip_music
build_helpers
step "Building Dogfighter.app"
"$HERE/tools/build-app.sh"
make_hd_textures

printf '\nSetup is done. Start the game with ./dogfighter, or double-click Dogfighter.app.\n'
path_hint
