# Airfix Dogfighter on Apple Silicon

An unofficial launcher for the Windows game Airfix Dogfighter (2000) on Apple Silicon Macs.
It runs the game through Wine.

[![Airfix Dogfighter for PC, gameplay video](https://img.youtube.com/vi/vuBLQVUCmEY/hqdefault.jpg)](https://www.youtube.com/watch?v=vuBLQVUCmEY)

*Gameplay video by [Highretrogamelord](https://www.youtube.com/@Highretrogamelord) on YouTube.*

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

| Option | What it does |
| --- | --- |
| (none) | Play in a window at the largest resolution that fits the screen. macOS scales it up on a Retina screen, so menu text stays readable. |
| `--res=WxH` | Use this game resolution instead, e.g. `--res=1440x900`. |
| `--sharp` | Use Retina pixels: sharper, but the menu text gets half as big. |
| `--windowed=WxH` | Force another Wine window size, e.g. `--windowed=1280x960`. |
| `--fullscreen` | Let the game switch the Mac's real display mode. |
| `--no-focusfix` | Turn off the focus fix (see Troubleshooting). |
| `--join=ADDRESS` | Put a server in the game's Address book, then start the game (see Online multiplayer). |
| `--winecfg` | Open Wine's settings for this game instead of playing. |
| `--doctor` | Check the installation and print a fix for each problem (see Self-test). |
| `--backup` | Copy your saves and settings to a dated zip file in `backups/` (see Saves). |
| `--restore[=FILE]` | Put a backup back: the newest one, or `FILE`. |

The first start creates a Wine prefix in `prefix/`, which takes a minute.
The disc image is not needed while playing: `cd/` acts as the CD in drive D:.

## CD music

The game plays its music from the CD's audio tracks.
Setup rips them to `music/Track02.ogg` to `Track11.ogg`.
A replacement `winmm.dll` ([ogg-winmm](https://github.com/dippy-dipper/ogg-winmm)) in `game/` plays them.

The in-game music slider works.
To override it, set a number from 0 to 99 in `game/winmm.ini`; 100 means "use the slider".

## Saves

Pilots, levels, photos and stickers live in `game/User`.
Screenshots (F12) go to `game/ScreenShots`.

```
./dogfighter --backup
```

This writes `backups/saves-<date>-<time>.zip`.
The zip holds `game/User`, `game/user.ini` and `game/system.ini`.
`backups/` is git-ignored.

```
./dogfighter --restore
./dogfighter --restore=saves-20260101-120000.zip
```

The first line puts the newest backup back.
The second one takes a file name from `backups/`, or a full path.
Restore replaces `game/User` and both settings files.
It first backs up what is there now, so nothing is lost.
Quit the game before you restore.

## Self-test

```
./dogfighter --doctor
```

It does not start the game.
It prints one line per check, with the fix for each failed one.
It exits with status 1 when a check failed.

It checks these things.
- Rosetta 2 is installed, and Wine is there and runs.
- macOS does not hold Wine in quarantine.
- The game files, the CD label and the ten music tracks are in place.
- The focus fix is built and newer than its source.
- The save folders in `game/User` exist.

## Online multiplayer

- The game uses UDP port 19400.
- Add the other players' addresses in the in-game Address book, or use `--join` (below).
- [Tailscale](https://tailscale.com) is the easiest way: everyone joins one tailnet and uses the Tailscale IP addresses. No port forwarding is needed.
- Without Tailscale, the host must forward UDP port 19400 to their Mac.
- All players need the same game version (see the top of `game/readme.txt`).
- Allow Wine through the macOS firewall. Click Allow when macOS asks, or add `wine/bin/wine` under System Settings > Network > Firewall > Options.

### Join a server by address

```
./dogfighter --join=100.64.0.7
```

This adds the address to the game's Address book and starts the game.
Open Multiplayer; the server is in the list when it is online.
The address stays in the Address book for later starts.

- Give an IP address or a host name, without a port.
- The game must have run once before, so that `game/user.ini` exists.
- The game cannot connect by itself at start: its menus open first.

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

- **Start here.** Run `./dogfighter --doctor`. It names what is broken and how to fix it.
- **Logs.** Each start writes `logs/run-<date>-<time>.log`. The music player's log is next to it, ending in `-music.log`.
- **Cmd+Tab.** The game was not made for task switching. The focus fix, on by default, keeps it running after Cmd+Tab and brings it back to the front when you return. If it says `focusfix.exe` or `focushook.dll` is missing, run `./setup.sh` again. Use `--no-focusfix` to test without it.
- **Tiny text.** `--sharp` halves the size of the menu text. Leave it off, or pick a smaller `--res`, for bigger text.
- **No music.** Check that `music/` holds ten `.ogg` files and that `game/winmm.dll` exists. Run `./setup.sh` again if not.
- **Disc not found.** `cd/.windows-label` must contain `Dogfighter`, with that exact case. Delete `cd/` and run `./setup.sh` again to rebuild it.

## Legal

For personal use with a disc you own.
Never commit or share the game files: `Dogfighter.bin`, `cd/`, `game/` or `music/`.
`.gitignore` keeps them out of git.
