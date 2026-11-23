#!/bin/bash
set -uo pipefail
RES="$(cd "$(dirname "$0")/../Resources" && pwd -P)"
STATE="$HOME/Library/Application Support/Dogfighter"
SHARED="wine-mach9 cd music hd-textures hd-videos build tools src dogfighter.reg"
ARGS=()
for arg in "$@"; do
  case "$arg" in -psn_*) ;; *) ARGS+=("$arg") ;; esac
done

alert() {
  /usr/bin/osascript -e 'on run argv' -e 'display alert "Airfix Dogfighter" message (item 1 of argv)' \
    -e 'end run' "$1" >/dev/null 2>&1 || true
}

fail() {
  echo "$1" >&2
  alert "$1"
  exit 1
}

seed_state() {
  local new="$STATE.new" item
  rm -rf "$new"
  mkdir -p "$new/game/User/Rosters" "$new/game/User/Save/Levels" "$new/game/User/Save/Photos" \
    "$new/game/User/Save/Stickers" "$new/game/ScreenShots" || return 1
  for item in User user.ini system.ini dogfighter-picture-before.txt; do
    if [ -e "$RES/saves/$item" ]; then /usr/bin/ditto "$RES/saves/$item" "$new/game/$item" || return 1; fi
  done
  mv "$new" "$STATE"
}

link_state() {
  local name dir file up target
  ln -sfn "$RES" "$STATE/app" || return 1
  for name in $SHARED; do ln -sfn "app/$name" "$STATE/$name" || return 1; done
  printf '#!/bin/bash\nexport DOGFIGHTER_HOME="$(cd "$(dirname "$0")" && pwd)"\nexec "$DOGFIGHTER_HOME/app/dogfighter" "$@"\n' \
    >"$STATE/dogfighter" && chmod +x "$STATE/dogfighter" || return 1
  find "$STATE/game" -type l ! -exec test -e {} \; -delete
  for name in user.ini system.ini; do
    target="$STATE/game/$name"
    if [ -L "$target" ] || [ ! -f "$target" ]; then
      rm -f "$target"
      cp "$RES/game/$name" "$target" || return 1
    fi
  done
  while IFS= read -r dir; do mkdir -p "$STATE/game/$dir" || return 1; done < <(cd "$RES/game" && find . -type d)
  while IFS= read -r file; do
    file="${file#./}"
    target="$STATE/game/$file"
    if [ -f "$target" ] && [ ! -L "$target" ]; then continue; fi
    up="$(printf %s "$file" | sed 's|[^/]*/|../|g; s|[^/]*$||')"
    ln -sfn "$up../app/game/$file" "$target" || return 1
  done < <(cd "$RES/game" && find . -type f)
  ln -sfn ../music "$STATE/game/Music"
}

if [ ! -d "$STATE" ]; then
  seed_state || fail "Could not make the folder $STATE for the game's saves and settings."
fi
link_state || fail "Could not set up $STATE for this app."

LAUNCHER=
stop_game() {
  trap - TERM INT HUP
  if [ -n "$LAUNCHER" ]; then kill -TERM "$LAUNCHER" 2>/dev/null || true; fi
  "$STATE/dogfighter" --stop
  wait
  exit 0
}
trap stop_game TERM INT HUP
"$STATE/dogfighter" ${ARGS[@]+"${ARGS[@]}"} &
LAUNCHER=$!
wait "$LAUNCHER"
status=$?
if [ "$status" != 0 ] && [ "${#ARGS[@]}" = 0 ]; then
  alert "The game did not start. The newest log in $STATE/logs says why."
fi
exit "$status"
