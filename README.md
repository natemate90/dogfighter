# Airfix Dogfighter on Apple Silicon

An unofficial launcher for the Windows game Airfix Dogfighter (2000) on Apple Silicon Macs.
It runs the game through Wine.

You need your own original Airfix Dogfighter CD.
This repo contains no game data.
`setup.sh` builds everything from an image of your disc.

Airfix Dogfighter © 2000 Unique Development Studios / Paradox Entertainment.
Airfix is a trademark of Hornby.
This project is not affiliated with any of them.

## Requirements

- A Mac with Apple Silicon (M1 or later).
- Rosetta 2: `softwareupdate --install-rosetta --agree-to-license`
- The Xcode Command Line Tools, for `clang` and `python3`: `xcode-select --install`
- About 3 GB of free disk space and an internet connection.
- Your Airfix Dogfighter CD, as a raw image (see below).

Setup downloads Wine 11.0 (Gcenx build), llvm-mingw, ogg-winmm, libogg and libvorbis.
It checks each download against a pinned SHA-256 checksum.

## Setup

Make a raw image of the whole disc, with 2352-byte sectors.
With `cdrdao` (`brew install cdrdao`) and a CD drive, that is one line:

```
cdrdao read-cd --read-raw --datafile Dogfighter.bin --driver generic-mmc:0x20000 Dogfighter.toc
```

Any ripper that makes a single BIN/CUE image of the disc also works.
If you have a `.bin` and a `.cue`, use the `.bin`.
An `.iso` will not work: it has no music.

Put `Dogfighter.bin` in this folder and run:

```
./setup.sh
```

Or pass its path: `./setup.sh path/to/Dogfighter.bin`.
Setup takes a few minutes.
If a step fails, fix the error it prints and run it again; finished steps are skipped.

To start the game from anywhere as `dogfighter`, link it into a folder on your PATH:

```sh
ln -s "$PWD/dogfighter" /opt/homebrew/bin/dogfighter
```

Setup prints this command when `/opt/homebrew/bin` or `~/.local/bin` is on your PATH.

## Running

```
./dogfighter
```

Once linked, `dogfighter` works from any folder.

The game opens in a normal Mac window.
Drag an edge to resize it, or use the green button.
The picture is scaled to fill the window, so menu text stays readable.

The game holds the mouse while it is in front.
Press Ctrl+Option to free the mouse, for the title bar or another app.
Press Ctrl+Option again to give it back.
The window title shows which of the two it is.
Cmd+Tab also frees the mouse, and the game takes it back when you return.

| Option | What it does |
| --- | --- |
| (none) | Play in a window you can resize. The picture is scaled to fill it. |
| `--res=WxH` | Use this game resolution in flight, e.g. `--res=1440x900`. The menus are always 640x480. Without it, the largest size that fits the screen is used. |
| `--sharp` | Use Retina pixels: a sharper picture in flight. |
| `--windowed=WxH` | Start with the picture at most this big, e.g. `--windowed=1024x768`. |
| `--wide` | Widen the view angle to fit a picture wider than 4:3 (see Picture quality). |
| `--original` | Leave the picture settings as the game made them (see Picture quality). |
| `--setup` | Show the game's setup dialog and wait for OK. |
| `--no-focusfix` | Start without the helper (see Troubleshooting). |
| `--stop` | End a running game and all its Wine processes. |
| `--debug=CHANNELS` | Write Wine debug channels to the log, e.g. `--debug=+seh`. |
| `--diag` | Write the game's windows, display mode and cursor state to the log. |
| `--winecfg` | Open Wine's settings for this game instead of playing. |

The first start creates a Wine prefix in `prefix/`, which takes a minute.
The disc image is not needed while playing: `cd/` acts as the CD in drive D:.

The game has a setup dialog for the driver, the language and advanced settings.
The launcher presses OK in it for you.
Use `--setup` to see the dialog.
The very first start always shows it.

`--diag` has test modes that run with nobody at the screen.
`./dogfighter --help` lists them.

## Picture quality

At every start the launcher turns four of the game's settings up.

| Setting | Game default | Launcher |
| --- | --- | --- |
| Colour depth in flight (`screen_depth` in `game/system.ini`) | 16 bit | 32 bit |
| Draw distance (`view_distance` in `game/user.ini`) | 200 | 450, the game's maximum |
| Light shafts (`detail_volumetriclight`) | 0 | 2 |
| Rooms drawn through doorways (`view_portals`) | 4 | 5 |

It also makes the ground and walls sharper in the distance (16x anisotropic filtering).
Your other settings and key bindings are not touched.

`--original` puts the four settings back to what they were and turns the sharper textures off.
The old values are kept in `game/dogfighter-picture-before.txt` until then.
A draw distance you set in the game's Options menu is raised again at the next start; use `--original` to keep it.

`--sharp` gives smoother edges on a Retina screen: the flight is drawn with four times the pixels.
On an M4 Max the frame rate stayed the same, about 30 frames a second.

`--wide` widens the view angle for a 16:10 or 16:9 picture.
Without it the game cuts off the top and bottom of the 4:3 view.
It is not the default, because the glow around lamps is not drawn while it is on.

## CD music

The game plays its music from the CD's audio tracks.
Setup rips them to `music/Track02.ogg` to `Track11.ogg`.
A replacement `winmm.dll` ([ogg-winmm](https://github.com/dippy-dipper/ogg-winmm)) in `game/` plays them.

The in-game music slider works.
To override it, set a number from 0 to 99 in `game/winmm.ini`; 100 means "use the slider".

## Saves

Pilots, levels, photos and stickers live in `game/User`.
Screenshots (F12) go to `game/ScreenShots`.
Back up `game/User` to keep your pilots.

## Online multiplayer

- The game uses UDP port 19400.
- Add the other players' addresses in the in-game Address book.
- [Tailscale](https://tailscale.com) is the easiest way: everyone joins one tailnet and uses the Tailscale IP addresses. No port forwarding is needed.
- Without Tailscale, the host must forward UDP port 19400 to their Mac.
- All players need the same game version (see the top of `game/readme.txt`).
- Allow Wine through the macOS firewall. Click Allow when macOS asks, or add `wine/bin/wine` under System Settings > Network > Firewall > Options.

## Controls

These are the defaults from `game/user.ini` and `game/readme.txt`.

| Key | Action |
| --- | --- |
| Up / Down arrows | Pitch |
| Left / Right arrows | Bank left / right |
| d / c | Throttle up / down |
| Space | Fire primary weapon (machine guns) |
| z | Fire secondary weapon |
| Keypad 0 | Next weapon |
| 1 | Cannon |
| 2 | Rockets |
| 3 | Bombs |
| 4 | Tesla coil |
| 5 | Particle beam |
| 6 | Homing missile |
| 7 | Paramines |
| 8 | A-bomb |
| Mouse | Look around (on by default, inverted) |
| Left Shift | Rear view |
| F1 | Change camera view |
| F2 | Message window |
| Tab | Mission info / multiplayer info |
| p | Pause |
| Esc | Menu |
| F12 | Screenshot |

Joystick input is off by default; turn it on in Options.

| Joystick button | Action |
| --- | --- |
| 1 | Fire primary weapon |
| 2 | Fire secondary weapon |
| 3 | Next weapon |
| 4 | Rear view |
| 5 | Change camera view |

The House Editor and Paint Room have their own keys.
They are listed in sections 1.1 and 1.2 of `game/readme.txt`.

## Troubleshooting

- **Logs.** Each start writes `logs/run-<date>-<time>.log`. The music player's log is next to it, ending in `-music.log`.
- **Slow start.** Wine sometimes crashes or hangs while the game starts Direct3D. The launcher sees this and starts the game again, up to eight times. A crashed start costs a few seconds, a hung one 15 seconds. A start that shows no picture within 15 seconds after the setup dialog counts as hung.
- **The mouse is stuck in the window.** Press Ctrl+Option. The game holds the mouse on purpose while you play.
- **Cmd+Tab.** The game was not made for task switching. The helper keeps it running after Cmd+Tab and brings it back to the front when you return.
- **The helper is missing.** If the launcher says `focusfix.exe` or `focushook.dll` is missing, run `./setup.sh` again.
- **Testing without the helper.** `--no-focusfix` runs the game in a plain Wine desktop window. The picture is not scaled, the window cannot be resized, the game stops when it loses the focus, and you press OK in the setup dialog yourself. The picture settings are the original ones, as with `--original`. A crashed start is started again, a hung one is not: end it with `./dogfighter --stop`.
- **Tiny text.** Make the window bigger. The picture grows with it.
- **Game still running.** `./dogfighter --stop` ends a game that hangs or that you cannot reach.
- **No music.** Check that `music/` holds ten `.ogg` files and that `game/winmm.dll` exists. Run `./setup.sh` again if not.
- **Disc not found.** `cd/.windows-label` must contain `Dogfighter`, with that exact case. Delete `cd/` and run `./setup.sh` again to rebuild it.

## Legal

For personal use with a disc you own.
Never commit or share the game files: `Dogfighter.bin`, `cd/`, `game/` or `music/`.
`.gitignore` keeps them out of git.
