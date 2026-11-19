#!/bin/bash
set -euo pipefail
[ $# -eq 0 ] || { echo "usage: $0" >&2; exit 2; }
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP="$ROOT/Dogfighter.app"
ICO="$ROOT/cd/Airfix.ico"
mkdir -p "$ROOT/build"
WORK="$(mktemp -d "$ROOT/build/app.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
NEW="$WORK/Dogfighter.app"
PLIST="$NEW/Contents/Info.plist"
STUB="$NEW/Contents/MacOS/Dogfighter"
mkdir -p "$NEW/Contents/MacOS" "$NEW/Contents/Resources"

cat >"$PLIST" <<'EOF'
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
  <string>local.dogfighter.launcher</string>
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
  iconutil -c icns -o "$NEW/Contents/Resources/Dogfighter.icns" "$set" 2>/dev/null
}

if make_icon; then
  plutil -insert CFBundleIconFile -string Dogfighter "$PLIST"
else
  rm -f "$NEW/Contents/Resources/Dogfighter.icns"
  echo "Could not make an icon from cd/Airfix.ico; Dogfighter.app has the plain app icon."
fi
plutil -lint -s "$PLIST"
codesign --force -s - "$NEW" 2>/dev/null ||
  echo "Could not sign Dogfighter.app; it still starts on the Mac that built it."

rm -rf "$APP"
mv "$NEW" "$APP"
echo "Built $APP"
