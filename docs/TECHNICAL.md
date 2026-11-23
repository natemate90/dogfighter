# How it works

Technical notes for developers. The player's guide is the [README](../README.md).

This is an unofficial launcher for the Windows game Airfix Dogfighter (2000) on Apple Silicon Macs.
It runs the game through Wine.
The repo contains no game data. `setup.sh` builds everything from a raw image of the player's own disc.

## Parts

- `setup.sh` checks the Mac, downloads the pinned tools, unpacks the game from the disc image, rips the music, builds the helpers and `Dogfighter.app`, and makes the larger textures.
- `dogfighter` is the launcher. It picks a Wine build, sets the game's settings and starts the game through the helper.
- The helper is `focusfix.exe` and `focushook.dll`. It puts the game in a normal Mac window, scales the picture, holds the mouse and does the picture work below.
- `build/intro-player` plays the sharper intro videos before the game starts. Setup builds it from `tools/intro-player.m` with `cc`.
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
It runs `./dogfighter` with no options, so it gets the same defaults as a start from Terminal.
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

### The pointer in the menus

The game moves its menu pointer by `mouse_sensitivity` / 1000 times the square of each mouse move, in pixels of its own picture.
That is in `NfMain::Input` in `AfEngine.dll`. The default `mouse_sensitivity` is 100.
- A move twice as fast takes the pointer four times as far. The slider in Options changes the factor, not the square.
- With full resolution Wine counts the window's pixels, two for each point on a Retina screen. So every move is twice the number and takes the pointer four times as far.
- The picture is no larger on the screen for that. So the pointer was too fast, at every setting of the slider.

The helper makes the pointer move as far over the picture as the Mac pointer moves over the window.
- Wine's DirectInput gets each mouse move from a hook. The helper stands in front of that hook.
- While the game shows its pointer, it replaces each move by the one whose square gives the right way. What rounding leaves over goes into the next move.
- It reads `mouse_sensitivity` from the game. At 100, the game's own value, the pointer goes exactly as far as the Mac pointer. The slider "Menu mouse sensitivity" in Options makes the way longer or shorter in proportion: 50 is half.
- The speed and the acceleration are the Mac's own, from System Settings.
- In a flight the game hides its pointer. The moves then stay as they are, so steering with the mouse is not changed.
- Only a build of `AfEngine.dll` with exactly that code is touched.
- `--no-pointer-match` turns it off.

Test runs sent mouse moves and asked the game where its pointer was, with the console command `pointer` of the test tool.
In a 2301x1726 window, moves adding up to 400,100 took the pointer from 29.8,18.6 to 141.3,46.4 in the 640x480 picture. That is 111.5,27.8, and the same share of the window is 111.3,27.8.
- The first move of that run, 100,60 after a fast move into the corner, ended 2 pixels too far. That is what the fast move's rounding had left over.
- With `mouse_sensitivity` 50 a move of 100,60 gave 14.9,9.6, half the way.
- In a flight's Esc menu, 1280x800 in a 2761x1726 window, 100,60 gave 46.4,27.8. In the flight itself the moves were not changed.
Nobody has tried it with a real mouse yet.

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

### One game at a time

The launcher refuses a second start while a game runs: "Dogfighter is already running. Stop it with ./dogfighter --stop."
- The lock is one per installation, not per Wine build, because both builds share `game/`, its settings and the `game/cache` link.
- The lock is `game/.dogfighter-running`, a file that holds the launcher's process id. macOS's `/usr/bin/shlock` makes it. It goes when the launcher ends.
- A lock whose process is gone is taken over. So a crashed launcher does not block the next start.
- If another program got that process id since, the lock still counts as held. `./dogfighter --stop` removes it.
- `--stop`, `--doctor` and `--backup` work while a game runs. `--restore` refuses then, as before.
- The fallback to the Rosetta Wine keeps the same process, so it keeps the lock.

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

By default the launcher also draws at full resolution and uses the larger textures, both described below.

`--original` puts the four settings back to what they were and turns the anisotropic filtering and the smooth edges off.
It also turns full resolution and the larger textures off, unless `--full-res` or `--hd-textures` is given too.
The old values are kept in `game/dogfighter-picture-before.txt` until then.
A draw distance set in the game's Options menu is raised again at the next start; `--original` keeps it.

`--res=WxH` sets the game resolution in flight, e.g. `--res=1440x900`. The menus are always 640x480. Without it, the largest size that fits the screen is used.
`--windowed=WxH` starts with the picture at most this big, e.g. `--windowed=1024x768`.
The size is in points, the unit of Mac window sizes. Where the launcher turns Wine's `RetinaMode` on, it hands the helper twice the numbers, because Wine counts pixels then.

### Full resolution

Full resolution is on by default. It draws the picture with as many pixels as the window has on a Retina screen.
The HUD, the menus and all letters keep the size they have without it.
The game goes on working in its own resolution, 1280x800 in a flight and 640x480 in the menus.
The helper enlarges the surface the game draws into and moves every corner point the game draws to the larger surface.
So the edges of 3D shapes are drawn at the full size, not stretched afterwards.
Letters and the pictures in the menus and the HUD have no more detail than before: they are the same small pictures, enlarged while drawing.
The sharper letters below change that for the letters.

- On an M4 Max a flight ran at 62 to 89 frames a second at 2774x1734, with 4 samples per pixel.
- It works together with the larger textures.
- F12 screenshots keep the game's own size.
- The picture follows the window when it is resized or zoomed, up to the screen's size.
- In a test, clicks on Info, Login and Campaign each landed on the button under the game's cursor.
- Nobody has looked at it on a screen yet.

How the options combine:
- `--no-full-res` turns it off. The game then draws in its own resolution and the picture is scaled to the window.
- `--sharp`, `--retina` and `--original` turn it off, because each asks for another picture.
- `--full-res` given together with one of those keeps it on.
- `--no-focusfix` turns it off. `--full-res` with `--no-focusfix` is refused: it needs the helper.
- Each start writes `Full resolution on` or `Full resolution off` to the log.
- A test run saves pictures of the full-size surface to `logs/shots/` only when `--full-res` is given.

### `--sharp`

`--sharp` uses Retina pixels: a sharper picture in flight, with a half-size HUD. It turns full resolution off.
The flight is drawn with four times the pixels, which gives smoother edges on a Retina screen.
On an M4 Max the frame rate stayed the same, about 30 frames a second.

### `--retina`

`--retina` opens the window with the Retina screen's own pixels and keeps the game's resolution.
Wine then scales the picture once to those pixels, and macOS does not scale it a second time.
The HUD keeps its size.
It turns full resolution off.
Nobody has compared it with full resolution off on a screen yet.

### `--deep-z`

`--deep-z` gives the game a 24-bit depth buffer where it asks for a 16-bit one.
That can stop far-away surfaces from flickering through each other.
In the first mission the picture was the same with and without it.

### The shape of the window

The window keeps the shape of the game's picture when it is resized or zoomed.
That is 4:3 in the menus and the shape of the flight resolution in a flight, for example 16:10.
- The helper answers `WM_SIZING`, which Wine's Mac driver asks during a drag. The side that moved further leads and the other follows.
- It also shapes every other change of size in `WM_WINDOWPOSCHANGING`, such as the green button.
- The picture always fills the window, so there are no bars. Bars would need a second draw each frame, and the mouse would have to be kept inside the picture and not the window.
- `--wide` does not change this. It widens the view angle for the flight resolution's shape, and the window has that shape.
- `--no-keep-shape` lets the window take any shape. The picture is then stretched to fill it.
- `--keep-shape` is still accepted. It is the default.

In a test run the test tool asked for seven sizes as a drag does. The picture kept 4:3 each time, for example 2461x1846 and 2715x2036.
A zoomed window kept the 4:3 shape of the menus in an earlier test. A drag by hand is not tried yet.

### `--fps=N`

`--fps=N` shows at most N pictures a second, from 15 to 1000.
Without it the game draws as fast as the screen shows pictures: 120 a second on a ProMotion display.
- The helper waits before it shows a picture, until 1/N second after the one before.
- Each picture is due a fixed time after the last one was due, so a wait that runs long is made up for.
- The game's own speed does not change. Only the number of pictures does.

### `--wide`

`--wide` widens the view angle for a 16:10 or 16:9 picture.
It shows more at the sides and the top.
The bottom edge of the picture may show a stretched band in some scenes.
It stays opt-in until a person has judged it.

## Larger textures

The game shrinks every texture to at most 256 pixels a side.
The launcher raises that limit and loads larger copies of the 3D textures.
The copies are made once, on the player's Mac, from the player's own game files.
Nothing is uploaded.

The launcher uses them by default when `hd-textures/` holds a complete set.
- Complete means: `texture-limit` says 512 or 1024, and every texture that `manifest.json` lists as made is in `cache/`.
- The tool writes `manifest.json` last, so a run that stopped halfway does not count.
- Without a complete set the game starts with its own textures, and the launcher says in one line to run `./setup.sh`.
- `--no-hd-textures` turns them off. So does `--original`, unless `--hd-textures` is given too.
- `--hd-textures` is still accepted. It is the default.

Without the upscalers below, the tool needs only the Xcode Command Line Tools:

```
python3 tools/upscale-textures.py
```

- It writes 1,192 textures and the 11 font pictures to `hd-textures/cache/`, twice as large as the originals.
- It also writes 640 menu and HUD pictures, two or four times as large (see [Menus and loading screens](#menus-and-loading-screens)).
- That takes about 980 MB of disk space: about 180 MB for the textures, the rest for the menu pictures.
- The packs in `game/` are never changed.

Without the upscalers the resizer is the Lanczos filter that comes with macOS.
It gives smoother edges up close. It does not add detail.

### Upscalers that draw detail

```
python3 tools/upscale-textures.py --fetch-tools
python3 tools/upscale-textures.py
```

`./setup.sh` runs both after the normal setup, but only when `hd-textures/` holds no complete set.
`python3 tools/upscale-textures.py --check` gives that answer; the launcher asks the same question.
A complete set stays as it is, whatever settings made it, for example `--scale 4`, `--upscaler vimage` or `--allow-other-tools`.
Setup then fetches no upscalers either, so upscalers of your own in `upscale-tools/` stay too.
It only adds missing menu pictures and redraws the labels, letters, desk, paintings and stamps (see [Redrawn labels](#redrawn-labels)).
To make the set again, run the tool yourself, or move `hd-textures/` away and run `./setup.sh`.
`./setup.sh --no-hd-textures` skips the step.

Setup never fails on this step:
- When the download fails, the second command uses the macOS filter.
- When the upscalers do not run, for example without access to the graphics card, setup runs the tool again with `--upscaler vimage`.
- When that fails too, setup says so and goes on. The game then uses its own textures.

A set made with the macOS filter is complete too. A later `./setup.sh` does not replace it with an upscaled one.
The tool on its own also skips finished work: a second run over the full set on an M4 Max took 3 seconds and changed nothing.

`--fetch-tools` downloads three archives, about 100 MB, to `downloads/upscale/`.
- `upscayl-bin` 20251207-174704, which runs the model.
- The Real-ESRGAN model `realesrgan-x4plus`, from the Real-ESRGAN release v0.2.5.0.
- `waifu2x-ncnn-vulkan` 20250915 with its `cunet` model, as the second choice.

It also fetches four fonts: three for the [redrawn labels](#redrawn-labels) and Oswald for the desk.
And it fetches the pictures and Python packages of [the desk](#the-desk-on-the-main-menu), the plane paintings and the stamps.

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

The game draws a flat picture at the size stored in its file.
So the font pictures and the menu pictures get a marker file, and the helper keeps their size (see [Markers](#markers-for-flat-pictures-with-more-pixels)).
Flat pictures that `tools/menu-pictures.json` does not list keep the game's own files.

### Generative detail for some surfaces

This is optional. It redraws 32 hand-picked surface textures four times as large, with new fine detail.
They are wood floors and boards, brick, slate, concrete, grass and cloth.
The list with a short prompt and a strength per texture is `tools/generative-surfaces.json`.

```
python3 tools/upscale-textures.py --fetch-tools --generative
python3 tools/upscale-textures.py
```

`./setup.sh --generative` does the same when no complete set is there yet.
With a complete set it only fetches the generative way and prints the second command, because it leaves a complete set alone.
A failure in this opt-in step stops setup.

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

In the game, with full resolution and the larger textures, the living room of the first Axis mission loaded without errors.
The floor boards showed finer grain.
No loss of frame rate was measured: 61 to 118 a second, against 52 to 81 with the usual set in the same scene.
Longer missions were not tested.

### Sharper letters

The game cuts its letters out of 11 font pictures in `Graphics\Fonts`, with the boxes of 8 `.fnt` tables.
The tool makes those twice as large and puts an empty file `<name>.gti.2x` next to each.
The helper draws a picture with that marker at its old size.
So letters keep their place and size, and get twice the pixels.

- The gain shows with full resolution, where a letter covers more screen pixels than the original has.
- waifu2x makes the letter shapes, and the macOS filter when the upscalers are missing.
- Real-ESRGAN is not used for letters: it left grey smears in them.
- The enlarged letter shapes, shrunk again, match the originals at 68 dB or better.
- A pixel that was empty stays empty, so no letter grows into its neighbour.
- This is not made with `--scale 4`.

#### Letters drawn from the fonts

Four of the fonts are typefaces that come with macOS.
For those, every glyph is then drawn again from the typeface, with four times the pixels, by `tools/fonts.py`.
The picture gets the marker `<name>.gti.4x` in place of `.2x`.
No upscaler and no AI is involved, and nothing is downloaded.

| Font | Typeface | Seen in the game | Glyphs drawn | Kept as made |
| --- | --- | --- | --- | --- |
| `typewriter` (2 pictures) | American Typewriter | Pilot Login, Pilot Roster, Mission Info, the message line in flight, the version label | 103 | 5: `Å` `-` `=` `#` `ß` |
| `typewriter_small` (2 pictures) | American Typewriter | the mission book and the briefing papers | 100 | 6: `Å` `Ü` `È` `%`, the check mark `¤`, `ß` |
| `system` | Arial | the console after `console_changefont system` | 70 | none |
| `system12` | Helvetica | the console after `console_changefont system12` | 89 | 4: `#` `~` `¤` `|` |

`system8`, `aeroplane`, `digital_large` and `digital_small` keep the waifu2x way. They are drawn by hand or their typeface was not found. `system8` is the console's own font.

How it works:
- `tools/fonts.json` holds the numbers each run draws from. Per font: the face, size, stretch and weight. Per glyph box: the character drawn, the left edge of its ink, its baseline and its size.
- The glyphs are drawn with the CoreText helper `tools/lettering-draw.c`.
- The `.fnt` tables do not change. Each glyph is drawn into its own box. Pixels outside the drawn boxes come from the made picture.
- Where several characters share a box, the one that fits best is drawn. So `system` draws Y where its table says Ü, as the game does.
- Alpha is the glyph's coverage times the font's gain. The colour is the one the original picture has at that alpha, so a font whose colour follows its alpha keeps doing so.
- Each glyph is drawn heavier than the typeface and only partly opaque. The game enlarges its small letters the smooth way, so on screen their strokes are about one original pixel wide and grey, not black.
- `weight` (original pixels added round each stroke) and `gain` (the alpha of a fully covered pixel) set that per font. For each weight, the gain that keeps the original's amount of ink was taken, and the pair whose glyphs, softened by one pixel at 4x, came closest to the original enlarged 4x the smooth way.
- The two typewriter fonts use weight 0.18 with gain 0.71 and 0.69. That fit was lightest at weight 0.35 to 0.4 with gain 0.5, but those letters looked lighter than the original's in the game. `system` and `system12` use weight 0.3 with gain 0.69 and 0.68.
- The made 2x picture stays in `hd-textures/replaced/`, and the manifest lists the picture with the way `font`.

Checks, for each glyph:
- The glyph is drawn with 3 pixels of room around its box and shrunk to the original size.
- Inside the box it is compared with the original alpha. Ink outside the box counts as difference, since the box cuts it off.
- The match runs from 0 to 100: 100 × (1 − difference / sum of both). It must reach 60. This only catches a wrong glyph: the heavier, lighter strokes score 65 to 94 at the right place, and a glyph one pixel off often scores as well.
- The glyph is also drawn one original pixel left, right, up and down. At its own place it must match at least 1 point better than at each of those. A glyph one pixel off has its right place next to it, which matches better, so it fails.
- At most 5% of the glyph's ink may fall outside the box, measured on the glyph drawn with weight 0 and full alpha. The extra weight would put up to 24% there; the box cuts that off, as the game's own glyphs are cut.
- Tested on all 363 drawn glyphs and their 1,452 one-pixel shifts: 362 glyphs pass and every shift fails. The one glyph that fails is the bar `|` of `system12`. It fills its box from top to bottom, so one pixel up matches exactly as well, and it keeps the made pixels.
- A glyph that fails keeps the made pixels. The kept glyphs in the table fail one of these.
- Outside the drawn boxes, the new picture must equal the made picture pixel for pixel. Else the whole picture stays as made.

Options and runs:
- `--no-font-redraw` puts the made 2x pictures back.
- `--font-times 2` draws them with twice the pixels instead of four times.
- `--lettering-only` redraws the fonts as well, so `./setup.sh` applies them to an existing set.
- A typeface missing on a Mac leaves its font as made, and the run says so in one line.
- Two runs in a row gave the same bytes. `--no-font-redraw` gave back the old set byte for byte, manifest records included.
- Drawing the six pictures takes about 1.5 seconds.

In the game, with full resolution:
- The Pilot Login, the Pilot Roster, the mission book, the briefing, the message line in flight, Mission Info and the console in `system12` and `system` were compared against the 2x set.
- Every text stood in the same place. The letters were sharp, and shapes that waifu2x had bent, such as `w` and `W`, were right.
- The first version drew the strokes thin and opaque. In a play test they looked too thin and too dark next to the original. With the weight and gain above, the briefing papers and the Pilot Login were compared again with the original game: the strokes carry the same ink, and their darkest pixels are within about 20 levels of the original's.
- The pictures are in `logs/shots/fonts-final/` and `logs/lettering-compare/`. `11-clipped-glyphs-fixed.png` shows the accented capitals that the first version cut at the box edge.

### Menus and loading screens

`tools/menu-pictures.json` lists the flat pictures the tool enlarges. `tools/menus.py` reads it.

| Pictures | Size | Way |
| --- | --- | --- |
| Main menu (12 tiles) and its 13 highlights | 4x | Real-ESRGAN, on the whole screen |
| 25 loading screens (12 tiles each) | 4x | Real-ESRGAN, on the whole screen |
| Mission selection: 16 tiles, the three other book tiles, the paper, 10 mission rows, 9 highlights | 4x | Real-ESRGAN, on the whole screen |
| Mission briefing: 6 tiles, the paper, 6 highlights, 37 photos of rooms, units and pickups | 4x | Real-ESRGAN, on the whole screen |
| Credits: the 12 tiles of the frame | 4x | Real-ESRGAN, on the whole screen |
| Credits: the 6 pictures of the scrolling text | 2x | waifu2x |
| Window frames, buttons, sliders, the mouse arrow | 2x | waifu2x |
| Medals, plane and weapon pictures, the icons of the model window, the maps of the Mission Info window, pilot photos | 4x | Real-ESRGAN |
| The HUD: gauges, plane shapes, weapon signs, digits, sights, radar frame (48 pictures) | 4x | Real-ESRGAN, then the labels are redrawn |

A screen is put together from its tiles into one 640x480 picture first.
That picture is enlarged, pulled back to the original and checked like a texture, then cut into the tiles again.
So no edge shows where two tiles meet.

A highlight is the piece the game draws over a screen under the mouse.
For each one the whole screen is enlarged once more with the highlight laid in, and only the highlight is cut out.
Its edges then continue into the screen around it.
The same is done for every piece the game lays over a screen: the rows of the mission list, the paper, and the photo on the briefing.

Where each piece lies is in the JSON file. The places come from two sources.
- `./dogfighter --diag-draws` writes the place of each picture's first draw to the log. The tiles of all five screens, four highlights, two mission rows and one briefing photo were read from that.
- The other highlights, rows and paper tiles were laid over the composed screen at every place, and the best fit was taken. Where both sources had a piece, they agreed.
- All 37 briefing photos are taken to lie where the one that was logged lies, at 350,65. A wrong place would not move a picture in the game. It would only make its edge fit the paper less well.

- Each picture gets its marker, `.2x` or `.4x`.
- The manifest lists each with its way, its scores, `marked` (2 or 4) and, for a piece of a screen, `screen`.
- Without the upscalers the macOS filter makes them. They then have the pixels and no new detail.
- Pilot photos are `.tga` files. The tool reads and writes them itself.
- `--no-menus` leaves all of them out and removes them from a set.
- `--menus-only` adds them to a complete set and keeps that set's settings and key, as `--lettering-only` does. `./setup.sh` runs it on a complete set.
- An override in `texture-overrides/` works for these too, for a `.gti` and for a `.tga` photo. It must have the enlarged size.
- A change in the JSON file makes the pictures it touches again on the next run.

Left out:
- The Paint Room's pieces, the stickers and `Graphics\Misc`: the game reads their pixels one by one.
- The House Editor: nobody has checked how it draws.
- The icons of the mission success screen and the two other credits frames (`creds_al`, `creds_ax`): no test run reached them.
- The photos and the noise behind the credits. The photos show the people who made the game, and an upscaler repaints faces.

One run on an M4 Max made the 640 pictures in about six and a half minutes. Each state of a screen costs one more pass over the whole screen, and the two mission screens have 67 states.
Every run makes eight pictures and one screen a second time and compares the bytes. In the last run all 20 files were the same, the 12 tiles of the credits frame among them.
The set grows from about 200 MB to about 980 MB. The 25 loading screens take most of that.

In the game, with full resolution: the login window, the Pilot Roster, the main menu with two highlights, the mission selection, the briefing, the model window, the credits, a loading screen, a flight and the map in the Mission Info window.
In the flight the gauges, the digits, the armour ring and the radar stood where they stand with the game's own files.
Every screen matched the one with the game's own files in layout. Info, Close, Login and Campaign opened on a click.
The upscaler repaints faces on the pilot photos a little. That is a matter of taste.

### Markers for flat pictures with more pixels

An empty file `<name>.2x` or `<name>.4x` next to a picture in `hd-textures/cache/` says it has 2 or 4 times the pixels a side.
The helper then keeps the picture at its old size and place.

- The game draws a flat picture as large as the size stored for it. After loading, the helper divides that stored size by 2 or 4.
- Window frames, buttons and sliders are laid out with the picture's real pixel count, from `GtImage::GetWidth` and `GetHeight` in `Cc.dll`. For a marked picture the helper answers those calls from `AfEngine.dll` and `Dogfighter.exe` with the stored size. The Direct3D driver keeps the real one.
- When the game shrinks a picture to its size limit, the stored size does not change, so the picture is still drawn right.
- The helper checks the bytes of the loader and of both size functions first. On another game build it writes one line to the log and leaves everything alone; marked pictures would then be drawn too large.
- Pictures the game reads pixel by pixel must not get a marker: the Paint Room's pieces, the stickers and `Graphics\Misc`.

Test runs used plain 2x and 4x copies of the window frames, the medals, a pilot photo, the cursor, the HUD and the main menu.
Each screen matched the one with the game's own files, with the limit at 1024 and at 512.
Info, Login and Campaign opened on a click.

### Redrawn labels

An upscaler cannot read. On a label a few pixels high it draws shapes that are almost letters.
So for 26 textures and 7 HUD pictures the tool sets the words again with a font, after the set is made.

- `tools/lettering.json` lists each texture, its words, the boxes and the fitted numbers.
- `tools/lettering.py` draws them with the helper `tools/lettering-draw.c`, which uses CoreText. No Python packages are needed.
- In each box the old letters are painted out from the pixels around them. Then the words are laid over in the font.
- Size, stretch, weight, position and the shift of each letter were fitted once to the original pixels. Each candidate was drawn, shrunk to the original size and compared with the original.
- Every run draws the same bytes from those numbers. Two runs in a row changed nothing.
- Nothing is traced and no AI draws letters. Only words that are clear in the original are set.

| Textures | Words | Font |
| --- | --- | --- |
| `firecr1`-`3`, `rocket123`, `abomb` (11 files) | PUFF, BANG, BOOM, ATOM | Stardos Stencil Bold |
| `glue1` | HUMBROL, POLY CEMENT, the three warning lines | Alfa Slab One, Arial Bold |
| `humbrol1` | HUMBROL, Enamel | Alfa Slab One, Helvetica |
| `books01` | ADVENTURE SERIES VOL 1 to 4, and 1 to 10 | Bebas Neue, Arial Bold |
| `books03` | 1 2 3 | Arial Bold |
| `fridge01` | COOLMAN | Arial Black |
| `MEDAL` | CHAMPIONS 1942 | Menlo Bold |
| `particleobj` (2 files) | LASER POINT | Arial Bold |
| `AirConTower1` (4 files), `AirConTowerD` (2 files) | 23 | Helvetica Bold |
| HUD: `clock1`, `clock2`, `weapon1`, `weapon2`, `techstar`, `techcross`, `armour` | FUEL, SPEED, PRIMARY, SECONDARY, TECH, ARMOR | Arial Black |
| `Mailbox` | U.S. MAIL | none: that box comes from the macOS filter, because the upscaler turned MAIL into other shapes |

The small bottom line of `humbrol1`, the two blueprints and about 90 other textures with writing are left as made. Their words are not certain, or the made texture already reads well.

Fonts:
- Stardos Stencil, Alfa Slab One and Bebas Neue are under the SIL Open Font License 1.1. They come from the Google Fonts repository at commit `06bfe0d62a98375cb09c942fa18e68bd32cff057`.
- `--fetch-tools` or `--fetch-fonts` downloads them to `upscale-tools/fonts/`, each checked against a pinned SHA-256 checksum, with its licence `OFL.txt` beside it.
- The HUD labels are five pixels high in the game's files. All six are set at one size, 6.6 pixels, which the fits of the single labels agreed on.
- Arial Bold, Arial Black, Helvetica and Menlo come with macOS. They are only read to draw pixels on your Mac and are not part of the repository.
- A missing font leaves its textures as made, and the run says so in one line.
- A macOS font with another checksum than listed is drawn anyway. The checks below catch letters that moved.

Checks, after drawing:
- No pixel outside the boxes changes, alpha included.
- The edges of a tiling texture do not change.
- Each box, shrunk to the original size, must match the original at 10 dB or more. The drawn boxes score 11 to 34 dB. The same words moved by 2 pixels, or drawn 20% smaller, score 6 to 9 dB.
- A texture that fails keeps its made version.

The manifest lists such a texture with the way `lettering`.
The made texture's record is under `generated`, and the fonts' checksums and the scores under `lettering`.
The made texture waits in `hd-textures/replaced/`.
- `--no-lettering` puts the made textures back. The next run without it draws them again.
- A file in `texture-overrides/` wins over the lettering.
- `--lettering-only` redraws just the labels and the font letters of a complete set, with the settings stored in its manifest. Nothing else is made again, and the set keeps its key, so a set made with `--scale 4` or `--upscaler vimage` stays that set.
- `./setup.sh` runs `--fetch-fonts` and `--lettering-only` on a complete set. A font that cannot be fetched leaves only its labels as made.
- It works at 2x and at 4x. On scratch sets made with `--scale 4`, with `--upscaler vimage` and with the defaults, `--lettering-only` drew all 26 and changed no other file; a later run with each set's own settings found it complete.

### Hand lettering on the menus

The upscaler draws shapes of its own into small hand lettering. It turned the G of CAMPAIGN into a spiral and gave the stencil headings of the briefing papers light edges and stripes.
So `tools/signs.py` draws those letters again over the made 4x pictures, from the game's own pixels alone. No AI and no font is used.

| Screen | Boxes |
| --- | --- |
| Main menu | the eight signs: PILOT ROSTER, HOUSE EDITOR, CAMPAIGN, MULTI-PLAYER, OPTIONS, LOG OUT, CREDITS, PAINT ROOM, each also in its highlight |
| Mission selection | QUICK BRIEF, the BACK and OK signs and their highlights |
| Mission briefing | MISSION BRIEFING, PRIMARY OBJECTIVES, SECONDARY OBJECTIVES, MODEL, the BACK, CHANGE MODEL and OK signs and their highlights |

How a box is drawn, by `tools/signs-draw.py`:
- The box is cut from the game's pictures and from the made pictures, laid together as the game lays them.
- The sheet is the largest patch of paper-coloured pixels and everything inside its convex hull. Wood, cork and desk round a sign stay as made.
- Each game pixel is split into paper, the lettering's ink and other inks such as a sign's black frame. The ink colour is taken from the box itself, so a highlight gets its own lighter ink.
- The lettering's share is enlarged 4x the smooth way and cut at the level that keeps its amount of ink, with a soft edge. So the strokes keep the original's shapes and weight.
- Where the made picture shows the lettering's ink near the game's letters, it gets the game's paper, enlarged smoothly. Then the new letters are laid over.
- The result goes back only into the pictures of that state: the screen's own tiles, or the highlight.
- Other states lay pictures over parts of some boxes: the HOUSE EDITOR and OPTIONS highlights over MULTI-PLAYER, and the paper of both mission screens over OK, the objectives headings, MODEL, BACK and CHANGE MODEL. Where such a picture shows exactly the screen's own pixels in the box, it holds a copy of the sign and gets the box drawn for the screen. So the sign looks the same in every state.
- A state whose pictures show the sign with other pixels must be listed and is drawn on its own: the highlights, and the briefing paper under BACK, whose top edge differs.
- The other states over a box show something else there, such as the arrow buttons or the paper without its heading, and stay as made.

What it needs and checks:
- `tools/signs.json` holds the boxes, a rough ink colour per box, the states and the numbers of the drawing.
- It runs in the desk's Python environment, `upscale-tools/desk/venv`. Without it the signs stay as made.
- The game's pixels in each box must match a checksum per state. Another language's signs stay as made.
- A box stays as made when its letters touch its edge, it holds too little lettering, or it scores under 18 dB against the game's pixels after shrinking. The drawn boxes score 24 to 37 dB.
- The desk, the paintings and the stamps are drawn over these pictures. Seven desk pieces carry new signs too and are listed with the way `desk` and a `sign` note.

- The manifest lists a changed picture with the way `sign` and the boxes drawn in it.
- `--no-signs` puts the made pictures back. `--menus-only` and `--lettering-only` draw them.
- Two runs gave the same bytes. Drawing the 36 boxes into 41 pictures takes a few seconds.

In the game, with full resolution, the main menu, the mission selection and the briefing were compared with the original game. The letters had the original's shapes, CAMPAIGN's G among them, and the headings had no light edges or stripes.
Left as made: the stencil words in the mission books (SELECT AIRFORCE, ALLIES, AXIS, SELECT MISSION). The books are laid out differently in each state, so their boxes would differ per state.

### The desk on the main menu

The upscaler cannot tell what the few pixels of a kit box or a paint tin show. On the main menu's desk it painted smears.
So the tool draws those boxes and tins again over the made 4x pictures, from photos of real ones.

- The boxes are 1990s Airfix boxes: the Fiat G50-bis lid, the Spitfire Mk IX lid and end, and the long sides of the Me262, Fw190D and Bf109G-6.
- The game's pictures are too small to tell which kits three box sides show: the second box on the right and two boxes on the left. They are drawn as a P-51D Mustang, an A6M2 Zero and a Typhoon, kits of the right colours. `tools/desk.json` marks them `invented`.
- Sides without a photo of their own are laid out on the Typhoon's side and end, with their own title, kit number, a few words and a strip of their lid painting.
- The nine tins are drawn from the Humbrol Super Enamel tin on Humbrol's 1997 "Colour System" binder. Each lid keeps the game's paint colour.
- The game's tins are 2 to 28% taller than a real one. The label keeps Humbrol's own proportions and starts under the rim; the height left over shows bare tin below it.
- The Airfix badge above the desk stays as made.
- The highlights of Credits, Options and Paint Room lie over boxes or tins. Each is drawn again with the highlight laid in, and cut out with its own edge.

How a box face is drawn:
- It is straightened out of the photo and warped onto the face's four corners in the menu.
- Its colours are mapped onto the made picture's pixels there. The paper becomes the game's paper, the darks move half way to the game's darks, and the game's light across the face replaces the photo's.
- The edges are softened, so the made picture's own edge pixels stay.

What it needs:
- `tools/desk.json` holds every number: the corners, the crops, the words, the tins, and the photos with their URL and SHA-256 checksum.
- `--fetch-tools` or `--fetch-desk` downloads the 12 photos, about 5 MB, to `upscale-tools/desk/references/`, each checked against its checksum. Most are pictures of eBay listings, which can disappear.
- It also makes a Python environment in `upscale-tools/desk/venv` with numpy and Pillow, at the versions of `tools/desk-requirements.txt`. `tools/desk-draw.py` runs in it.
- The titles use Oswald, from the Google Fonts repository at the same commit as the label fonts, under the SIL Open Font License 1.1. The small words use Arial, which comes with macOS.
- Nothing is drawn by AI. The photos never enter the repository; the drawn pictures stay in `hd-textures/`.

Checks:
- The numbers were fitted to the game's own pixels under the boxes and tins. The tool checks those pixels against a checksum. All four languages of the disc have the same pixels there.
- Each drawn piece, shrunk to the original size, must match the original at 15 dB or more. The drawn pieces score 20 to 32 dB. This only catches a drawing gone wrong as a whole.
- A missing photo, font or package, or a failed check, leaves the desk as made, and the run says why in one line.

The manifest lists such a piece with the way `desk`.
The made picture's record is under `generated`, and the photos' checksums, the package versions and the scores under `desk`.
The made picture waits in `hd-textures/replaced/`.
- 11 pieces change: six main menu tiles and the five highlights.
- `--no-desk` puts the made pictures back. The next run without it draws them again.
- `--menus-only` and `--lettering-only` draw the desk too. `./setup.sh` runs `--fetch-desk` and `--lettering-only` on a complete set.
- A later run with the same photos, numbers, packages and made pictures keeps the pieces and draws nothing.
- Drawing takes about 4 seconds on an M4 Max. Two runs gave the same bytes.

### The plane paintings

Twelve planes have an Airfix box painting in the game: on their loading screen, inside the television, and in the model window.
The game's copies are a few hundred pixels wide, and the upscaler repainted rivets, letters and faces.
So the tool draws each painting again over the made 4x pictures, from a picture of the real box art.

| Plane | Box art |
| --- | --- |
| Bf109G-6 | photo of the 1990s box 01072 |
| P-61 Black Widow | Airfix's render of A04006V, and the same painting without words, both from uk.airfix.com |
| Dauntless | Airfix's render of A02022V |
| Fiat G.50 | Airfix's render of A01046V, and the wide banner of its page |
| Fw190D | photo of the box A01064 without a swastika on the tail, as in the game |
| Hellcat | two photos of the 1968 box 253 |
| Hurricane Mk1 | flat scan of the "Aircraft of the Aces" box 02082, and a photo of the later box |
| P-51D Mustang | photo of the 1990s box 02098 |
| Spitfire Mk IX | photos of the box 02081 and of its "Aircraft of the Aces" box |
| Ju87B-2 Stuka | photo of the 1:24 box 18002 |
| Typhoon | photo of the box 01027 |
| Zero | two photos of the box 01028 |

How a painting is drawn:
- The box art is laid onto the game's picture with a fitted homography and a small grid of bends on top. The fit was made once from matched points and lies within about half a pixel of the game's picture.
- The colours are fitted to the game's picture in small windows. The game's colours, its light and the dark edge of the television stay; the detail comes from the box art.
- Where the box shows a title, a logo, a frame or other words, the made picture stays. The game's painting does not have them.
- Where the box art does not reach, as at the top of most loading screens, the made picture stays too.
- The frame of the television and of the model window picture stays as made.

What it needs:
- `tools/paintings.json` holds every number: the corners, the bends, the printed area of each picture, the boxes where the made picture stays, and each picture with its URL and SHA-256 checksum.
- `--fetch-tools` or `--fetch-paintings` downloads the 18 pictures, about 14 MB, to `upscale-tools/paintings/references/`, each checked against its checksum. Five come from Airfix's own image host, one from vintage-airfix.com, the rest are eBay listings, which can disappear.
- `tools/paintings-draw.py` runs in the desk's Python environment, `upscale-tools/desk/venv`, which `--fetch-paintings` sets up too.
- Nothing is drawn by AI. The box art never enters the repository; the drawn pictures stay in `hd-textures/`.

Checks:
- The numbers were fitted to the game's own pixels of each picture. The tool checks those pixels against a checksum. All four languages of the disc have the same pixels there.
- Each drawn painting, shrunk to the original size, must match the original at 15 dB or more inside its area. The drawn ones score 22 to 28 dB, the made ones 54 to 71. The box art has its own detail where the game's copy is blurred, so the score only catches a drawing gone wrong as a whole.
- A missing picture or package, or a failed check, leaves that painting as made, and the run says why in one line.

The manifest lists such a piece with the way `painting`.
The made picture's record is under `generated`, and the target, the pictures' checksums, the package versions and the scores under `painting`.
The made picture waits in `hd-textures/replaced/`.
- 57 pieces change: 45 tiles of 12 loading screens and the 12 plane pictures of the model window.
- `--no-paintings` puts the made pictures back. The next run without it draws them again.
- `--menus-only` and `--lettering-only` draw the paintings too. `./setup.sh` runs `--fetch-paintings` and `--lettering-only` on a complete set.
- A later run with the same pictures, numbers, packages and made pictures keeps the pieces and draws nothing.
- Drawing all 24 takes about 20 seconds on one core. Two runs gave the same bytes.

### The stamps in the mission book

The Axis and US Airforce pages of the mission book carry a round ink stamp, about 60 pixels wide.
The upscaler turned it to mush. So the tool draws each stamp again over the made 4x pictures, as sharp ink on the page.

| Page | Stamp |
| --- | --- |
| Axis, and its highlighted page | the Reichsadler on a wreathed swastika, as in the game |
| US Airforce | the "Hap Arnold" winged star of the US Army Air Forces |

- The game's US stamp is the seal of the Department of the Air Force, from 1947. That is too late for the war, so the stamp shows the wartime winged star instead.
- The words in the game's rings cannot be read. The rings are drawn plain, without words.
- The Allies page's RAF eagle and crown stay as made. Drawn again from the game's 66 by 20 pixels, it looked blotchier than the made picture. No public-domain drawing of that badge in the game's pose was found.

How a stamp is drawn:
- The old ink is taken off: near the stamp, the paper is drawn again from the game's own paper, without its ink, with the made paper's grain.
- That paper follows the page's shadow toward the spine. Each pixel's paper is a plane fitted to the paper around it.
- The new paper fades into the made picture before the edges of the drawn box, so no line shows there.
- The rings are circles. The emblems are drawn from their SVG files, each colour standing for full ink or bare paper.
- Four corners lay the stamp onto the page, so it leans with the book. They were fitted once to the game's rings.
- The ink gets rough edges, lighter patches and a few bare specks, like a rubber stamp. The noise has a fixed seed.

What it needs:
- `tools/stamps.json` holds every number: the corners, the rings, where each emblem goes, the ink colours, and the two SVG files with their URL and SHA-256 checksum.
- `--fetch-tools` or `--fetch-stamps` downloads the two SVG files, about 40 KB, from Wikimedia Commons to `upscale-tools/stamps/references/`. Both are in the public domain.
- `tools/stamps-draw.py` runs in the desk's Python environment, `upscale-tools/desk/venv`, which `--fetch-stamps` sets up too.
- Nothing is drawn by AI. The emblems never enter the repository.

Checks:
- The numbers were fitted to the game's own pixels of each picture. The tool checks those pixels against a list of checksums. The languages differ there by the highlight's brightness and one pixel, so the list holds one checksum for each.
- Each drawn stamp, shrunk to the original size, must match the original at 14 dB or more. The drawn ones score 17 to 18 dB. The ink is sharper than the game's blurred copy, and the US emblem is another drawing, so the score only catches a drawing gone wrong as a whole.
- Near each edge of the drawn box, the new paper may differ from the made picture by at most 3 levels of 255 in mean brightness. The drawn ones differ by under 2.
- A missing emblem or package, or a failed check, leaves that stamp as made, and the run says why in one line.

The manifest lists such a piece with the way `stamp`.
The made picture's record is under `generated`, and the target, the emblems' checksums, the package versions and the scores under `stamp`.
The made picture waits in `hd-textures/replaced/`.
- 3 pieces change: `mission_sel_02`, `book_hilight_axis` and `mission_sel_18`.
- `--no-stamps` puts the made pictures back. The next run without it draws them again.
- `--menus-only` and `--lettering-only` draw the stamps too. `./setup.sh` runs `--fetch-stamps` and `--lettering-only` on a complete set.
- A later run with the same emblems, numbers, packages and made pictures keeps the pieces and draws nothing.
- Drawing all three takes under a second. Two runs gave the same bytes.

### Your own textures

Put a `.gti` file in `texture-overrides/`, under the same path as in `hd-textures/cache/`.
The next run of the tool puts it in the set in place of the made texture.

- It must have the size, pixel format and number of mipmap levels of the made texture. Otherwise the tool refuses it and says why.
- It gets no other check.
- The manifest lists it with the way `override`.
- Change the file and the next run takes the new one.
- Remove the file and the next run puts the made texture back.

Use it for a texture the redrawn labels do not cover.
`texture-overrides/` is not part of the repository, because it holds game art.

### How the game finds them

- The game opens `cache\<path>` in its folder before it looks in its packs.
- The launcher links `game/cache` to `hd-textures/cache`.
- A pilot photo of your own in `game/User/Save/Photos` stays in use. The game would open the larger copy in `cache\` first, so the launcher compares each photo there with the game's photo the copy was made from. If one differs, `game/cache` links to `dogfighter-cache` in the Wine prefix's `drive_c` instead. That folder holds links to the whole set, without the copies and markers of those photos. The set itself is not changed.
- When the larger textures are off, it removes any link at `game/cache`, wherever it points, and writes that to the log. A link left behind would let the game load those files without the raised size limit and the letter markers, so letters could come out twice as large.
- If `game/cache` is a real folder, the launcher leaves it alone and keeps the larger textures off.
- The helper changes the 256-pixel limit in the running game's memory. No game file is changed.

`tools/gti.py` turns one texture into a PNG and back, for your own edits.
The file format is described at the top of `tools/gti.py`.
`tools/up.py` lists and unpacks the game's `.up` packs.

## Intro videos

The game plays two videos at start, from `game/Video/`.
- `companies.avi`: the company logos, 43.5 seconds.
- `airfix.avi`: the Airfix intro, 65.5 seconds.
- Both are 640x480 at 15 frames a second, Indeo 5 video with 22 kHz stereo PCM sound.

The texture tool can make them 4x as large (2560x1920) and 60 frames a second.
It is optional and separate from the textures.
The launcher plays them before the game starts (see [How the launcher plays them](#how-the-launcher-plays-them)).

```
python3 tools/upscale-textures.py --fetch-videos
python3 tools/upscale-textures.py --videos
```

`--fetch-videos` first fetches the texture tool's upscalers, as `--fetch-tools` does.
Then it downloads about 9.8 GB to `upscale-tools/video/`.
- A Python environment with the packages of `tools/video-requirements.txt`. It needs Python 3.12 or later.
- SeedVR2's code, the ComfyUI-SeedVR2_VideoUpscaler release v2.5.23 (Apache-2.0).
- The SeedVR2 models: the 3B model as GGUF Q8_0, the 7B "sharp" model as GGUF Q4_K_M and the VAE (Apache-2.0).
- `rife-ncnn-vulkan` 20250112 with the RIFE 4.26 model (MIT).
- ffmpeg comes with the Python package `imageio-ffmpeg`.

What is checked differs per kind of file.
- SeedVR2's code, its models and RIFE have their URL and SHA-256 in `tools/videos.json`.
- `upscayl-bin` and the Real-ESRGAN model have theirs in `tools/upscale-textures.py`.
- A download that does not match is refused, and the tool stops.
- Before each run the models, RIFE and `upscayl-bin` are checked again. One that does not match stops the run.
- SeedVR2's unpacked code is not checked again. Only a note of the archive it came from is.
- The Python packages are pinned by version only (`==`), without a checksum. That includes `imageio-ffmpeg` and the ffmpeg inside it.
- The manifest records ffmpeg's SHA-256, but nothing checks it.

`tools/videos.json` gives each video a level.
- Level 1, the company logos: Real-ESRGAN on each frame, by the texture tool's `upscayl-bin`, then the textures' pull-back in `tools/texture-refine.c`. It adds sharpness, not detail.
  Each frame, shrunk again by averaging each 4x4 block and rounding, is the game's frame. In a test on six frames every pixel matched, with a sharpened Lanczos picture in place of Real-ESRGAN.
- Level 2, the Airfix intro: SeedVR2 3B. It redraws whole shots, 9 frames at a time, so the new detail does not flicker. The look is a restored copy of the same film.
- Level 3, a 10-second sample of the Airfix intro: SeedVR2 7B "sharp", the most the model can add.

Then for every video:
- Cuts between shots are found on small copies of the frames.
- RIFE makes three frames between each two, 15 to 60 a second. The frames of the game stay unchanged.
- A video's `no_interpolate` ranges get no RIFE frames. Each frame there is shown four times, as the game shows it.
  In the Paradox logo of `companies.avi`, frames 234 to 408, every third frame nearly repeats the one before. RIFE then moved the swarm of stars in stops and jumps. Its frames between also blurred the stars.
- At a cut, RIFE would blend two shots. So the last frame of a shot is held until the next shot starts.
- Every frame of the game keeps its own time, so sound and picture stay in sync.
- x265 writes 10-bit HEVC. The `.mov` holds the game's sound unchanged.

The videos go to `hd-videos/`, with `manifest.json`: checksums, settings, model checksums, run time, and the lowest free memory, worst pressure and most swap seen.
- A video whose source, settings and models did not change is not made again.
- A run that stops goes on where it stopped. The work files are in `hd-videos/.work/`.
- `--video-only NAME` makes one video. `--video-clip START,SECONDS` makes only that part, to `hd-videos/clips/`. `--video-level N` tries another level, also to `clips/`.
- SeedVR2 gets a long shot in chunks of at most 29 frames. Its memory grows with the chunk, and 52 frames needed more than 22 GB. Each chunk also sees 4 frames of its neighbours, and the 4 frames where two chunks meet are faded from one to the other.
- The fade averaged two sets of made detail, so those frames were up to 30% softer. A repair step after SeedVR2 gives them the fine detail of the nearest frame of the chunk with the larger share, moved along the motion found on the game's frames. The coarse picture stays the fade's. With `between`, RIFE's frames around each border get the same repair after RIFE, since RIFE would otherwise mix two sets of detail again.
- SeedVR2 drew dark smudges into the flat sky of the Airfix intro. In a video's `smooth_flat` frame ranges, at the video's own level only, every pixel the game's frame shows as flat comes from a smooth upscale of that frame. Text and edges keep SeedVR2's picture.
- The repair works on the kept SeedVR2 frames, in `fixed/` of the work folder. Changing its settings (`repair` in `tools/videos.json`) remakes the frames between and the video, not the SeedVR2 frames.
- `tools/video-check.py OLD.mov NEW.mov` measures both faults in two made videos: the sky's darkest spots against the smooth upscale, and how much softer each chunk border is than its neighbours.
- SeedVR2 keeps freed graphics memory for reuse. Above 6 GB it gives some back, and 19 GB is its hard limit (26 GB for level 3). Without these limits it reached 29 GB. Changing them does not make the video again.
- The limits alone did not hold. So SeedVR2 runs through `tools/seedvr2-run.py`. It empties that kept memory before each phase and after each batch. It changes SeedVR2's code in memory only, so the unpacked files keep their checksum.
- A stopped run of level 2 or 3 goes on from the chunk where it stopped. SeedVR2's own output goes to `seedvr2.log` in the work folder.
- While a tool runs, `videos.log` gets a line each minute with its memory (`tool=`), graphics memory included.

The run follows macOS's memory pressure, the green, yellow and red of Activity Monitor.
So compressed memory and idle apps swapped to the SSD do not stop it.
- At yellow or red no new shot, chunk or batch of frames starts. The tool checks again every 30 seconds. After 10 minutes the run stops.
- Red for 20 seconds in a row while a tool runs stops it, and the run ends. Between tools, red only makes the run wait.
- Swap growing by more than 16 GB during the run ends it at once, so the SSD does not fill. Swap in use before the run does not count.
- When the pressure cannot be read, the old rule holds. Nothing starts under 15% free memory, and the run ends under 8%. `videos.log` says so once.
- Each line of `videos.log` shows `free=`, `used=`, `pressure=` and `swap=`.
- The limits are under `"memory"` in `tools/videos.json`.

SeedVR2 and `upscayl-bin` need the Mac's graphics card. Without it, levels 1 to 3 are left out. RIFE alone falls back to the processor, much slower.

### How the launcher plays them

The game plays `companies.avi`, then `airfix.avi`.
The launcher plays `hd-videos/companies.mov` and `hd-videos/airfix.mov` before it starts Wine.
- It plays them with `build/intro-player`, a small AVFoundation program. macOS decodes the HEVC; nothing is downloaded.
- The window is as large as the game's first window and opens at the top left of the main screen, where the game's opens. The game always runs in a window, so the videos do too.
- Esc, a click or any key skips one video. Closing the window skips the rest.
- `--mute` plays them without sound.
- A `--diag` run leaves them out, so test runs are as before.

The game must then leave out its own copies.
Its file has no setting or switch for that.
It plays the names in a list in its data, in order, until an empty entry.
- The launcher sets `DOGFIGHTER_SKIP_INTROS` to the number of videos it showed.
- The helper takes that many names off the front of the list in the game's memory, before the game runs.
- With both shown, the list holds one name of a file that does not exist. The game always opens the first entry, and a file it cannot open ends its intro, as when a video ends.
- Only a build with exactly this list is touched. The launcher checks the same bytes in `game/Dogfighter.exe` before it plays anything, so an unknown build plays only its own intros.
- No file is changed. The `.avi` files stay where they are. A start without the variable plays the game's own intros.

So only an unbroken run from the first video can be replaced.
- `companies.mov` alone: it plays, then the game plays its own `airfix.avi`.
- `airfix.mov` alone: the game plays both of its own, and the launcher says why.
- A video that does not play: the player stops there, and the game plays its own from that video on. The launcher says why in one line.

The player's exit status is the number of videos shown or skipped. A higher status, such as a crash, counts as none shown.
If Mach9 does not start and the launcher starts the Rosetta Wine, the videos are not played again.
`build/intro-player` and the helper must be newer than their sources; if not, the game plays its own and the launcher says to run `./setup.sh`.

`--no-hd-videos` lets the game play its own intros. `--original` does too, unless `--hd-videos` is given.

The game leaving out its own copies was run with `--diag-intros-shown`: on Mach9 it went straight to the main menu.
Nobody has run the player window, its decoding or the skipping yet.

## CD music

The game plays its music from the CD's audio tracks.
Setup rips them to `music/Track02.ogg` to `Track11.ogg`.
A replacement `winmm.dll` ([ogg-winmm](https://github.com/dippy-dipper/ogg-winmm)) in `game/` plays them.

The in-game music slider works.
To override it, set a number from 0 to 99 in `game/winmm.ini`; 100 means "use the slider".

`--mute` starts the game without sound: no videos, music or effects. Other apps keep their sound, and the next start without it has sound again.

## Saves

Pilots, levels, photos and stickers live in `game/User`.
Screenshots (Fn + F12) go to `game/ScreenShots`, as `Img00000.tga` and up, in the game's own resolution.
- The game takes one only for a key that `game/user.ini` binds to `screenshot`. It writes that file again at every quit.
- The first play test's file had lost its `bind F12 "screenshot"` line, so F12 did nothing.
- At each start the launcher adds that line when no key is bound to `screenshot` and F12 is free. It says so in one line.
- Keys work in a flight, not in the menus. That is the game's own rule.

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
- The helper and the controller lister `build/joylist.exe` are built, and the helper is newer than its source.
- When `hd-videos/` holds an intro video: the intro player is built, `game/Dogfighter.exe` is the build whose intros the helper can leave out, and the first frame of each video decodes.
- The save folders in `game/User` exist.

After the checks it lists the controllers the game can see, or says `no controller found`.
It also says when Joystick is off in the game's Options. Neither counts as a failed check.

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
The keys in an existing `game/user.ini` are never changed, with one exception: F12 gets `screenshot` back when no key has it (see Saves).

### Controllers

Nobody has tried a real controller yet. This section says what was read and what was run.

How a controller reaches the game, in both Wine builds:
- Wine's driver `winebus.sys` reads controllers in two ways at once: through the SDL library, and through macOS IOHID (the raw reports of the device).
- Each controller is kept from one of the two. Wine's rule picks SDL for gamepads and raw reports for a short list of devices.
- A gamepad that SDL knows becomes a standard pad. `winexinput.sys` then shows it to DirectInput as Windows shows an Xbox pad.
- That pad has X and Y (left stick), Rx and Ry (right stick), one Z axis for both triggers, a hat and 10 buttons.
- Any other joystick from SDL keeps its own axes, numbered in order: X, Y, Z, Rx, Ry, Rz.
- The game asks DirectInput for joysticks and gets them.

The Rosetta Wine loads SDL 2.32 from `wine/lib`. Mach9 loads SDL 3.4 from `wine-mach9/wine/lib/external`, through the sdl2-compat layer.
Read in `dlls/winebus.sys` and `dlls/winexinput.sys` of Wine 11.0 and of Mach9's Wine at commit `501796b0ed`.

What the launcher sets:
- `dogfighter.reg` adds `Hidraw`=0 under `HKLM\System\CurrentControlSet\Services\winebus\Devices\054C` and `...\057E`. Those are Sony and Nintendo.
- Without it Wine reads a DualShock 4 or DualSense raw. The game's throttle axis Z is then the right stick, left and right.
- With it they go through SDL and behave like an Xbox pad.
- The launcher exports `SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS=1`. Wine reads controllers in `winedevice.exe`, which is never the app in front. Mach9's SDL can read a pad through Apple's GameController, and that only serves the app in front unless this is set.
- Wine's own settings stay at their defaults: `Enable SDL` 1, `Map Controllers` 1, `DisableHidraw` 0.
- At each start it writes `sets option_joystick "true"` to `game/user.ini` when a controller is connected and the option is not on yet. It never writes `false`. `--no-auto-joystick` turns this off.
- It finds a controller with `hidutil list`, matching HID devices that have Generic Desktop usage 4, 5 or 8: joystick, gamepad, multi-axis controller. These are the usages SDL's macOS joystick code matches. The check takes about 10 ms.
- An Xbox controller on a USB cable may not show as a HID device. Then the option stays as it was.

How the game reads a joystick, from the code of `Dogfighter.exe`:
- It only reads one when `option_joystick` in `game/user.ini` is true. Options in the game sets that.
- At start it takes the first joystick DirectInput lists (`EnumDevices`, `DIDEVTYPE_JOYSTICK`, attached only). So connect before starting. It does that whatever the option says.
- Each time it polls, it first checks that it has a joystick, then reads the option. So the option works at once when changed in the game.
- With no joystick found at start it never polls one. The option being on then does nothing.
- It asks for a range of 0 to 10000 on X, Y and Z. If there is no Z axis it takes the first slider.
- X is bank and Y is pitch. Moves under 8% of the way count as the middle.
- Z or the slider is the throttle, as a position: the lowest value is full throttle.
- With the pad from `winexinput.sys`, Z rests in the middle. The right trigger lowers it and the left trigger raises it.
- The game sends a throttle only when the axis has moved. So the keys `d` and `c` keep working until a trigger is touched.
- It reads 32 buttons as `jbutton0` to `jbutton31`. A `bind jbuttonN "action"` line in `game/user.ini` sets one.
- It reads Rx, Ry and Rz but does nothing with them. It does not read the hat.

`./dogfighter --doctor` runs `build/joylist.exe` in Wine. It asks DirectInput the way the game does and prints each joystick with its axes and buttons.
Wine adds a controller a moment after its first program starts. So the tool asks again for up to five seconds before it says `no controller found`.

What was run, on an M4 Max with no controller connected:
- Both builds start the SDL and the IOHID reader and read the two `Hidraw` settings. One start of each build with `--debug=+hid` showed it: the log has "main loop started" for SDL and for IOHID, and "disabling hidraw" for `054c` and `057e`.
- `--doctor` prints `no controller found` on both builds.
- `hidutil` finds no controller either, so the launcher leaves `option_joystick` as it is.
- Keyboard and mouse still reach the game in a flight on both builds. An F12 press and a click bound to `screenshot` each made a screenshot.

Not done for controllers:
- macOS has no way to make a pretend controller without installing a driver. So no input from a controller was ever seen.
- A joystick without force feedback goes through SDL on both builds. If its throttle is not its third axis, the game reads the wrong one. Setting `Hidraw`=1 under `...\winebus\Devices\VVVV/PPPP` (its vendor and product id, in hex) makes Wine read it raw.
- The launcher does not turn off the macOS shortcut on the Home, PS or Xbox button. That is a setting of the whole Mac.

## Troubleshooting

- **Logs.** Each start writes `logs/run-<date>-<time>.log`. The music player's log is next to it, ending in `-music.log`.
- **Lines with `err:` in the log.** Wine's messages go to the log only, never to Terminal. Two kinds are in every log on Mach9 and are harmless. The log ends with a note on each.
  - `err:d3d:wined3d_check_gl_call ... GL_INVALID_FRAMEBUFFER_OPERATION (0x506) from glClear`, 10 to 20 times. The game makes a Direct3D device ten times while it starts. For each one Wine clears the new window once (`wined3d_context_gl_init`, only for a new drawable). The game's window is not on the screen yet, so OpenGL leaves the clear out. Each line comes once or twice from a new thread, before the first picture, and never again.
  - `err:ntoskrnl:ZwLoadDriver failed to create driver ... winebth`. Wine's Bluetooth driver does not load on a Mac. The game does not use it. Controllers come in through `winebus.sys`.
- **The helper is missing.** If the launcher says `focusfix.exe` or `focushook.dll` is missing, run `./setup.sh` again.
- **Testing without the helper.** `--no-focusfix` runs the game in a plain Wine desktop window. The picture is not scaled, the window cannot be resized, the game stops when it loses the focus, and you press OK in the setup dialog yourself. The picture is the original one, as with `--original`: no full resolution, no larger textures. A crashed start is started again, a hung one is not: end it with `./dogfighter --stop`.
- **No music.** Check that `music/` holds ten `.ogg` files and that `game/winmm.dll` exists. Run `./setup.sh` again if not.
- **Disc not found.** `cd/.windows-label` must contain `Dogfighter`, with that exact case. Delete `cd/` and run `./setup.sh` again to rebuild it.

## All launcher options

| Option | What it does |
| --- | --- |
| (none) | Play in a window you can resize, at full resolution, with the larger textures when a complete set is there. |
| `--res=WxH` | Use this game resolution in flight, e.g. `--res=1440x900`. The menus are always 640x480. Without it, the largest size that fits the screen is used. |
| `--full-res` | On by default. Draw the 3D picture with the Retina screen's own pixels and keep the HUD, the menus and the letters at normal size. Keeps it on with `--sharp`, `--retina` or `--original`. |
| `--no-full-res` | Draw in the game's own resolution and scale the picture to the window. |
| `--sharp` | Use Retina pixels: a sharper picture in flight, with a half-size HUD. Turns full resolution off. |
| `--retina` | Draw the window with the Retina screen's own pixels and keep the game's resolution. Turns full resolution off. |
| `--windowed=WxH` | Start with the picture at most this big, in points, e.g. `--windowed=1024x768`. |
| `--wide` | Widen the view angle for a 16:10 or 16:9 picture. |
| `--hd-textures` | On by default. Use the larger textures when a complete set is there. Keeps them on with `--original`. |
| `--no-hd-textures` | Use the game's own textures. |
| `--hd-videos` | On by default. Play the sharper intro videos from `hd-videos/` before the game starts, and let the game leave out its own copies. Keeps them on with `--original`. |
| `--no-hd-videos` | Let the game play its own intro videos. |
| `--smooth=N` | Smooth jagged edges with N samples per pixel: 0, 2 or 4. Without it the launcher uses 4. |
| `--deep-z` | Give the game a 24-bit depth buffer where it asks for 16 bits. |
| `--keep-shape` | On by default. Keep the window in the shape of the game's picture when you resize or zoom it. |
| `--no-keep-shape` | Let the window take any shape. The picture is then stretched to fill it. |
| `--fps=N` | Show at most N pictures a second, from 15 to 1000, e.g. `--fps=60`. |
| `--no-pointer-match` | Leave the speed of the pointer in the menus to the game. |
| `--original` | Leave the picture as the game made it: its settings, its resolution, its textures, its intro videos. |
| `--mute` | Start the game without sound. |
| `--no-auto-joystick` | Do not turn on Joystick in the game's Options when a controller is connected. |
| `--join=ADDRESS` | Put a server in the game's Address book, then start the game. |
| `--setup` | Show the game's setup dialog and wait for OK. |
| `--no-focusfix` | Start without the helper (see Troubleshooting). |
| `--wine=NAME` | Pick the Wine build: `--wine=mach9` or `--wine=stable`, the Rosetta Wine. Any other name uses `wine-NAME/` and `prefix-NAME/`. |
| `--wine-rule=KEY=VALUE` | Only with Mach9: one Mach9 setting for the game. Can be given more than once. |
| `--stop` | End a running game and all its Wine processes. Without `--wine`, on both Wine builds. |
| `--debug=CHANNELS` | Write Wine debug channels to the log, e.g. `--debug=+seh`. |
| `--diag` | Write the game's windows, display mode and cursor state to the log. |
| `--winecfg` | Open Wine's settings for this game instead of playing. |
| `--doctor` | Check the installation and print a fix for each problem. Lists the controllers the game can see. |
| `--backup` | Copy saves and settings to a dated zip file in `backups/`. |
| `--restore[=FILE]` | Put a backup back: the newest one, or `FILE`. |

### Test options

`--diag` has test modes that run with nobody at the screen.
`./dogfighter --help` describes each one.
A run with any `--diag` option does not hold the mouse, so the Mac stays usable, and it is muted.
Test runs follow the same picture defaults as a normal start.

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
| `--diag-keys=SECONDS:SCANCODE[:HOLDSECONDS],...` | Presses keys, as scan codes in hex. `1d38` presses Ctrl+Option. Codes from 80 up are the extended keys, such as `c8` Up and `d0` Down. With HOLDSECONDS the key stays down that long. Keys whose times overlap are down together. Both times can have decimals. |
| `--diag-mouse=SECONDS:DX:DY[:c\|:o],...` | Moves the mouse, and with `:c` clicks. |
| `--diag-console=SECONDS:COMMAND` | Runs a game console command, with `+` for each space and `++` for a `+` itself. `40:++thrustinc` starts the game's held action `+thrustinc` as a key press does, and `45:-thrustinc` ends it. The game's console does not know these names, so the helper runs `thrustinc 1` and `thrustinc 0`, as the game does for a bound key. Of three `+` in a row the first is the space. A command with a real space in it is taken as written, and every `+` in it is a `+` itself: `--diag-console='40:bind x +fire'`. SECONDS can have decimals. Letters, digits, spaces and `_ . + -` are allowed. A command that is due during the game's intro videos waits for the main menu. On Mach9 a mission started during them ends the game with exit code -1. `pointer` is not a game command: the helper writes to the log where the game's menu pointer is and what it did to the mouse moves. `fullshot` is not one either: with full resolution, the helper saves the full-size picture two frames later to `logs/shots/`. |
| `--diag-display=right` | Opens the game window on the display furthest to the right. |
| `--diag-hold` | Holds the mouse, as a normal start does. |
| `--diag-sound` | Keeps the sound, as a normal start does. |
| `--diag-end=SECONDS` | Ends the game this long after its first picture, without the game's own quit. |
| `--diag-zoom=SECONDS` | Zooms the window this long after the first picture. |
| `--diag-drag=SECONDS` | Asks for seven window sizes as a drag does, and logs what the window became. |
| `--diag-draws` | Writes to the log where the game first draws each flat picture: its place on the game's screen and its size. |
| `--diag-intros-shown=COUNT` | Starts the game as if the launcher had played the first COUNT sharper intro videos, 1 or 2, so the game leaves its own out. |
| `--diag-shot-on=TEXT` | With `--full-res`: saves the full-size picture a few frames after the game loads a picture whose path holds TEXT. Works with and without the larger textures. |
| `--diag-hd-dir=FOLDER` | Looks for the larger textures in FOLDER, a full path, in place of `hd-textures/`. An empty folder tests a start without them. The link to FOLDER is removed when the run ends. |

### Options of setup.sh

| Option | What it does |
| --- | --- |
| `--language=NAME` | English, French, German or Italian. |
| `--no-hd-textures` | Skip the larger textures: no upscalers are fetched and no set is made. |
| `--hd-textures` | Still accepted. Making the larger textures is the default. |
| `--generative` | Also set up the generative way. Not with `--no-hd-textures`. |
| `path/to/Dogfighter.bin` | The disc image, if it is not `./Dogfighter.bin`. |

## Not tested yet

Collected from the sections above.
- Mach9 on an M1. Nobody has played a whole mission on Mach9.
- Full resolution, now the default: nobody has looked at it on a screen.
- `--retina`: nobody has compared it with full resolution off on a screen.
- The window keeping the picture's shape, now the default: a drag by hand.
- The pointer in the menus: a real mouse or trackpad. Only moves sent by the test tool were measured.
- `--fps=N`: how a capped flight feels.
- `--wide`: not judged by a person.
- `--deep-z`: only the first mission was compared.
- `--scale 4` and the generative textures: longer missions.
- Letters drawn from the fonts: the multiplayer screens, `--font-times 2` in the game, and the console fonts `system` and `system12` with their heavier strokes.
- Hand lettering on the menus: the highlights other than CAMPAIGN were only looked at as pictures, not in the game.
- Sharper letters at 2x: `system8` (the console) and `aeroplane` (window titles) were seen in test runs but not compared. `digital_large` and `digital_small` were never loaded in a test run.
- Redrawn labels: not yet looked at in the game.
- The desk on the main menu: not yet looked at in the game.
- The plane paintings and the stamps in the mission book: not yet looked at in the game.
- `--join`: whether the Multiplayer screen lists the server.
- The sharper intro videos: the player window, its decoding and the skipping were never run. The game leaving out its own copies was run with `--diag-intros-shown`.
- The Airfix intro at level 2: only a 4-second clip was made so far. The level 3 sample was not made yet.
- Controllers: none was ever connected. Open points are whether the game gets its input, the direction of pitch, the triggers as throttle, Xbox over USB, and whether the Key configuration screen takes controller buttons.
- Turning Joystick on by itself: no controller was connected. The write was tried on a copy of `game/user.ini`, with a pretend controller name in place of `hidutil`.
- Joystick throttle: no joystick was connected. A lever that is not the third axis is read wrongly through SDL.
- The macOS side of controllers: that the Home, PS or Xbox button opens Launchpad or the Games overlay, and that System Settings > Game Controllers lists a controller and turns that off. Both are from memory.

## Legal

For personal use with a disc you own.
Never commit or share the game files: `Dogfighter.bin`, `cd/`, `game/`, `music/`, `hd-textures/`, `hd-videos/` or `Dogfighter.app`.
`.gitignore` keeps them out of git.
