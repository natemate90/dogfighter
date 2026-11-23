#!/bin/bash
set -euo pipefail
usage() {
  cat <<'EOF'
usage: tools/build-app.sh                  Dogfighter.app in the repo folder, which starts ./dogfighter
       tools/build-app.sh --full [--data=FOLDER]
                                           dist/Dogfighter.app with everything inside: Wine, the game,
                                           the music, the larger textures, the intro videos and the
                                           helpers. FOLDER is the installed game, by default the repo.
EOF
}
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FULL=0
DATA="$ROOT"
for arg in "$@"; do
  case "$arg" in
    --full) FULL=1 ;;
    --data=*) DATA="$(cd "${arg#--data=}" && pwd)" ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
  esac
done
[ "$FULL" = 1 ] || [ "$DATA" = "$ROOT" ] || { usage >&2; exit 2; }

die() { echo "$*" >&2; exit 1; }

if [ "$FULL" = 1 ]; then
  APP="$DATA/dist/Dogfighter.app"
  BUNDLE_ID=local.dogfighter.app
  mkdir -p "$DATA/dist"
  WORK="$(mktemp -d "$DATA/dist/.app.XXXXXX")"
else
  APP="$ROOT/Dogfighter.app"
  BUNDLE_ID=local.dogfighter.launcher
  mkdir -p "$ROOT/build"
  WORK="$(mktemp -d "$ROOT/build/app.XXXXXX")"
fi
ICO="$DATA/cd/Airfix.ico"
trap 'rm -rf "$WORK"' EXIT
NEW="$WORK/Dogfighter.app"
PLIST="$NEW/Contents/Info.plist"
STUB="$NEW/Contents/MacOS/Dogfighter"
RES="$NEW/Contents/Resources"
mkdir -p "$NEW/Contents/MacOS" "$RES"

cat >"$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleDevelopmentRegion</key>
  <string>en</string>
  <key>CFBundleDisplayName</key>
  <string>Airfix Dogfighter</string>
  <key>CFBundleExecutable</key>
  <string>Dogfighter</string>
  <key>CFBundleIdentifier</key>
  <string>$BUNDLE_ID</string>
  <key>CFBundleInfoDictionaryVersion</key>
  <string>6.0</string>
  <key>CFBundleName</key>
  <string>Dogfighter</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleShortVersionString</key>
  <string>1.0</string>
  <key>CFBundleVersion</key>
  <string>1</string>
  <key>LSApplicationCategoryType</key>
  <string>public.app-category.games</string>
  <key>LSMinimumSystemVersion</key>
  <string>11.0</string>
  <key>LSUIElement</key>
  <true/>
</dict>
</plist>
EOF

shortcut_stub() {
  {
    printf '#!/bin/bash\nLAUNCHER=%q\n' "$ROOT/dogfighter"
    cat <<'EOF'
alert() {
  /usr/bin/osascript -e 'on run argv' -e 'display alert "Airfix Dogfighter" message (item 1 of argv)' \
    -e 'end run' "$1" >/dev/null 2>&1 || true
}
if [ ! -x "$LAUNCHER" ]; then
  alert "The launcher is not at $LAUNCHER any more. Run ./setup.sh in the game folder to rebuild this app."
  exit 1
fi
"$LAUNCHER" || { alert "The game did not start. Run ./dogfighter in Terminal to see why."; exit 1; }
EOF
  } >"$STUB"
}

installed_language() {
  LC_ALL=C awk '{ sub(/\r$/, "") } index($0, "current_language=") == 1 { print substr($0, 18); exit }' \
    "$DATA/game/system.ini" 2>/dev/null || true
}

copy() { /usr/bin/ditto --norsrc --noextattr --noqtn --noacl "$@"; }

check_data() {
  local name t
  [ -x "$DATA/wine-mach9/wine/bin/wine" ] || die "No Mach9 in $DATA/wine-mach9. The app holds Mach9 only; run ./setup.sh on macOS 26.4 or later."
  [ -f "$DATA/cd/.windows-label" ] && [ -f "$DATA/cd/data1.hdr" ] || die "No disc copy in $DATA/cd. Run ./setup.sh first."
  for t in 02 03 04 05 06 07 08 09 10 11; do
    [ -f "$DATA/music/Track$t.ogg" ] || die "$DATA/music/Track$t.ogg is missing. Run ./setup.sh first."
  done
  for name in focusfix.exe focushook.dll joylist.exe windiag.exe crashlog.dll intro-player winmm.dll; do
    [ -f "$DATA/build/$name" ] || die "$DATA/build/$name is missing. Run ./setup.sh first."
  done
  [ "$DATA/build/focusfix.exe" -nt "$DATA/src/focusfix/focusfix.c" ] &&
    [ "$DATA/build/focushook.dll" -nt "$DATA/src/focusfix/focushook.c" ] &&
    [ "$DATA/build/intro-player" -nt "$DATA/tools/intro-player.m" ] ||
    die "The helpers in $DATA/build are older than their source. Run ./setup.sh first."
  python3 -I -B "$DATA/tools/upscale-textures.py" --check --out "$DATA/hd-textures" ||
    die "No complete set of larger textures in $DATA/hd-textures. Run ./setup.sh first."
  for name in companies airfix; do
    [ -f "$DATA/hd-videos/$name.mov" ] || echo "No $DATA/hd-videos/$name.mov, so the app plays the game's own intro videos."
  done
}

full_contents() {
  local language name item
  check_data
  language="$(installed_language)"
  echo "Copying the game ($language), Wine, the music, the textures and the videos into the app."
  python3 -I -B "$ROOT/tools/iscab.py" "$DATA/cd" "$RES/game" "${language:-English}" >/dev/null
  [ -f "$RES/game/Dogfighter.exe" ] && [ -f "$RES/game/system.ini" ] && [ -f "$RES/game/user.ini" ] ||
    die "The game files could not be unpacked from $DATA/cd."
  copy "$DATA/build/winmm.dll" "$RES/game/winmm.dll"
  copy "$DATA/wine-mach9" "$RES/wine-mach9"
  rm -rf "$RES/wine-mach9/wine/include"
  copy "$DATA/cd" "$RES/cd"
  copy "$DATA/music" "$RES/music"
  for item in cache manifest.json texture-limit; do copy "$DATA/hd-textures/$item" "$RES/hd-textures/$item"; done
  for name in companies airfix; do
    [ ! -f "$DATA/hd-videos/$name.mov" ] || copy "$DATA/hd-videos/$name.mov" "$RES/hd-videos/$name.mov"
  done
  for name in focusfix.exe focushook.dll joylist.exe windiag.exe crashlog.dll intro-player; do
    copy "$DATA/build/$name" "$RES/build/$name"
  done
  copy "$DATA/src/focusfix" "$RES/src/focusfix"
  copy "$DATA/tools" "$RES/tools"
  find "$RES/tools" -name __pycache__ -prune -exec rm -rf {} +
  for item in User user.ini system.ini dogfighter-picture-before.txt; do
    [ ! -e "$DATA/game/$item" ] || copy "$DATA/game/$item" "$RES/saves/$item"
  done
  copy "$ROOT/dogfighter" "$RES/dogfighter"
  copy "$ROOT/dogfighter.reg" "$RES/dogfighter.reg"
  copy "$ROOT/tools/app-start.sh" "$STUB"
}

if [ "$FULL" = 1 ]; then full_contents; else shortcut_stub; fi
chmod +x "$STUB"

make_icon() {
  local png="$WORK/icon.png" set="$WORK/Dogfighter.iconset" size
  [ -f "$ICO" ] || return 1
  mkdir -p "$set"
  sips -s format png "$ICO" --out "$png" >/dev/null 2>&1 || return 1
  [ -s "$png" ] || return 1
  for size in 16 32 128 256 512; do
    sips -z "$size" "$size" "$png" --out "$set/icon_${size}x${size}.png" >/dev/null 2>&1 &&
      sips -z $((size * 2)) $((size * 2)) "$png" --out "$set/icon_${size}x${size}@2x.png" >/dev/null 2>&1 &&
      [ -s "$set/icon_${size}x${size}.png" ] && [ -s "$set/icon_${size}x${size}@2x.png" ] || return 1
  done
  iconutil -c icns -o "$RES/Dogfighter.icns" "$set" 2>/dev/null
}

if make_icon || { [ "$FULL" = 1 ] && [ -s "$DATA/Dogfighter.app/Contents/Resources/Dogfighter.icns" ] &&
  copy "$DATA/Dogfighter.app/Contents/Resources/Dogfighter.icns" "$RES/Dogfighter.icns"; }; then
  plutil -insert CFBundleIconFile -string Dogfighter "$PLIST"
else
  rm -f "$RES/Dogfighter.icns"
  echo "Could not make an icon from cd/Airfix.ico; Dogfighter.app has the plain app icon."
fi
plutil -lint -s "$PLIST"

if [ "$FULL" = 1 ]; then
  [ -z "$(find "$NEW" -type l -lname '/*')" ] || die "The app holds a link to a full path outside it."
  codesign --force -s - "$NEW"
  codesign --verify --deep --strict "$NEW" || die "The signature of the app does not verify."
else
  codesign --force -s - "$NEW" 2>/dev/null ||
    echo "Could not sign Dogfighter.app; it still starts on the Mac that built it."
fi

rm -rf "$APP"
mv "$NEW" "$APP"
if [ "$FULL" = 1 ]; then
  echo "Built $APP ($(du -sh "$APP" | cut -f1)). It holds the game's files: keep it to yourself."
else
  echo "Built $APP"
fi
