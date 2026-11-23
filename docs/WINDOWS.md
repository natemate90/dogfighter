# Windows 10 and 11

A first version of Windows support. **Nobody has run any of it on Windows yet.**
The scripts were written on a Mac. They were not run, and not even parsed by PowerShell.
Treat every claim below as unverified unless it says "checked".

The Mac port stays as it is. `setup.sh` and `dogfighter` are unchanged.

## Status

| Part | State |
| --- | --- |
| `setup.ps1`: game files from your own BIN/CUE | Written, not run |
| `setup.ps1`: music ripped to `music\Track02.ogg` and up | Written, not run |
| `setup.ps1`: builds `winmm.dll`, `focusfix.exe`, `focushook.dll`, `joylist.exe` | Written, not run. The same C files cross-build on the Mac (checked). |
| `dogfighter.ps1`: settings, larger textures, start through the helper | Written, not run |
| Graphics on modern Windows | dgVoodoo2 by default, Windows' own DirectDraw with `-Wrapper none`. Neither tried. |
| Larger textures | Only a set made on a Mac and copied over. Windows setup does not make them. |
| Sharper intro videos | Missing. The game's own intros are left out by default. |
| Full-resolution picture, window scaling, mouse holding | Missing on Windows. Those helper parts hook Wine's own Direct3D. |
| Backups, `--join`, the F12 screenshot key fix, own pilot photos | Missing on Windows. |

## Install and play

1. Make a raw image of your own disc: one `.bin` with 2352-byte sectors, and its `.cue`. An `.iso` has no music.
   Free tools on Windows that write BIN/CUE include ImgBurn and CDRDAO. Not tried with this disc.
2. Get this repo as a zip from GitHub, or with `git clone`, and put `Dogfighter.bin` in its folder.
3. Double-click `setup.cmd`, or run it in a terminal:

   ```
   setup.cmd path\to\Dogfighter.bin
   ```

   It downloads about 220 MB the first time and needs about 3 GB of disk space.
4. Optional: copy a finished `hd-textures` folder from a Mac install into the repo folder.
5. Double-click `dogfighter.cmd`. `dogfighter.cmd -Help` lists the options.

`setup.cmd` and `dogfighter.cmd` only start `setup.ps1` and `dogfighter.ps1` with `-ExecutionPolicy Bypass`.
That way Windows runs the scripts without a change to its settings.

`dogfighter.cmd -Doctor` checks the install and lists the controllers.

## What the scripts do

They follow `setup.sh` and `dogfighter` step by step, with the same folders.
Where a Mac step uses a Python tool from `tools\`, Windows runs the same tool.

Setup:
- Downloads llvm-mingw, Python's embeddable package, libogg, libvorbis, ogg-winmm and dgVoodoo2. Each is checked against a pinned SHA-256.
- `tools\scan.py` writes the disc's data track as an ISO. `tar.exe` unpacks it to `cd\`, as `tar` does on the Mac. If `tar.exe` cannot read it, setup mounts the ISO with Windows instead. The ISO stays as `cd.iso`.
- `tools\iscab.py` installs the game in `game\`, in the chosen language. Language switching works as on the Mac.
- `tools\find_tracks.py` and `tools\rip_tracks.py` rip the music. The encoder is the same libvorbis example program the Mac builds, built for Windows.
- `game\Music` is a directory junction to `music\`. `game\cache` is one to `hd-textures\cache`. Junctions need no administrator rights, unlike symbolic links.
- It builds `winmm.dll` with the same compiler flags as `tools/build-winmm.sh`, and the helper with those of `tools/build-focusfix.sh`.

The launcher:
- Sets the game's resolution to the largest listed size that fits the screen, as the Mac launcher does.
- Raises the picture settings (32-bit colour, draw distance 450, light shafts, portals). `-Original` puts them back. Both use the same `game\dogfighter-picture-before.txt` as the Mac.
- Links the larger textures when `hd-textures\` holds a complete set. The check is `tools\upscale-textures.py --check`.
- Turns on the game's Joystick option when `joylist.exe` sees a controller.
- Starts the game through `focusfix.exe`, which loads `focushook.dll` before the game runs and presses OK in its setup dialog.

### Which parts of the helper can work on Windows

`focushook.dll` does two kinds of work.
- Game-level changes: the raised 256-pixel texture limit, the markers for pictures with more pixels, leaving out the intro videos, F12 screenshots in 32-bit colour. These patch the game's own DLLs. They do not depend on Wine. So they should work on Windows with any DirectDraw.
- Picture work: scaling into a window, full resolution, multisampling, the depth buffer. These hook `wined3d.dll`, Wine's Direct3D. Windows has no `wined3d.dll`, so they stay off.

The hook turns the picture work on only when `DOGFIGHTER_WINDOW` is set. The Windows launcher never sets it.
The game-level changes run regardless. This is read from the code, not tested.

Two small changes to the helper make it usable from a normal Windows account.
Under Wine it loads `C:\dogfighter-focushook.dll` and logs to `C:\`. A normal Windows user cannot write there.
- `DOGFIGHTER_HOOK_DLL` names the hook DLL. Without it the path is the old one.
- `DOGFIGHTER_LOG_DIR` names the folder for `dogfighter-focusfix.log` and `dogfighter-focushook.log`. With it, the hook also logs when the picture work is off.

The Mac launcher sets neither variable, so nothing changes there.

## Research

Sources were read on 23 Nov 2026 unless marked otherwise.
"From #13" means the research in issue #13 (22 Nov 2026), not checked again.

### The game on Windows 10 and 11 today

- On My Abandonware, players advise patch 1.20 and Windows XP SP2 compatibility mode. One says the videos do not play on Windows 11. From #13. [My Abandonware](https://www.myabandonware.com/game/airfix-dogfighter-cjz)
- Collection Chamber has an installer tested on Windows 11. It uses dgVoodoo and mounts the CD image. From #13. [Collection Chamber](https://collectionchamber.blogspot.com/p/airfix-dogfighter.html)
- A speedrun.com guide uses the nGlide wrapper on Windows 10. Not read (403). From #13. [speedrun.com](https://www.speedrun.com/airfix_dogfighter/guides/mlqcb)
- Typical DirectDraw failures on Windows 11: "DirectDraw initialization failed", black screens on a mode switch. dgVoodoo2 is the usual fix. From #13. [allthings.how](https://allthings.how/how-to-fix-directdraw-initialization-failed-error-on-windows-11)
- Windows 11 24H2 Auto HDR can spoil colours in old games. From #13. [TechRadar](https://www.techradar.com/computing/windows/gamers-beware-windows-11-24h2-update-could-wreck-your-colors-and-crash-your-games)
- Unknown: whether the game needs its disc in a drive at start. Under Wine, `cd\` is mapped as drive D:. On Windows, `-MountCd` mounts `cd.iso`. Whether that is needed, and whether `Mount-DiskImage` needs administrator rights, is not known.

### Graphics wrapper

| Option | Fit | Notes |
| --- | --- | --- |
| dgVoodoo2 | Default in this version | DirectX 1 to 7 on Direct3D 11. Has its own anisotropic filtering, antialiasing, window mode and resolution settings. The helper's game-level changes do not care which DirectDraw runs. |
| Windows' own DirectDraw (`-Wrapper none`) | Fallback | Reports of black screens and failed starts on Windows 11. Fine to learn what breaks. |
| WineD3D for Windows | Next experiment | The only option where the helper's picture work could run, since it ships `wined3d.dll`. Not wired in. See below. |
| DDrawCompat, cnc-ddraw, DXVK | No | DDrawCompat does no translation. cnc-ddraw does not support Direct3D games. DXVK has no DirectDraw. From #13. |

Checked tonight:
- dgVoodoo2 2.87.6 (25 Oct 2026) is a GitHub release. Its zip matches GitHub's SHA-256. `MS\x86\` holds `DDraw.dll` and `D3DImm.dll`, the two DirectX 7 files. `MS\arm64_chpe_x86\` holds builds for x86 programs on Windows on ARM. [dgVoodoo2 releases](https://github.com/dege-diosg/dgVoodoo2/releases)
- dgVoodoo's readme: "For native usage you always need the 32bit (x86) version dlls." [dgVoodoo readme](http://dege.freeweb.hu/dgVoodoo2/ReadmeGeneral/)
- `dgVoodoo.conf` has `FullScreenMode`, `ScalingMode`, and in `[DirectX]` `Filtering` (1 to 16 for anisotropic), `Antialiasing` and `dgVoodooWatermark` (on by default). The launcher writes these into `game\dgVoodoo.conf`.
- The Mac launcher already removes dgVoodoo files and its "dgVoodoo DX API Layer" video card from `game\`, left over from an earlier test under Wine. So dgVoodoo2 adds its own video card to `game\system.ini`. The launcher removes it again with `-Wrapper none`.
- WineD3D for Windows 11.21 (30 Oct 2026), LGPL. Its site only offers "latest" links, which change, so it cannot be pinned the way setup pins downloads. An archive of older builds exists. The site does not say whether `ddraw.dll` is in the zip. [WineD3D for Windows](http://fdossena.com/?p=wined3d/index.frag)

For WineD3D to run the helper's picture work, the Wine version must match the one the hooks were written for (Wine 11, Mach9 0.4.0). The window and mouse code is also written around the Mac. That is real work, so it is left for later.

### CD music

- ogg-winmm replaces `winmm.dll` in the game folder and plays `Music\Track02.ogg` and up. It reads `Music` next to its own DLL (checked in its source). ISC licence (checked). [ogg-winmm](https://github.com/dippy-dipper/ogg-winmm)
- Its README names Windows 8.1 and 10, not 11. From #13.
- A Windows 7 `winmm.dll` copied into Windows 11 crashes programs. The DLL in the game folder is the safe way. From #13. [Vogons](https://www.vogons.org/viewtopic.php?p=625425)
- Real CD audio on Windows 11 is unreliable, and hex-edited game files for CD audio set off Windows Defender. Both are avoided here. From #13.
- Forks with loop and pause fixes exist, such as ayuanx's. Try one if the music misbehaves. From #13. [ayuanx/ogg-winmm](https://github.com/ayuanx/ogg-winmm)
- dgVoodoo2's release also has a `WinMM.zip`. Not looked at.

### Intro videos

- The game's intros are Indeo 5 `.avi`. Windows blocks the Indeo codec since a 2009 security advisory. Re-enabling it is possible but should not be asked of players. From #13. [Microsoft advisory](https://support.microsoft.com/en-us/topic/microsoft-security-advisory-vulnerabilities-in-the-indeo-codec-could-allow-remote-code-execution-december-8-2009-680127c6-f4fd-e533-b641-6ab3a25fb4f4)
- So the launcher sets `DOGFIGHTER_SKIP_INTROS=2` by default, and the game goes straight to its menu. `-GameIntros` lets the game try its own.
- The sharper `.mov` videos are 10-bit HEVC. Windows 11 may need Microsoft's paid HEVC extension for them. Sources disagree. From #13.
- Plan from #13: a small Media Foundation player, with setup turning the videos into H.264. Not started.

### Controllers

- The game reads the first DirectInput joystick: X and Y for bank and pitch, Z or a slider for throttle, up to 32 buttons.
- An Xbox controller shows up in DirectInput with both triggers on one Z axis. The Mac port copies that behaviour, so throttle should feel the same. Not checked on Windows. From #13.
- A PlayStation controller shows up as "Wireless Controller" with an odd button layout. DS4Windows can make it look like an Xbox controller; HidHide stops the game from seeing both. From #13. [DS4Windows](https://github.com/ds4windowsapp/DS4Windows)
- `dogfighter.cmd -Doctor` lists what DirectInput sees, with `build\joylist.exe`.

### Windows on ARM

- Windows 11 on ARM runs x86 and x64 programs through emulation. Parallels on Apple Silicon is enough for "does it start", not for speed. From #13.
- Setup fetches the x64 llvm-mingw and Python, which need Windows 11's x64 emulation.
- dgVoodoo2 has builds for emulated x86 programs (`arm64_chpe_x86`). The launcher uses the plain x86 files everywhere. Not tried.

## Downloads and licences

Setup downloads these at setup time. Nothing is shipped in the repo.

| Download | Licence | SHA-256 source |
| --- | --- | --- |
| llvm-mingw 20261117, `ucrt-x86_64` (Windows host) | Apache 2.0 with LLVM exception; mingw-w64 parts ZPL and others | Downloaded tonight, matches GitHub's digest |
| Python 3.14.9 embeddable package, amd64 | PSF licence | Downloaded tonight from python.org |
| libogg 1.3.6, libvorbis 1.3.7 | BSD | Same pins as `setup.sh` |
| ogg-winmm at `09859f0` | ISC | Same pin as `setup.sh` |
| dgVoodoo2 2.87.6 | Own terms, see below | Downloaded tonight, matches GitHub's digest |

dgVoodoo2's terms (readme, section 1):
- "You can freely ship your game or game mod with unmodified individual dgVoodoo components (files) included."
- A re-distribution on its own must be "the original, unmodified .zip package".
- "You cannot bundle dgVoodoo inside launchers or frameworks, for general use across multiple applications."

This port fetches the original zip from dgVoodoo's own GitHub release, for this one game, and copies two unmodified files from it.
That reads as allowed, but it is a reading, not legal advice.
Older forum posts say the author wanted to be asked first. [Vogons](https://www.vogons.org/viewtopic.php?p=1226866)
Asking him is the safe choice if this becomes the default.

The pins are copied from `setup.sh`. When one changes there, change it in `setup.ps1` too.

## First test on Windows

Do these in order and keep each run's log from `logs\`.

1. `setup.cmd path\to\Dogfighter.bin`. Note any step that fails.
2. `dogfighter.cmd -Doctor`.
3. `dogfighter.cmd -Wrapper none`. Does the game start? Does it ask for the disc? If so, add `-MountCd`.
4. `dogfighter.cmd`, with dgVoodoo2. Then `dogfighter.cmd -Windowed`.
5. In the log: does `focushook` say "texture size limit raised" and "the launcher showed the first 2 intro videos"?
6. Music in the menus and in flight. `game\winmm.log` is copied next to the run log.
7. With `hd-textures\` copied from a Mac: are textures and menu letters sharp and the right size?
8. A controller: does `-Doctor` list it, and does the throttle work?
9. Windows Defender stays on. Does it flag `focusfix.exe` or `focushook.dll`? The helper loads its DLL into the game the way some malware does.

## Open decisions

- Graphics: dgVoodoo2 as the default, or wait for a WineD3D test?
- dgVoodoo2's licence: ask its author, or keep the download-at-setup reading above?
- Building on the player's PC (220 MB of downloads) or prebuilt helpers as a GitHub release made on the Mac?
- PowerShell scripts, or small exes as #13 suggests? PowerShell was chosen for this first version because it needs no build step and reads like the bash scripts.
