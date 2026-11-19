#!/bin/bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: ./run.sh [--res=WxH] [--sharp] [--windowed[=WxH] | --fullscreen] [--focusfix] [--winecfg]

  (no option)       Play in a window at the largest resolution that fits the screen.
                    macOS scales it up on a Retina screen, so menu text stays readable.
  --res=WxH         Use this game resolution instead, e.g. --res=1440x900.
  --sharp           Use Retina pixels: sharper, but the menu text gets half as big.
  --windowed=WxH    Force another Wine window size, e.g. --windowed=1280x960.
  --fullscreen      Let the game switch the Mac's real display mode.
  --focusfix        Keep the game running after Cmd+Tab and bring it back on return.
  --winecfg         Open Wine's settings for this game's prefix instead of playing.
EOF
}

MODE=windowed
DESKTOP_SIZE=
GAME_RES=
FOCUSFIX=0
SHARP=0
for arg in "$@"; do
  case "$arg" in
    --windowed) MODE=windowed ;;
    --windowed=*) MODE=windowed; DESKTOP_SIZE="${arg#--windowed=}" ;;
    --res=*) GAME_RES="${arg#--res=}" ;;
    --fullscreen) MODE=fullscreen ;;
    --sharp) SHARP=1 ;;
    --focusfix) FOCUSFIX=1 ;;
    --winecfg) MODE=winecfg ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
  esac
done
for size in "$DESKTOP_SIZE" "$GAME_RES"; do
  [[ -z "$size" || "$size" =~ ^[0-9]+x[0-9]+$ ]] || { echo "Bad size: $size" >&2; exit 2; }
done

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WINE="$HERE/wine/bin/wine"
WINESERVER="$HERE/wine/bin/wineserver"
GAME_DOS='C:\Games\Dogfighter'
REG="$HERE/dogfighter.reg"
INI="$HERE/game/system.ini"
FOCUSFIX_EXE="$HERE/build/focusfix.exe"
FOCUSHOOK_DLL="$HERE/build/focushook.dll"
SIZES="2560x1600 2560x1440 1920x1200 1920x1080 1680x1050 1600x1200 1600x900 1440x900
       1280x1024 1280x960 1280x800 1280x720 1024x768 800x600 640x480"

export WINEPREFIX="$HERE/prefix"
export WINEDEBUG="${WINEDEBUG:-fixme-all}"
export WINEDLLOVERRIDES="winmm=n,b;mscoree=;mshtml="

mkdir -p "$HERE/logs"
LOG="$HERE/logs/run-$(date +%Y%m%d-%H%M%S).log"
say() { echo "$*" | tee -a "$LOG"; }

ini_get() {
  [ -f "$1" ] || return 0
  awk -v s="[$2]" -v k="$3" '
    { sub(/\r$/, "") }
    /^\[/ { in_s = ($0 == s); next }
    in_s && index($0, k "=") == 1 { print substr($0, length(k) + 2); exit }' "$1"
}

ini_set() {
  local tmp
  tmp="$(mktemp "$1.XXXXXX")"
  awk -v s="[$2]" -v k="$3" -v v="$4" '
    { cr = sub(/\r$/, "") ? "\r" : "" }
    /^\[/ {
      if (in_s && !done) { print k "=" v cr; done = 1 }
      in_s = ($0 == s); if (in_s) seen = 1
    }
    in_s && index($0, k "=") == 1 { if (!done) print k "=" v cr; done = 1; next }
    { print $0 cr }
    END { if (!seen) print s "\r"; if (!done) print k "=" v "\r" }' "$1" >"$tmp"
  mv "$tmp" "$1"
}

game_section() {
  local dev card
  dev="$(ini_get "$INI" setup current_device)"
  card="$(ini_get "$INI" "${dev:-Direct3D}" device_card)"
  [ -n "$card" ] && echo "${dev:-Direct3D}.$card"
}

screen_info() {
  /usr/bin/osascript -l JavaScript -e '
    ObjC.import("AppKit");
    var s = $.NSScreen.screens.objectAtIndex(0), f = s.visibleFrame, k = s.backingScaleFactor >= 2 ? 2 : 1;
    k + " " + Math.floor(f.size.width) + " " + Math.floor(f.size.height - 28)' 2>/dev/null || true
}

retina_in_prefix() {
  awk '
    /^\[/ { in_s = index($0, "[Software\\\\Wine\\\\Mac Driver]") == 1; next }
    in_s && index($0, "\"RetinaMode\"=") == 1 { print; exit }' "$WINEPREFIX/user.reg" 2>/dev/null || true
}

fits() {
  [ -z "$LIMIT" ] || { [ "${1%x*}" -le "${LIMIT%x*}" ] && [ "${1#*x}" -le "${LIMIT#*x}" ]; }
}

largest_fit() {
  local size
  for size in $SIZES; do
    if fits "$size"; then echo "$size"; return; fi
  done
  echo 640x480
}

ini_size() {
  local section w h
  section="$(game_section || true)"
  [ -n "$section" ] || return 0
  w="$(ini_get "$INI" "$section" screen_width)"
  h="$(ini_get "$INI" "$section" screen_height)"
  if [[ "$w" =~ ^[0-9]+$ && "$h" =~ ^[0-9]+$ ]]; then echo "${w}x${h}"; fi
}

watch_front() {
  local flag="$1" was_front=1 pid exe
  while sleep 0.3; do
    pid="$(lsappinfo info -only pid "$(lsappinfo front 2>/dev/null)" 2>/dev/null |
      sed -n 's/.*=\([0-9][0-9]*\).*/\1/p')"
    exe=""
    [ -n "$pid" ] && exe="$(ps -o comm=,command= -p "$pid" 2>/dev/null || true)"
    if [[ "$exe" == *"$HERE/wine/"* || "$exe" == *Dogfighter* ]]; then
      if [ "$was_front" = 0 ]; then
        : >"$flag"
        echo "focusfix: Wine is in front again" >>"$LOG"
      fi
      was_front=1
    else
      was_front=0
    fi
  done
}

if ! /usr/bin/arch -x86_64 /usr/bin/true 2>/dev/null; then
  echo "Rosetta 2 is missing. Install it with:" >&2
  echo "  softwareupdate --install-rosetta --agree-to-license" >&2
  exit 1
fi
[ -x "$WINE" ] || { echo "Wine not found at $WINE" >&2; exit 1; }
if [ "$FOCUSFIX" = 1 ] && { [ ! -f "$FOCUSFIX_EXE" ] || [ ! -f "$FOCUSHOOK_DLL" ]; }; then
  echo "Missing $FOCUSFIX_EXE or $FOCUSHOOK_DLL; build them with tools/build-focusfix.sh" >&2
  exit 1
fi

if [ ! -f "$WINEPREFIX/system.reg" ]; then
  say "First run: creating the Wine prefix in $WINEPREFIX (takes a minute)..."
  xattr -dr com.apple.quarantine "$HERE/wine" 2>/dev/null || true
  "$WINE" wineboot --init >>"$LOG" 2>&1
  "$WINESERVER" -w
fi

mkdir -p "$WINEPREFIX/dosdevices" "$WINEPREFIX/drive_c/Games"
ln -sfn ../../cd "$WINEPREFIX/dosdevices/d:"
ln -sfn ../../../game "$WINEPREFIX/drive_c/Games/Dogfighter"

REG_SUM="$(shasum -a 256 "$REG" | cut -d' ' -f1)"
if [ "$(cat "$WINEPREFIX/.dogfighter-reg" 2>/dev/null || true)" != "$REG_SUM" ]; then
  say "Importing $REG"
  "$WINE" regedit /S "$REG" >>"$LOG" 2>&1
  "$WINESERVER" -w
  echo "$REG_SUM" > "$WINEPREFIX/.dogfighter-reg"
fi

SCREEN="$(screen_info)"
LIMIT=
RETINA=n
if [[ "$SCREEN" =~ ^([12])\ ([0-9]+)\ ([0-9]+)$ ]]; then
  scale="${BASH_REMATCH[1]}"
  [ "$SHARP" = 1 ] || scale=1
  if [ "$scale" = 2 ]; then RETINA=y; fi
  LIMIT="$((BASH_REMATCH[2] * scale))x$((BASH_REMATCH[3] * scale))"
fi
if [ "$(retina_in_prefix)" != "\"RetinaMode\"=\"$RETINA\"" ]; then
  say "Setting Wine RetinaMode to $RETINA for this screen."
  "$WINE" reg add 'HKCU\Software\Wine\Mac Driver' /v RetinaMode /t REG_SZ /d "$RETINA" /f >>"$LOG" 2>&1
  "$WINESERVER" -w
fi

if [ "$MODE" = windowed ] && [ -n "$LIMIT" ]; then
  if [ -z "$GAME_RES" ]; then
    GAME_RES="$(largest_fit)"
  elif ! fits "$GAME_RES"; then
    say "$GAME_RES does not fit on this screen ($LIMIT max); using $(largest_fit)."
    GAME_RES="$(largest_fit)"
  fi
fi
if [ -n "$GAME_RES" ] && [ "$GAME_RES" != "$(ini_size)" ]; then
  SECTION="$(game_section || true)"
  if [ -n "$SECTION" ]; then
    ini_set "$INI" "$SECTION" screen_width "${GAME_RES%x*}"
    ini_set "$INI" "$SECTION" screen_height "${GAME_RES#*x}"
    say "Game resolution set to $GAME_RES."
  else
    say "No video card in $INI yet; start the game once, then use --res."
  fi
fi
if [ "$MODE" = windowed ] && [ -z "$DESKTOP_SIZE" ]; then
  DESKTOP_SIZE="$(ini_size)"
  DESKTOP_SIZE="${DESKTOP_SIZE:-1024x768}"
fi

GAME_CMD=("$GAME_DOS\\Dogfighter.exe")
WATCH_PID=
if [ "$FOCUSFIX" = 1 ] && [ "$MODE" != winecfg ]; then
  FLAG="$WINEPREFIX/drive_c/dogfighter-focusfix.flag"
  cp "$FOCUSFIX_EXE" "$WINEPREFIX/drive_c/dogfighter-focusfix.exe"
  cp "$FOCUSHOOK_DLL" "$WINEPREFIX/drive_c/dogfighter-focushook.dll"
  GAME_CMD=('C:\dogfighter-focusfix.exe' 'C:\dogfighter-focusfix.flag' "$GAME_DOS\\Dogfighter.exe")
  watch_front "$FLAG" &
  WATCH_PID=$!
  trap 'kill "$WATCH_PID" 2>/dev/null || true' EXIT
  say "Focus fix on: the game keeps running after Cmd+Tab and comes back to the front on return."
fi

cd "$HERE"
case "$MODE" in
  winecfg)
    "$WINE" winecfg >>"$LOG" 2>&1
    ;;
  windowed)
    say "Starting Airfix Dogfighter in a ${DESKTOP_SIZE} window. Log: $LOG"
    "$WINE" explorer "/desktop=Dogfighter,$DESKTOP_SIZE" start /wait /d "$GAME_DOS" "${GAME_CMD[@]}" >>"$LOG" 2>&1 || true
    ;;
  fullscreen)
    say "Starting Airfix Dogfighter fullscreen. Log: $LOG"
    "$WINE" start /wait /d "$GAME_DOS" "${GAME_CMD[@]}" >>"$LOG" 2>&1 || true
    ;;
esac
"$WINESERVER" -w

if [ -n "$WATCH_PID" ]; then
  kill "$WATCH_PID" 2>/dev/null || true
  cat "$WINEPREFIX/drive_c/dogfighter-focusfix.log" >>"$LOG" 2>/dev/null || true
fi
if [ -f "$HERE/game/winmm.log" ]; then
  cp "$HERE/game/winmm.log" "${LOG%.log}-music.log"
fi
say "Done. Log: $LOG"
