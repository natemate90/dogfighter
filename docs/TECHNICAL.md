# How it works

Technical notes for developers. The player's guide is the [README](../README.md).

This is an unofficial launcher for the Windows game Airfix Dogfighter (2000) on Apple Silicon Macs.
It runs the game through Wine.
The repo contains no game data. `setup.sh` builds everything from a raw image of the player's own disc.

## Parts

- `setup.sh` checks the Mac, downloads the pinned tools, unpacks the game from the disc image, rips the music and builds the helpers and `Dogfighter.app`.
- `dogfighter` is the launcher. It picks a Wine build, sets the game's settings and starts the game through the helper.
- The helper is `focusfix.exe` and `focushook.dll`. It puts the game in a normal Mac window, scales the picture, holds the mouse and does the picture work below.
- `tools/upscale-textures.py` makes the larger textures.

## Setup

Requirements, as `setup.sh` checks them:
- A Mac with Apple Silicon (M1 or later).
- macOS 26.4 or later to play without Rosetta. Setup then fetches Mach9, a Wine that needs none (see Wine builds).
- On older macOS, Rosetta 2: `softwareupdate --install-rosetta --agree-to-license`
- The Xcode Command Line Tools, for `clang` and `python3`: `xcode-select --install`
- About 5 GB of free disk space and an internet connection. On macOS before 26.4 it is about 3 GB.
- The disc as a raw image.

Setup downloads Mach9 0.4.0 on macOS 26.4 or later, Wine 11.0 (Gcenx build) where Rosetta is installed, and llvm-mingw, ogg-winmm, libogg and libvorbis.
It checks each download against a pinned SHA-256 checksum.

### The disc image

Make a raw image of the whole disc, with 2352-byte sectors.
With `cdrdao` (`brew install cdrdao`) and a CD drive, that is one line:

```
cdrdao read-cd --read-raw --datafile Dogfighter.bin --driver generic-mmc:0x20000 Dogfighter.toc
```

Any ripper that makes a single BIN/CUE image of the disc also works.
If you have a `.bin` and a `.cue`, use the `.bin`.
An `.iso` will not work: it has no music.

Put `Dogfighter.bin` in the repo folder and run `./setup.sh`, or pass its path: `./setup.sh path/to/Dogfighter.bin`.
If a step fails, fix the error it prints and run it again; finished steps are skipped.

To start the game from anywhere as `dogfighter`, link it into a folder on your PATH:

```sh
ln -s "$PWD/dogfighter" /opt/homebrew/bin/dogfighter
```

Setup prints this command when `/opt/homebrew/bin` or `~/.local/bin` is on your PATH.

### Language

The disc has English, French, German and Italian.
Setup installs English unless `--language=NAME` picks another.
Run it again with another language to switch.
Switching swaps the language pack, `game/readme.txt` and one line in `game/system.ini`.
Pilots and saves in `game/User` and the key bindings stay as they are.
Without `--language`, a later run keeps the installed language.

### Dogfighter.app

Setup also builds `Dogfighter.app` in the repo folder.
It runs `./dogfighter` with no options.
Its icon is made from `cd/Airfix.ico` on the player's Mac, so the app is not part of this repo.
The app remembers where the folder is. If the folder moves, run `./setup.sh` again and use the new app.

## The launcher

The first start creates a Wine prefix, which takes a minute: `prefix-mach9/` for Mach9, `prefix/` for the Rosetta Wine.
The disc image is not needed while playing: `cd/` acts as the CD in drive D:.

The game has a setup dialog for the driver, the language and advanced settings.
The launcher presses OK in it.
`--setup` shows the dialog and waits for OK.
The very first start always shows it.

### Window and mouse

The game opens in a normal Mac window that can be resized.
The picture is scaled to fill the window, so menu text stays readable.

The game holds the mouse while it is in front.
Ctrl+Option frees the mouse, for the title bar or another app.
To move the window, press Ctrl+Option, then drag the title bar.
Ctrl+Option again, or a click in the picture, gives the mouse back.
While the game holds the mouse, the launcher gives the Mac pointer an empty picture, so only the game's own cursor shows.
Ctrl+Option, the drag and the hidden pointer were seen working with Mach9 on an M4 Max.
The window title shows which of the two it is.
Cmd+Tab also frees the mouse, and the game takes it back on return.
The game was not made for task switching. The helper keeps it running after Cmd+Tab and brings it back to the front.

## Wine builds

There are two Wine builds, and the launcher picks one.

- [Mach9](https://github.com/athei/mach9) is a Wine build for Apple Silicon that needs no Rosetta. It runs the game's Intel code with its own emulator, FEX. It is the default on macOS 26.4 or later, when `wine-mach9/` is there.
- Wine 11.0 (Gcenx build) is an Intel program, so macOS runs it through Rosetta 2. It is the default on older macOS, and the fallback everywhere else. Apple removes most of Rosetta with macOS 28.

`./setup.sh` fetches Mach9 on macOS 26.4 or later and does not ask for Rosetta there.
It fetches the Rosetta Wine too when Rosetta is installed.

If the game does not start on Mach9, the launcher says so in one line and starts it on the Rosetta Wine.
That needs Rosetta and `wine/`.

Pick a build with `--wine`:

```
./dogfighter --wine=mach9
./dogfighter --wine=stable
```

- `--wine=mach9` uses `wine-mach9/` and `prefix-mach9/`. `--wine=stable` uses `wine/` and `prefix/`. Any other name uses `wine-NAME/` and `prefix-NAME/`.
- `--doctor` and `--winecfg` take the same option. Without it they follow the launcher's pick.
- `--stop` without `--wine` ends the game on both builds.
- Mach9 is tested on one Mac, an M4 Max, with Mach9 0.4.0. It is not tested on an M1.
- Mach9 is 1.1 GB unpacked, and its prefix about 770 MB.
- The game files in `game/`, the saves and the settings are shared by both builds.
- The two intro videos play on Mach9. Esc skips them.

What was measured on the M4 Max, in the first mission at 1280x800:

| | Rosetta Wine | Mach9 |
| --- | --- | --- |
| Frames a second in flight | about 30 | about 100 |
| Loading a mission | about 30 seconds | 2 to 5 seconds |
| Starts that needed a second try | about half | none of 27 |

The launcher gives Mach9 one setting by itself: `opengl=cgl`, Apple's OpenGL.
Mach9's own OpenGL ends the game at start on the Mac it was tested on.
`--wine-rule=KEY=VALUE` adds more Mach9 settings, or another `opengl=` value in place of that one. It can be given more than once, and only with Mach9.
For example, `--wine-rule=env=FEX_X87REDUCEDPRECISION=` turns on exact floating-point maths.
With that the game ran at 21 frames a second, so it is off by default.

Nobody has played a whole mission on Mach9 yet.
The menus, sound, Ctrl+Option, dragging the window and the hidden pointer were seen working with a real mouse on an M4 Max.

### Start crashes and restarts

The Rosetta Wine sometimes crashes or hangs while the game starts Direct3D.
The launcher sees this and starts the game again, up to eight times.
A crashed start costs a few seconds, a hung one 15 seconds.
A start that shows no picture within 15 seconds after the setup dialog counts as hung.

## Picture quality

At every start the launcher turns four of the game's settings up.

| Setting | Game default | Launcher |
| --- | --- | --- |
| Colour depth in flight (`screen_depth` in `game/system.ini`) | 16 bit | 32 bit |
| Draw distance (`view_distance` in `game/user.ini`) | 200 | 450, the game's maximum |
| Light shafts (`detail_volumetriclight`) | 0 | 2 |
| Rooms drawn through doorways (`view_portals`) | 4 | 5 |

It also makes the ground and walls sharper in the distance (16x anisotropic filtering).
It smooths the jagged edges of 3D shapes with 4 samples per pixel (multisampling).
The HUD and the menus keep their size.
On an M4 Max the frame rate stayed the same, on both Wine builds.
`--smooth=0` turns the smoothing off, and `--smooth=2` uses 2 samples.
Other settings and key bindings are not touched.

`--original` puts the four settings back to what they were and turns the sharper textures and the smooth edges off.
The old values are kept in `game/dogfighter-picture-before.txt` until then.
A draw distance set in the game's Options menu is raised again at the next start; `--original` keeps it.

`--res=WxH` sets the game resolution in flight, e.g. `--res=1440x900`. The menus are always 640x480. Without it, the largest size that fits the screen is used.
`--windowed=WxH` starts with the picture at most this big, e.g. `--windowed=1024x768`.

### `--full-res`

`--full-res` draws the picture with as many pixels as the window has on a Retina screen.
The HUD, the menus and all letters keep the size they have without it.
The game goes on working in its own resolution, 1280x800 in a flight and 640x480 in the menus.
The helper enlarges the surface the game draws into and moves every corner point the game draws to the larger surface.
So the edges of 3D shapes are drawn at the full size, not stretched afterwards.
Letters and the pictures in the menus and the HUD have no more detail than before: they are the same small pictures, enlarged while drawing.
The sharper letters below change that for the letters.

- On an M4 Max a flight ran at 62 to 89 frames a second at 2774x1734, with 4 samples per pixel.
- It works together with `--hd-textures`.
- F12 screenshots keep the game's own size.
- The picture follows the window when it is resized or zoomed, up to the screen's size.
- In a test, clicks on Info, Login and Campaign each landed on the button under the game's cursor.
- Nobody has looked at it on a screen yet.

### `--sharp`

`--sharp` uses Retina pixels: a sharper picture in flight, with a half-size HUD.
The flight is drawn with four times the pixels, which gives smoother edges on a Retina screen.
On an M4 Max the frame rate stayed the same, about 30 frames a second.

### `--retina`

`--retina` opens the window with the Retina screen's own pixels and keeps the game's resolution.
Wine then scales the picture once to those pixels, and macOS does not scale it a second time.
The HUD keeps its size.
Nobody has compared the two on a screen yet.

### `--deep-z`

`--deep-z` gives the game a 24-bit depth buffer where it asks for a 16-bit one.
That can stop far-away surfaces from flickering through each other.
In the first mission the picture was the same with and without it.

### `--keep-shape`

`--keep-shape` keeps the window in the shape of the game's picture when it is resized or zoomed.
Without it, a window dragged to another shape stretches the picture.
A zoomed window kept the 4:3 shape of the menus in a test; a drag by hand is not tried yet.

### `--wide`

`--wide` widens the view angle for a 16:10 or 16:9 picture.
It shows more at the sides and the top.
The bottom edge of the picture may show a stretched band in some scenes.
It stays opt-in until a person has judged it.

## Larger textures

The game shrinks every texture to at most 256 pixels a side.
`--hd-textures` raises that limit and loads larger copies of the 3D textures.
The copies are made once, on the player's Mac, from the player's own game files.
Nothing is uploaded, and nothing is downloaded unless the upscalers below are asked for.

```
python3 tools/upscale-textures.py
./dogfighter --hd-textures
```

- The first command needs only the Xcode Command Line Tools.
- It writes 1,192 textures and the 11 font pictures to `hd-textures/cache/`, twice as large as the originals.
- That takes under a minute and about 180 MB of disk space.
- The packs in `game/` are never changed.
- Without `--hd-textures` the game uses its own textures, as before.

Without the upscalers the resizer is the Lanczos filter that comes with macOS.
It gives smoother edges up close. It does not add detail.

### Upscalers that draw detail

```
python3 tools/upscale-textures.py --fetch-tools
python3 tools/upscale-textures.py
```

`./setup.sh --hd-textures` runs both after the normal setup.
A plain `./setup.sh` downloads none of this.

`--fetch-tools` downloads three archives, about 100 MB, to `downloads/upscale/`.
- `upscayl-bin` 20251207-174704, which runs the model.
- The Real-ESRGAN model `realesrgan-x4plus`, from the Real-ESRGAN release v0.2.5.0.
- `waifu2x-ncnn-vulkan` 20250915 with its `cunet` model, as the second choice.

Each archive is checked against a SHA-256 checksum pinned in the tool before it is unpacked.
Only the program and model files are unpacked, to `upscale-tools/`.
The tool refuses to run them when their checksums differ, unless `--allow-other-tools` is passed.

It ran once on an M4 Max, on all 1,192 textures, in 271 seconds.
Real-ESRGAN made 1,140 of them, waifu2x 50, the macOS filter 2, and none was refused.
The eight textures made a second time came out byte-identical.

Each texture goes through these steps.
- Invisible pixels get the colour of their visible neighbours, so no dark rim appears.
- A tiling texture gets a wrapped border of 16 pixels, cut off again afterwards.
- Real-ESRGAN makes it 4x, and for 2x that is averaged down.
- The result is pulled back to the original, so colours and shapes cannot drift.
- Alpha is resized by the macOS filter, never by the upscaler.

Then the texture is checked.
- Shrunk to the original size, it must match the original.
- A tiling texture must still tile.
- A texture that fails goes to waifu2x, then to the macOS filter.
- One that fails all three is not written, and the game uses its own.

The limits are at the top of `tools/upscale-textures.py`, with what each score means.
The limits are provisional.
In the one full run they sent 52 of 1,192 textures to the next way.

### The manifest and later runs

`hd-textures/manifest.json` lists every texture with the way it took and its scores.
The tool prints the count per way at the end.
It also makes eight textures a second time and says whether they came out the same.
A run that stops can be started again and goes on where it stopped.
A later run makes only what is missing or changed.
New files go into the set only after all of them are made.
`--only TEXT` makes the textures whose path contains the text, and leaves the rest of the set alone.

`--upscaler vimage` keeps the macOS filter even when the upscalers are there.
`--sheets FOLDER` writes pictures that put the macOS filter next to the set.

`--scale 4` makes textures four times as large, up to 1024 pixels.
That needs about 730 MB of disk space.
With the macOS filter it loaded in the first mission at the same frame rate, and looked much like 2x.
Longer missions are not tested: the game is a 32-bit program and may run out of memory.

Only textures on 3D shapes and the font pictures are resized.
Menus, loading screens, the HUD and the maps keep their size.
The game draws those at the size stored in the file, so larger files would break the layout.

### Generative detail for some surfaces

This is optional. It redraws 32 hand-picked surface textures four times as large, with new fine detail.
They are wood floors and boards, brick, slate, concrete, grass and cloth.
The list with a short prompt and a strength per texture is `tools/generative-surfaces.json`.

```
python3 tools/upscale-textures.py --fetch-tools --generative
python3 tools/upscale-textures.py
```

`./setup.sh --hd-textures --generative` does the same.

- It downloads about 6.6 GB to `upscale-tools/generative/`: a Python environment with the pinned packages of `tools/generative-requirements.txt`, and two models.
- The models are Stable Diffusion 1.5 (licence CreativeML OpenRAIL-M) and the ControlNet 1.1 tile model (licence OpenRAIL), at pinned revisions with pinned checksums.
- The tile model only comes as a pickle file. It is read once with a loader that cannot run code, and kept as safetensors.
- It needs Python 3.12 or later. The Xcode Command Line Tools have 3.9, so the tool looks for one from Homebrew or python.org.
- After that, a normal run uses it for the listed textures. `--no-generative` leaves it out.

How a listed texture is made:
- First the usual way above, at 2x.
- The model redraws that result at 4x, on the Mac's graphics card, with a fixed seed.
- A tiling texture is drawn so that it still tiles.
- The coarse shapes are then put back from the original.
- The result must stay close to the original and must not show a seam. Otherwise the 2x result is kept.
- The manifest lists it with the way `generative`, its prompt, strength, seed and the model checksums.

The checks do not catch everything the model invents.
So the list holds only textures whose result was looked at by eye.
In the first run 40 were listed.
Four failed the checks and four more were dropped after looking: a seam, a swirl pattern, and nails drawn as a metal bracket.

One run on an M4 Max, all 40 textures:
- 386 seconds in all, 4 to 8 seconds for a 512-pixel texture, 14 to 27 seconds for 1024 by 512.
- Free memory never went under 20%. The tool starts no new texture under 15% free and stops under 10%.
- Eight textures made a second time came out byte-identical. Another Mac may give slightly different pictures.
- The 32 textures take 29 MB instead of 7 MB.

In the game, with `--full-res --hd-textures`, the living room of the first Axis mission loaded without errors.
The floor boards showed finer grain.
No loss of frame rate was measured: 61 to 118 a second, against 52 to 81 with the usual set in the same scene.
Longer missions were not tested.

### Sharper letters

The game cuts its letters out of 11 font pictures in `Graphics\Fonts`.
The tool makes those twice as large and puts an empty file `<name>.gti.2x` next to each.
The helper draws a picture with that marker at its old size.
So letters keep their place and size, and get twice the pixels.

- The gain shows with `--full-res --hd-textures`, where a letter covers more screen pixels than the original has.
- waifu2x makes the letter shapes, and the macOS filter when the upscalers are missing.
- Real-ESRGAN is not used for letters: it left grey smears in them.
- The enlarged letter shapes, shrunk again, match the originals at 68 dB or better.
- A pixel that was empty stays empty, so no letter grows into its neighbour.
- This is not made with `--scale 4`.

One test run opened the Pilot Roster with `--full-res --hd-textures`.
The text stood in the same place and its strokes were crisper.
Other screens were not compared.
Window frames and other menu pictures do not work this way and are left alone.

### Your own textures

Put a `.gti` file in `texture-overrides/`, under the same path as in `hd-textures/cache/`.
The next run of the tool puts it in the set in place of the made texture.

- It must have the size, pixel format and number of mipmap levels of the made texture. Otherwise the tool refuses it and says why.
- It gets no other check.
- The manifest lists it with the way `override`.
- Change the file and the next run takes the new one.
- Remove the file and the next run puts the made texture back.

This is meant for textures where an upscaler garbled small lettering.
`texture-overrides/` is not part of the repository, because it holds game art.

### How the game finds them

- The game opens `cache\<path>` in its folder before it looks in its packs.
- The launcher links `game/cache` to `hd-textures/cache`, and removes the link without the option.
- The helper changes the 256-pixel limit in the running game's memory. No game file is changed.

`tools/gti.py` turns one texture into a PNG and back, for your own edits.
The file format is described at the top of `tools/gti.py`.
`tools/up.py` lists and unpacks the game's `.up` packs.

## CD music

The game plays its music from the CD's audio tracks.
Setup rips them to `music/Track02.ogg` to `Track11.ogg`.
A replacement `winmm.dll` ([ogg-winmm](https://github.com/dippy-dipper/ogg-winmm)) in `game/` plays them.

The in-game music slider works.
To override it, set a number from 0 to 99 in `game/winmm.ini`; 100 means "use the slider".

`--mute` starts the game without sound: no videos, music or effects. Other apps keep their sound, and the next start without it has sound again.

## Saves

Pilots, levels, photos and stickers live in `game/User`.
Screenshots (Fn + F12) go to `game/ScreenShots`.

`./dogfighter --backup` writes `backups/saves-<date>-<time>.zip`.
The zip holds `game/User`, `game/user.ini` and `game/system.ini`.
`backups/` is git-ignored.

`./dogfighter --restore` puts the newest backup back.
`./dogfighter --restore=saves-20260101-120000.zip` takes a file name from `backups/`, or a full path.
Restore replaces `game/User` and both settings files.
It first backs up what is there now, so nothing is lost.
Quit the game before restoring.

## Self-test

`./dogfighter --doctor` does not start the game.
It prints one line per check, with the fix for each failed one.
It exits with status 1 when a check failed.

It checks these things.
- The Wine build a plain `./dogfighter` uses is there and runs. For Mach9 that it needs no Rosetta, for the Rosetta Wine that Rosetta 2 is installed.
- With `--wine=mach9` or `--wine=stable` it checks that build.
- macOS does not hold Wine in quarantine.
- The game files, the CD label and the ten music tracks are in place.
- The helper is built and newer than its source.
- The save folders in `game/User` exist.

## Online multiplayer

- The game uses UDP port 19400.
- Add the other players' addresses in the in-game Address book, or use `--join`.
- [Tailscale](https://tailscale.com) is the easiest way: everyone joins one tailnet and uses the Tailscale IP addresses. No port forwarding is needed.
- Without Tailscale, the host must forward UDP port 19400 to their Mac.
- All players need the same game version (see the top of `game/readme.txt`).
- Allow Wine through the macOS firewall. Click Allow when macOS asks, or add `wine/bin/wine` (for Mach9 `wine-mach9/wine/bin/wine`) under System Settings > Network > Firewall > Options.

`./dogfighter --join=100.64.0.7` writes the address into the game's Address book and starts the game.
The Address book is kept in `game/user.ini`, as a line like `sets address_0 "100.64.0.7"`.
The line is still there after the game quits.
Nobody has checked yet that the Multiplayer screen then lists the server.
If it does not, type the address into the Address book in the game.

- Give an IP address or a host name, without a port.
- The game must have run once before, so that `game/user.ini` exists.
- The game cannot connect by itself at start: its menus open first.

## Controls

The key table in the README holds the defaults from `game/user.ini` and `game/readme.txt`.
Setup adds `x` for "next weapon" to a new `game/user.ini`, because MacBooks have no keypad.
An existing `game/user.ini` is never changed.

## Troubleshooting

- **Logs.** Each start writes `logs/run-<date>-<time>.log`. The music player's log is next to it, ending in `-music.log`.
- **The helper is missing.** If the launcher says `focusfix.exe` or `focushook.dll` is missing, run `./setup.sh` again.
- **Testing without the helper.** `--no-focusfix` runs the game in a plain Wine desktop window. The picture is not scaled, the window cannot be resized, the game stops when it loses the focus, and you press OK in the setup dialog yourself. The picture settings are the original ones, as with `--original`. A crashed start is started again, a hung one is not: end it with `./dogfighter --stop`.
- **No music.** Check that `music/` holds ten `.ogg` files and that `game/winmm.dll` exists. Run `./setup.sh` again if not.
- **Disc not found.** `cd/.windows-label` must contain `Dogfighter`, with that exact case. Delete `cd/` and run `./setup.sh` again to rebuild it.

## All launcher options

| Option | What it does |
| --- | --- |
| (none) | Play in a window you can resize. The picture is scaled to fill it. |
| `--res=WxH` | Use this game resolution in flight, e.g. `--res=1440x900`. The menus are always 640x480. Without it, the largest size that fits the screen is used. |
| `--full-res` | Draw the 3D picture with the Retina screen's own pixels and keep the HUD, the menus and the letters at normal size. |
| `--sharp` | Use Retina pixels: a sharper picture in flight, with a half-size HUD. |
| `--retina` | Draw the window with the Retina screen's own pixels and keep the game's resolution. |
| `--windowed=WxH` | Start with the picture at most this big, e.g. `--windowed=1024x768`. |
| `--wide` | Widen the view angle for a 16:10 or 16:9 picture. |
| `--hd-textures` | Use the larger textures. |
| `--smooth=N` | Smooth jagged edges with N samples per pixel: 0, 2 or 4. Without it the launcher uses 4. |
| `--deep-z` | Give the game a 24-bit depth buffer where it asks for 16 bits. |
| `--keep-shape` | Keep the window in the shape of the game's picture when you resize or zoom it. |
| `--original` | Leave the picture settings as the game made them. |
| `--mute` | Start the game without sound. |
| `--join=ADDRESS` | Put a server in the game's Address book, then start the game. |
| `--setup` | Show the game's setup dialog and wait for OK. |
| `--no-focusfix` | Start without the helper (see Troubleshooting). |
| `--wine=NAME` | Pick the Wine build: `--wine=mach9` or `--wine=stable`, the Rosetta Wine. Any other name uses `wine-NAME/` and `prefix-NAME/`. |
| `--wine-rule=KEY=VALUE` | Only with Mach9: one Mach9 setting for the game. Can be given more than once. |
| `--stop` | End a running game and all its Wine processes, on both Wine builds. |
| `--debug=CHANNELS` | Write Wine debug channels to the log, e.g. `--debug=+seh`. |
| `--diag` | Write the game's windows, display mode and cursor state to the log. |
| `--winecfg` | Open Wine's settings for this game instead of playing. |
| `--doctor` | Check the installation and print a fix for each problem. |
| `--backup` | Copy saves and settings to a dated zip file in `backups/`. |
| `--restore[=FILE]` | Put a backup back: the newest one, or `FILE`. |

### Test options

`--diag` has test modes that run with nobody at the screen.
`./dogfighter --help` describes each one.
A run with any `--diag` option does not hold the mouse, so the Mac stays usable, and it is muted.

| Option | What it does |
| --- | --- |
| `--diag=focus-test[:SECONDS]` | Takes the focus away and gives it back, frees and takes the mouse, resizes and zooms the window, then ends the game. |
| `--diag=move-test` | Frees the mouse, moves the window by 160,100, sends a click for the picture and logs the window and the mouse rectangle after each step. |
| `--diag=start-test` | Ends the game after 8 seconds of picture. |
| `--diag=stall-test` | As start-test, but treats the first start as one that never drew. |
| `--diag=crash-test` | As start-test, but ends the first start as its setup dialog closes. |
| `--diag=fallback-test` | As start-test, but ends every start on a Mach9 picked without `--wine`. |
| `--diag=draw-test` | Runs a small test program that draws straight to the screen surface. |
| `--diag=press-ok` | For `--no-focusfix`: presses OK in the setup dialog. |
| `--diag=press-cancel` | For `--setup`: presses Cancel there. |
| `--diag-keys=SECONDS:SCANCODE,...` | Presses keys, as scan codes in hex. `1d38` presses Ctrl+Option. |
| `--diag-mouse=SECONDS:DX:DY[:c\|:o],...` | Moves the mouse, and with `:c` clicks. |
| `--diag-console=SECONDS:COMMAND` | Runs a game console command, with `+` for each space. |
| `--diag-display=right` | Opens the game window on the display furthest to the right. |
| `--diag-hold` | Holds the mouse, as a normal start does. |
| `--diag-sound` | Keeps the sound, as a normal start does. |
| `--diag-end=SECONDS` | Ends the game this long after its first picture, without the game's own quit. |
| `--diag-zoom=SECONDS` | Zooms the window this long after the first picture. |
| `--diag-drag=SECONDS` | Asks for seven window sizes as a drag does, and logs what the window became. |

### Options of setup.sh

| Option | What it does |
| --- | --- |
| `--language=NAME` | English, French, German or Italian. |
| `--hd-textures` | After the normal setup, fetch the upscalers and make the larger textures. |
| `--generative` | With `--hd-textures`: also set up the generative way. |
| `path/to/Dogfighter.bin` | The disc image, if it is not `./Dogfighter.bin`. |

## Not tested yet

Collected from the sections above.
- Mach9 on an M1. Nobody has played a whole mission on Mach9.
- `--full-res`: nobody has looked at it on a screen.
- `--retina`: nobody has compared it with the default on a screen.
- `--keep-shape`: a drag by hand.
- `--wide`: not judged by a person.
- `--deep-z`: only the first mission was compared.
- `--scale 4` and the generative textures: longer missions.
- Sharper letters: only the Pilot Roster was compared.
- `--join`: whether the Multiplayer screen lists the server.

## Legal

For personal use with a disc you own.
Never commit or share the game files: `Dogfighter.bin`, `cd/`, `game/`, `music/`, `hd-textures/` or `Dogfighter.app`.
`.gitignore` keeps them out of git.
