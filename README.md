# Airfix Dogfighter on Apple Silicon

Play Airfix Dogfighter, the Windows game from 2000, on a Mac with Apple Silicon.
You play from your own original game disc.
This project holds only the tools that set the game up. It contains no game data.

[![Airfix Dogfighter for PC, gameplay video](https://img.youtube.com/vi/vuBLQVUCmEY/hqdefault.jpg)](https://www.youtube.com/watch?v=vuBLQVUCmEY)

*Gameplay video by [Highretrogamelord](https://www.youtube.com/@Highretrogamelord) on YouTube.*

Airfix Dogfighter © 2000 Unique Development Studios / Paradox Entertainment.
Airfix is a trademark of Hornby.
This is an unofficial project. It is not affiliated with any of them.

## What you need

- A Mac with Apple Silicon: M1 or later.
- macOS 26.4 or later works best (see below).
- Your original Airfix Dogfighter CD, and a CD drive to copy it. A copy you made earlier also works (see step 4).
- An internet connection while you install.
- Free disk space:
  - about 5 GB for the game (about 3 GB on macOS older than 26.4),
  - about 1 GB more for the sharper textures and menus that setup makes,
  - about 6.6 GB more for the optional extra detail on walls and floors.

### Which macOS works best

The game runs through Wine, a program that lets Windows games run on a Mac.
There are two versions of Wine, and the game picks one by itself.

On **macOS 26.4 or later** it uses Mach9, a Wine made for Apple Silicon.
On the test Mac, an M4 Max, it was much faster than the other one:

| | Older macOS | macOS 26.4 or later |
| --- | --- | --- |
| Frames a second in flight | about 30 | about 100 |
| Loading a mission | about 30 seconds | 2 to 5 seconds |
| Starts that needed a second try | about half | none of 27 |

Mach9 has been tested on one Mac, an M4 Max. It is not tested on an M1.
Nobody has played a whole mission with it yet.

On **older macOS** the game uses a Wine that needs Rosetta 2.
Rosetta 2 is Apple's tool that runs programs made for Intel Macs.
Apple removes most of Rosetta with macOS 28.

## Install

You type a few commands in Terminal.
Open it from Applications > Utilities > Terminal.
Paste each command, press Return, and wait until it is finished.

1. **Install Apple's command line tools.**

   ```
   xcode-select --install
   ```

   A window opens. Click Install and wait.

2. **Install Rosetta 2, only on macOS older than 26.4.**

   ```
   softwareupdate --install-rosetta --agree-to-license
   ```

   On macOS 26.4 or later you can skip this.
   With Rosetta installed, the game has a backup: if it does not start on Mach9, it starts on the other Wine.

3. **Get this project.**
   In Terminal, copy and run these two lines:

   ```
   git clone https://github.com/natemate90/dogfighter.git
   cd dogfighter
   ```

   Run all later commands in this folder.
   In a new Terminal window, type `cd dogfighter` again first.

4. **Copy your game disc to a file.**
   You need a CD drive and the free tool `cdrdao`.
   Install `cdrdao` with Homebrew, a free installer for tools like this (see [brew.sh](https://brew.sh)):

   ```
   brew install cdrdao
   ```

   Put the disc in the drive and run:

   ```
   cdrdao read-cd --read-raw --datafile Dogfighter.bin --driver generic-mmc:0x20000 Dogfighter.toc
   ```

   This makes `Dogfighter.bin` in the folder.
   - Any program that copies the whole disc to one BIN/CUE pair also works. Use the `.bin` file.
   - An `.iso` file does not work: it has no music.
   - If the `.bin` is somewhere else, give its place to setup: `./setup.sh path/to/Dogfighter.bin`.

5. **Run setup.**

   ```
   ./setup.sh
   ```

   This installs the game in English.
   For another language, add it at the end: `--language=French`, `--language=German` or `--language=Italian`.

   Setup takes a few minutes.
   It downloads what it needs and checks each download.
   It copies the game from your disc file and copies the music too.
   Last, it makes sharper textures for the game (see [Best picture](#best-picture)).
   At the end it says: `Setup is done. Start the game with ./dogfighter, or double-click Dogfighter.app.`

   If a step fails, setup says what went wrong.
   Fix that and run `./setup.sh` again. Finished steps are skipped.

To switch the language later, run setup again with another `--language`.
Your pilots, saves and key settings stay as they are.

## Play

```
./dogfighter
```

- The first start takes about a minute longer. It prepares Wine for the game.
- The very first start shows the game's setup window. Click OK. After that, the launcher clicks OK for you.
- With Mach9 (macOS 26.4 or later) two intro videos play. Press Esc to skip them.
- The game opens in a normal Mac window. Drag an edge or click the green button to make it bigger. The picture grows with the window.

For a game without sound, start it with `./dogfighter --mute`.

**Dogfighter.app.** Setup also makes `Dogfighter.app` in the folder.
Double-click it to play without Terminal. It starts the game with no options, so with the best picture.
You can drag it to Applications or the Dock.
If you move the game folder, run `./setup.sh` again and use the new app.

**Start from any folder.** Setup may end with a command that starts with `ln -s`.
Run it once. After that, `dogfighter` works in any Terminal folder.

### Best picture

The game starts with the best picture by itself:
- The 3D picture uses every pixel of your Retina screen. The edges of 3D shapes are drawn sharp, not stretched.
- Text, menus and the gauges in flight keep their normal size.
- The textures of the 3D world have twice the pixels.
- Letters have twice the pixels too, so they look crisper.
- The main menu, the loading screens, the medals, the pilot photos and the pictures of planes and weapons have four times the pixels.
- Window frames, buttons and the mouse arrow have twice the pixels.
- Labels with small writing, such as on the bombs, the glue tube and the book spines, are redrawn with matching fonts.
- Every start also turns some of the game's own settings up, such as the draw distance and the colour depth.

Setup makes the sharper textures once.
- It downloads two upscalers, about 100 MB. These programs enlarge pictures and draw in detail.
- The textures and menu pictures take about 800 MB of disk space.
- One run on an M4 Max took about six and a half minutes.
- If the upscalers do not run on your Mac, setup uses the Mac's own filter. Those textures are smoother, with less detail.
- Running setup again leaves a finished set as it is. It only adds menu pictures that are missing.

The textures are made on your Mac from your own game files. Nothing is uploaded.
Your game files are never changed.
If the textures are missing, the game uses its own and says how to make them.

To turn parts off, add one of these after `./dogfighter`:

| Option | What it turns off |
| --- | --- |
| `--no-hd-textures` | The sharper textures. |
| `--no-full-res` | The extra pixels. The picture is scaled to the window instead. |
| `--original` | All of it: the game looks as it did in 2000. |

To skip the sharper textures in setup, run `./setup.sh --no-hd-textures`.

This is new.
Test runs on an M4 Max measured the frame rate and checked clicks on menu buttons.
Nobody has looked at it on a real screen yet.
It is not tested on an M1.

## Mouse and keyboard

- The game holds the mouse while it is in front.
- **Ctrl+Option** frees the mouse. Then you can use other apps, or drag the window by its title bar.
- Click in the picture, or press Ctrl+Option again, to give the mouse back.
- Cmd+Tab also frees the mouse. The game takes it back when you return.
- The window title shows whether the game holds the mouse.

On a Mac keyboard, hold **Fn** for F1, F2 and F12.
To use them without Fn, turn on "Use F1, F2, etc. keys as standard function keys".
It is in System Settings > Keyboard > Keyboard Shortcuts > Function Keys.

MacBooks have no number keypad. So setup also makes **x** the key for "next weapon".
It does that only when it makes a new key settings file. It never changes one you have.

| Key | Action |
| --- | --- |
| Up / Down arrows | Pitch |
| Left / Right arrows | Bank left / right |
| d / c | Throttle up / down |
| Space | Fire primary weapon (machine guns) |
| z | Fire secondary weapon |
| x or Keypad 0 | Next weapon |
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
| Fn + F1 | Change camera view |
| Fn + F2 | Message window |
| Tab | Mission info / multiplayer info |
| p | Pause |
| Esc | Menu |
| Fn + F12 | Screenshot |

A joystick is off by default. Turn it on in the game's Options.

| Joystick button | Action |
| --- | --- |
| 1 | Fire primary weapon |
| 2 | Fire secondary weapon |
| 3 | Next weapon |
| 4 | Rear view |
| 5 | Change camera view |

The House Editor and the Paint Room have their own keys.
They are in sections 1.1 and 1.2 of `game/readme.txt`.

## Extra detail for walls and floors (optional)

This step uses an image model, a program trained to draw pictures.
It repaints 32 hand-picked surfaces at four times their size, with finer detail.
They are wood floors and boards, brick, slate, concrete, grass and cloth.

Each result is checked against the original.
If a check fails, the normal sharper texture is used instead.
The checks do not catch everything, so the list holds only surfaces whose result was looked at by eye.

What it needs:
- About 6.6 GB of downloads and disk space.
- Python 3.12 or later. Python is a programming language some tools need. Apple's command line tools only have 3.9.

To get Python 3.12, use one of these:
- With Homebrew: `brew install python@3.12`
- Or download the macOS installer of Python 3.12 or later from [python.org](https://www.python.org/downloads/) and run it.

Then run these two lines:

```
./setup.sh --generative
python3 tools/upscale-textures.py
```

The first line downloads the models. The second repaints the surfaces in your texture set.
Then start the game as usual.

How long: first the download, which depends on your connection.
The repainting then took about six and a half minutes on an M4 Max.

In a test, the living room of the first Axis mission loaded without errors.
Its floor boards showed finer wood grain, with no loss of frame rate.
Longer missions were not tested.

Licences of the two models: Stable Diffusion 1.5 (CreativeML OpenRAIL-M) and the ControlNet 1.1 tile model (OpenRAIL).

## Music

The game plays the music from the disc's audio tracks.
Setup copies them, so the disc is not needed while you play.
The music slider in the game works.

## Saves and backups

Your pilots, levels, photos and stickers are in `game/User`.
Screenshots (Fn + F12) go to `game/ScreenShots`.

To make a backup:

```
./dogfighter --backup
```

This writes a dated zip file to the `backups` folder.
It holds your saves and your settings.

To put a backup back, quit the game first. Then:

```
./dogfighter --restore
```

That puts the newest backup back.
For an older one, name it: `./dogfighter --restore=saves-20260101-120000.zip`.
Restore first backs up what is there now, so nothing is lost.

## Play with friends

- [Tailscale](https://tailscale.com) is the easiest way. It is a free app that links computers in one private network.
  - Everyone joins the same Tailscale network and uses the Tailscale addresses.
  - No router settings are needed.
- Without Tailscale, the host must forward UDP port 19400 to their Mac in the router's settings.
- All players need the same game version. It is at the top of `game/readme.txt`.
- Let Wine through the macOS firewall. Click Allow when macOS asks.
  If you missed that, add Wine under System Settings > Network > Firewall > Options.
  The file to add is `wine-mach9/wine/bin/wine` with Mach9, or `wine/bin/wine` with the Rosetta Wine.

Add your friends' addresses in the game's Address book.
Or let the launcher add one and start the game:

```
./dogfighter --join=100.64.0.7
```

- Give an IP address or a host name, without a port.
- The game must have run once before.
- The game does not connect by itself. Its menus open first.
- Nobody has checked yet that the Multiplayer screen then lists the server. If it does not, type the address into the Address book in the game.

## Problems and fixes

Start with the self-check. It does not start the game:

```
./dogfighter --doctor
```

It checks the installation and prints a fix for each problem.

| Problem | What to do |
| --- | --- |
| The game hangs, or you cannot reach it | Run `./dogfighter --stop`. |
| It says `Dogfighter is already running` | Only one game can run at a time. Quit that one, or run `./dogfighter --stop`. |
| The game starts over by itself | Nothing. On the Rosetta Wine a start sometimes fails. The launcher tries again, up to eight times. |
| The game does not start on Mach9 | The launcher switches to the Rosetta Wine by itself, if Rosetta is installed. To always use it, start with `./dogfighter --wine=stable`. |
| The mouse is stuck in the window | Press Ctrl+Option. The game holds the mouse on purpose. |
| The window cannot be dragged | Press Ctrl+Option first, then drag the title bar. |
| The text is tiny | Make the window bigger. The picture grows with it. |
| No music | Check that the `music` folder holds ten `.ogg` files. If not, run `./setup.sh` again. |
| The disc is not found | Delete the `cd` folder and run `./setup.sh` again. |
| It says `focusfix.exe` or `focushook.dll` is missing | Run `./setup.sh` again. |
| It says there is no complete set of larger textures | Run `./setup.sh` again. It makes them. |
| Setup says a tool is missing | It names the tool, and in most cases the command that installs it. Install it, then run `./setup.sh` again. |

Each start writes a log file to the `logs` folder. Include it when you ask for help.

## All options

Add these after `./dogfighter`, for example `./dogfighter --mute`.

| Option | What it does |
| --- | --- |
| (none) | Play in a window you can resize, with the best picture. |
| `--no-full-res` | Draw the picture with fewer pixels and scale it to the window. |
| `--no-hd-textures` | Use the game's own textures. |
| `--mute` | Play without any sound. The next start without it has sound again. |
| `--res=WxH` | Picture size in flight, for example `--res=1440x900`. Without it, the largest size that fits is used. |
| `--windowed=WxH` | Start with the picture at most this big, for example `--windowed=1024x768`. |
| `--keep-shape` | Keep the window in the shape of the picture when you resize it. Not tried by hand yet. |
| `--original` | Keep the game's own picture: its settings, resolution and textures. |
| `--setup` | Show the game's setup window. |
| `--join=ADDRESS` | Add a server to the game's Address book, then start the game. |
| `--wine=stable` | Use the Rosetta Wine. `--wine=mach9` uses Mach9. |
| `--doctor` | Check the installation. |
| `--stop` | End a game that hangs. |
| `--backup` | Back up your saves and settings. |
| `--restore` | Put the newest backup back. `--restore=FILE` puts back that one. |

Setup takes these:

| Option | What it does |
| --- | --- |
| `--language=NAME` | English, French, German or Italian. |
| `--no-hd-textures` | Do not make the sharper textures. |
| `--generative` | Also add the extra detail for walls and floors. |

More picture options and test options are in [docs/TECHNICAL.md](docs/TECHNICAL.md).

## Legal

For personal use with a disc you own.
Never share the game files: `Dogfighter.bin`, `cd/`, `game/`, `music/`, `hd-textures/` or `Dogfighter.app`.

How it all works, for developers: [docs/TECHNICAL.md](docs/TECHNICAL.md).
