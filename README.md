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
  - about 1.2 GB more for the sharper textures and menus that setup makes,
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
- If you made the sharper intro videos, they play first, in their own window, on either Wine. Esc, a click or any key skips one. The game then leaves out its own copies. That part was tested on Mach9. Nobody has tried the video window itself yet. How to make them is in [docs/TECHNICAL.md](docs/TECHNICAL.md#intro-videos).
- The game opens in a normal Mac window. Drag an edge or click the green button to make it bigger. The picture grows with the window.
- The window keeps the shape of the picture, so the picture is never stretched. Drag one side and the other follows.

For a game without sound, start it with `./dogfighter --mute`.

**Dogfighter.app.** Setup also makes `Dogfighter.app` in the folder.
Double-click it to play without Terminal. It starts the game with no options, so with the best picture.
You can drag it to Applications or the Dock.
If you move the game folder, run `./setup.sh` again and use the new app.

**One app with everything inside.** After setup, on macOS 26.4 or later, run:

```
tools/build-app.sh --full
```

- This makes `dist/Dogfighter.app`, about 2.6 GB. It holds Wine, the game, the music, the sharper textures and the intro videos.
- It runs without the game folder. You can move it to Applications.
- It plays like `./dogfighter`, with the same best picture.
- What the game writes goes to `~/Library/Application Support/Dogfighter`: saves, settings, screenshots, logs and backups.
- The build copies your saves from `game/` into the app. Its first start copies them from there into that folder. The ones in `game/` are never changed.
- Saves made with `./dogfighter` after the build are not in the app. Build it again before its first start to take them along. That takes about ten seconds.
- The first start takes about a minute longer. It prepares Wine.
- It uses Mach9 only. It has no fallback to the Rosetta Wine.
- It holds your game files. Keep it to yourself.

**Start from any folder.** Setup may end with a command that starts with `ln -s`.
Run it once. After that, `dogfighter` works in any Terminal folder.

**How to play.** The menus, pickups, console, cheats, House Editor and multiplayer levels are in the [player's guide](docs/GUIDE.md).

### Best picture

The game starts with the best picture by itself:
- The 3D picture uses every pixel of your Retina screen. The edges of 3D shapes are drawn sharp, not stretched.
- Jagged edges of 3D shapes are smoothed. The ground and walls stay sharp in the distance.
- Text, menus and the gauges in flight keep their normal size.
- The textures of the 3D world have twice the pixels.
- The letters of the Pilot Login, the Pilot Roster, Mission Info, the message line in flight, the mission book and the briefing are drawn again from the Mac's own matching fonts, with four times the pixels, so they look sharp. Their strokes keep the weight and the soft grey of the original letters. The other letters have twice the pixels.
- The main menu, the loading screens, the mission books, the briefing, the medals, the pilot photos and the pictures of planes and weapons have four times the pixels.
- Window frames, buttons and the mouse arrow have twice the pixels.
- The gauges in flight have four times the pixels. Their labels, such as FUEL and SPEED, are redrawn with a matching font.
- Labels with small writing, such as on the bombs, the glue tube and the book spines, are redrawn with matching fonts.
- The model kit boxes and paint tins on the main menu's desk are drawn again from photos of real 1990s Airfix boxes and a Humbrol tin. Setup downloads the photos once.
- The twelve plane paintings on the loading screens and in the model window are drawn again from Airfix's box art. Setup downloads the pictures once.
- The hand-written signs on the main menu, such as CAMPAIGN, the BACK, OK and CHANGE MODEL signs, and the stencil headings of the briefing papers are drawn again from the game's own pixels. The upscaler had invented shapes in them.
- The ink stamps on the Axis and US Airforce pages of the mission book are drawn again as sharp ink. The US page shows the wartime winged star instead of the 1947 seal.
- Every start also turns some of the game's own settings up, such as the draw distance and the colour depth.

Setup makes the sharper textures once.
- It downloads two upscalers, about 100 MB. These programs enlarge pictures and draw in detail.
- The textures and menu pictures take about 1 GB of disk space.
- One run on an M4 Max took about eleven minutes.
- If the upscalers do not run on your Mac, setup uses the Mac's own filter. Those textures are smoother, with less detail.
- Running setup again keeps a finished set. It only adds missing menu pictures and draws the labels, letters, signs, desk, paintings and stamps again.

The textures are made on your Mac from your own game files. Nothing is uploaded.
Your game files are never changed.
If the textures are missing, the game uses its own and says how to make them.

To turn parts off, add one of these after `./dogfighter`:

| Option | What it turns off |
| --- | --- |
| `--no-hd-textures` | The sharper textures. |
| `--no-hd-videos` | The sharper intro videos. |
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
- The pointer in the menus moves as far over the picture as the Mac pointer moves over the window. Its speed follows the Mac's own setting, in System Settings > Mouse or Trackpad.
- The slider "Menu mouse sensitivity" in the game's Options makes it slower or faster than that. A new start has it at the matching speed.

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

The House Editor and the Paint Room have their own keys.
They are in sections 1.1 and 1.2 of `game/readme.txt`.

## Controllers and joysticks

Nobody has tried this with a real controller yet.
What was checked without one is in [docs/TECHNICAL.md](docs/TECHNICAL.md), under Controls.

These should work:
- Xbox Wireless Controller (Series X|S, and Xbox One models with Bluetooth), over Bluetooth.
- PlayStation DualShock 4 and DualSense, over Bluetooth or a USB cable.
- Nintendo Switch Pro Controller.
- USB and Bluetooth joysticks, and other gamepads macOS can see.

Use Bluetooth for an Xbox controller. macOS may not see one on a USB cable.

To set it up:
1. Connect the controller before you start the game. Pair it in System Settings > Bluetooth, or plug it in.
2. Run `./dogfighter --doctor`. Its last lines list the controllers the game can see.
3. Start the game. When a controller is connected, the launcher turns on Joystick in the game's Options.

The launcher never turns Joystick off. You can do that in Options, behind the books in the main menu.

The game uses one controller: the first in that list.

| Controller | Action |
| --- | --- |
| Left stick | Pitch and bank |
| Right trigger (RT / R2) | More speed while you hold it |
| Left trigger (LT / L2) | Less speed while you hold it |
| A / Cross | Fire primary weapon |
| B / Circle | Fire secondary weapon |
| X / Square | Next weapon |
| Y / Triangle | Rear view |
| LB / L1 | Change camera view |

- The stick should work like a flight stick: pull it down to climb.
- With both triggers released the plane flies at half speed, once you have touched a trigger.
- The right stick and the D-pad do nothing. The game does not read them.
- The keyboard and the mouse keep working next to the controller.
- On a joystick with a throttle lever, the lever should set the speed. Not checked yet.
- On some joysticks the twist of the stick comes before the lever. Then the twist changes the speed.
- The fix for that is in [docs/TECHNICAL.md](docs/TECHNICAL.md), under Controllers.

**Other buttons.** The game's Options have a Key configuration screen.
Nobody has checked yet whether it takes controller buttons.
The sure way is the file `game/user.ini`. Quit the game first, then add or change a line like this:

```
bind jbutton5 "+thrustinc"
```

| Name in the file | Xbox | PlayStation |
| --- | --- | --- |
| `jbutton0` | A | Cross |
| `jbutton1` | B | Circle |
| `jbutton2` | X | Square |
| `jbutton3` | Y | Triangle |
| `jbutton4` | LB | L1 |
| `jbutton5` | RB | R1 |
| `jbutton6` | View | Create / Share |
| `jbutton7` | Menu | Options |
| `jbutton8` | Left stick click | L3 |
| `jbutton9` | Right stick click | R3 |

The actions are the words in quotes in that file, such as `+primattack`, `use next` or `pause_toggle`.

**The Xbox, PS or Home button.** macOS uses it for itself.
It may open Launchpad or the Games overlay. That would put another app in front of the game.
Do not press it while you play.
The switch for it should be in System Settings > Game Controllers, with the controller connected.
What the button does, and where that switch is, are from memory. Nobody has checked them on a Mac.

**If the controller is not found:**
- Run `./dogfighter --doctor`. It says `no controller found` when Wine sees none.
- Check that macOS sees it. It should be listed in System Settings > Game Controllers (place not checked).
- Quit the game, connect the controller, then start the game again.
- Disconnect other controllers. The game only uses the first one.
- If the plane steers by itself, the stick does not rest in the middle. Turn Joystick off in Options, and start with `./dogfighter --no-auto-joystick` from then on.

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
Screenshots (Fn + F12) go to `game/ScreenShots`, as TGA pictures named `Img00000.tga` and up.
Fn + F12 works in a flight, not in the menus.

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
It also lists the controllers the game can see.

| Problem | What to do |
| --- | --- |
| The game hangs, or you cannot reach it | Run `./dogfighter --stop`. |
| It says `Dogfighter is already running` | Only one game can run at a time. Quit that one, or run `./dogfighter --stop`. |
| The game starts over by itself | Nothing. On the Rosetta Wine a start sometimes fails. The launcher tries again, up to eight times. |
| The game does not start on Mach9 | The launcher switches to the Rosetta Wine by itself, if Rosetta is installed. To always use it, start with `./dogfighter --wine=stable`. |
| The mouse is stuck in the window | Press Ctrl+Option. The game holds the mouse on purpose. |
| The window cannot be dragged | Press Ctrl+Option first, then drag the title bar. |
| The text is tiny | Make the window bigger. The picture grows with it. |
| The Mac gets warm or loud | Start with `./dogfighter --fps=60`. The game then draws 60 pictures a second, not 120. |
| The controller does nothing | See "Controllers and joysticks" above. Connect it before you start the game. |
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
| `--no-hd-videos` | Let the game play its own intro videos. |
| `--mute` | Play without any sound. The next start without it has sound again. |
| `--no-auto-joystick` | Do not turn on Joystick in the game's Options when a controller is connected. |
| `--res=WxH` | Picture size in flight, for example `--res=1440x900`. Without it, the largest size that fits is used. |
| `--windowed=WxH` | Start with the picture at most this big, in points, for example `--windowed=1024x768`. |
| `--no-keep-shape` | Let the window take any shape. The picture is then stretched to fill it. |
| `--fps=N` | Show at most N pictures a second, for example `--fps=60`. Without it the game draws as fast as the screen shows pictures. |
| `--no-pointer-match` | Leave the speed of the pointer in the menus to the game. |
| `--original` | Keep the game's own picture: its settings, resolution, textures and intro videos. |
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
Never share the game files: `Dogfighter.bin`, `cd/`, `game/`, `music/`, `hd-textures/`, `hd-videos/`, `Dogfighter.app` or `dist/`.

How it all works, for developers: [docs/TECHNICAL.md](docs/TECHNICAL.md).
