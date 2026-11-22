# Player's guide

This guide is about playing the game once it runs.
To install and start it, see the [README](../README.md).

Some things below are marked.
- **Tested**: run in the game on a Mac, and the result was seen.
- **Not tested**: found in the game's own files only.

## Contents

1. [Getting started](#1-getting-started)
2. [Controls](#2-controls)
3. [The console](#3-the-console)
4. [Cheat sheet](#4-cheat-sheet)
5. [House Editor](#5-house-editor)
6. [Multiplayer](#6-multiplayer)
7. [Tips and known quirks](#7-tips-and-known-quirks)

## 1. Getting started

### Your pilot

The game opens with the Pilot Login window.
- Pick a pilot and click Login.
- Click Enlist to make a new pilot. Give a callsign and pick a photo.
- Delete removes a pilot for good.

All progress belongs to the pilot: missions, score, medals and planes.

### The main menu

In the main menu, point at an object and a short label shows. Click it to go there.

| Label | Opens |
| --- | --- |
| Log on as another pilot or quit | Pilot Login, or quit the game. It is the door. |
| Play a mission campaign | Campaign |
| Start/Join a multiplayer game | Multiplayer |
| Options and settings | Options. It is the books. |
| View the record of your pilot | Pilot Roster |
| Redecorate the Airfix villa | House Editor |
| Paint your own stickers | Paint Room |
| Cast & Crew | The credits |

**Options** has the picture settings, Joystick on or off, the menu mouse speed and the Key configuration.

**Pilot Roster** shows your rank, points, kills, crashes and medals.
Ranks go from Recruit up to Skywalker. There are also ranks below Recruit.

**Paint Room** is where you paint stickers for the wings and the tail.
Its keys are in the table below.

| Key | Paint Room action |
| --- | --- |
| F1 to F6 | Pen, line, fill, zoom, circle, square |
| Backspace / z | Clear the picture / undo |
| 1, 2, 3 | Sticker spot: wing top, wing bottom, tail |
| p / e / d | Put the sticker on / fetch it back to edit / remove it |
| l / s | Load / save a sticker |
| Page Up, Page Down | Other plane |
| Home, End | Other camouflage |
| Esc | Leave |

On a Mac keyboard, hold Fn for the F keys.

### The campaign

1. Click Campaign in the main menu.
2. In the left book, pick a side: Allies or Axis.
3. Pick a mission in the lower book. The paper on the right is a short brief.
4. Click OK. The briefing shows your goals.
5. Click Change model to pick a plane. Click OK to fly.

Each side has ten missions. A finished mission gets a tick.

The first mission teaches the basics. It is called Right Stuff for the Allies and Jagdschule for the Axis.
- Fly through the house and collect the items the messages ask for.
- Use the radar, bottom right, to find them.
- Shoot the ground units it sends you to.

Many missions end only when you land on your own airfield and stop.
The message "Return to base" means that.

In flight, Esc opens a menu: Resume game, Restart mission, Exit to main menu.
After a mission you can go on, play it again or try again.

### Pickups

| Pickup | What it does |
| --- | --- |
| Paint and Glue | Goals in many missions. |
| Model kit and Plans | Win the mission with both, and you get a new plane. |
| Weapon schematics | Win the mission with them, and you get a new weapon. |
| Keys | Open the door of the same colour. There are six colours. |
| Stars and crosses | Raise the TECH counter. A higher tech level gives your guns, cannon, rockets and bombs better ammunition. |
| Ammunition | Refills your ammunition. |
| Repairs | Repairs your plane. |
| Fuel | Refills your tank. |
| Cannon, Rockets, Bombs, Homing missiles, Paramines, Tesla coil, Particle beam, A-bomb | Adds that weapon. |

Some pickups hide inside vases and other things that break. Shoot them.

### Saving

The game saves your pilot by itself after each mission.
There is no save during a mission.

| What | Where in the game folder |
| --- | --- |
| Pilots | `game/User/Rosters` |
| House Editor levels | `game/User/Save/Levels` |
| Stickers | `game/User/Save/Stickers` |
| Pilot photos | `game/User/Save/Photos` |
| Screenshots | `game/ScreenShots` |
| Keys and settings | `game/user.ini` |

To back all of this up, see [Saves and backups](../README.md#saves-and-backups) in the README.

## 2. Controls

The keys, the mouse and the Mac shortcuts are in the README:
- [Mouse and keyboard](../README.md#mouse-and-keyboard)
- [Controllers and joysticks](../README.md#controllers-and-joysticks)

The House Editor keys are in [section 5](#5-house-editor).

### Change the keys

1. In the main menu, click the books for Options.
2. Open Key configuration.
3. Pick an action and press the new key.

Default key configuration puts the game's own keys back.
These steps are not tested.

The game keeps the keys in `game/user.ini`, one line per key:

```
bind F12 "screenshot"
```

- You can edit that file. Quit the game first, or it writes over your change.
- `MouseView true` turns mouse look on. `MouseInvert true` turns the mouse upside down.
- A key can run any console command, for example `bind F3 "screenshot"`. Tested.

## 3. The console

The console is a text line where you type commands for the game.

### Open and close it

1. In flight, type `hacker`. Do not press Return. The console opens at the top left.
2. Press Backspace once. The `r` of `hacker` stays in the line otherwise.
3. Type a command and press Return.
4. Type `hacker` again to close it.

Tested in flight. Not tested in the menus.

### Commands worth knowing

| Command | What it does | Example | Status |
| --- | --- | --- | --- |
| `screenshot` | Saves a picture to `game/ScreenShots`. | `screenshot` | Tested |
| `fov` | Sets the view angle. The game uses 90. More shows more at the sides. | `fov 110` | Tested |
| `where` | Says which room you are in. | `where` | Tested |
| `god` | Turns invincibility on or off. | `god` | Tested |
| `give` | Gives you a weapon. Leave out the `Wp` of its name. | `give Missile` | Tested |
| `give_techlevel` | Sets your tech level, 0 to 4. | `give_techlevel 4` | Tested |
| `type` and `spawn` | Puts you in another plane. Type the plane name, then `spawn`. | `type AcMe262`, then `spawn` | Tested |
| `kill` | Destroys your own plane. Counts as a crash. | `kill` | Tested |
| `spawn` | After a crash: starts you again. | `spawn` | Tested |
| `missionrestart` | Starts the mission again. | `missionrestart` | Tested |
| `time_scale` | Game speed. 1 is normal. | `time_scale 0.5` | Tested |
| `pause`, `unpause` | Stops and starts the game. | `pause` | Tested |
| `ai` | Autopilot on or off. | `ai on` | Tested |
| `sets` | Shows or changes a setting. See the [cheat sheet](#4-cheat-sheet). | `sets view_distance` | Tested |
| `console_changefont` | Changes the console's letters. | `console_changefont system12` | Tested |
| `log` | Also writes everything the console says to a file in `game/`. | `log console.txt` | Tested |
| `exec` | Runs the commands in a text file in `game/`, one per line. | `exec mycommands.txt` | Tested |
| `bind` | Puts a command on a key until you quit. | `bind F3 screenshot` | Tested |
| `info` | Lists everything in the mission, and your plane. | `info` | Tested |
| `list_types` | Lists all plane, vehicle, ship and weapon names. | `list_types` | Tested |
| `edithouse` | Opens the House Editor. | `edithouse` | Tested |
| `quit` | Quits the game. | `quit` | Tested |

Plane names for `type`:
`AcBf109`, `AcBlackWidow`, `AcDauntless`, `AcFiatG50`, `AcFw190`, `AcHellcat`, `AcHurricane`, `AcKomet`, `AcMe262`, `AcMustang`, `AcSpitfire`, `AcStuka`, `AcTyphoon`, `AcZero`.

Weapon names for `give`:
`MGun`, `Cannon`, `Rocket`, `Bomb`, `Teslacoil`, `Particlebeam`, `Missile`, `Paramine`, `ABomb`.

Console fonts: `system8`, `system`, `system12`, `typewriter`, `typewriter_small`, `aeroplane`, `digital_small`, `digital_large`.
`system12` and `typewriter` were tested.

### Other commands

These are in the game's files. What they do is read from their names and help texts.

| Command | What it should do | Status |
| --- | --- | --- |
| `unbind KEY` | Takes a command off a key. | Not tested |
| `controls_default` | Puts the game's own keys back. | Not tested |
| `join ADDRESS` | Joins a multiplayer server. | Not tested |
| `give_medal NAME` | Gives one medal, such as `medal_1a`. Saved to your pilot. | Tested, through `admiral` |
| `skin NAME` | Paints your plane another way. | Not tested |
| `cd_play N`, `cd_stop` | Plays a music track, or stops it. | Not tested |
| `load_language NAME` | Switches the game's language. | Not tested |
| `list_textures`, `list_sounds`, `list_instances` | Long lists for developers. | Not tested |
| `message TEXT` | A chat line in multiplayer. Nothing shows in single player. | Tested in single player only |
| `togglecamera`, `firstperson`, `console`, `show_rate` | They run, but no clear change was seen. | Tested, unclear |

## 4. Cheat sheet

Cheats are words you type during play. You do not open the console for them.
- The flight cheats work in single player only.
- They do nothing while the game is paused.
- Most show a message above the dashboard.

| Type this | Where | What happens | Status |
| --- | --- | --- | --- |
| `hacker` | In flight | Opens or closes the console. | Tested |
| `gogates` | In flight | Quits the game at once. | Tested |
| `hybris` | In flight | Invincible. Type it again to turn it off. | Tested |
| `hefaistos` | In flight | All weapons. | Tested |
| `realtimelightning` | In flight | Adds the Tesla coil, without a message. | Tested |
| `athena` | In flight | Highest tech level. | Tested |
| `slomo` | In flight | Slow motion. `time_scale 1` in the console makes it normal again. | Tested |
| `birgeroco` | In flight | Double speed. | Tested |
| `autopilot` | In flight | The plane flies itself. Type it twice; see the note below. | Tested |
| `racerwagen` | In flight | You drive a small racing car. | Tested |
| `hades` | In flight | Type it three times. The third time destroys everything, you and your bases too. | Tested |
| `admiral` | In flight | All medals. They stay on your pilot for good. | Tested |
| `prometheus` | Mission choice in Campaign | Opens all ten missions of that side. | Tested |
| `icarus` | Mission choice in Campaign | Change model then offers twelve planes of both sides. | Tested |
| `extra` | House Editor | Probably shows more settings for objects. | Not tested |
| `freerotate` | House Editor | Probably lets z and x tilt an object. | Not tested |
| `fov 110` | Console | Wider view. 90 is the game's own. | Tested |
| `sets view_distance 450` | Console | How far you see, 0 to 450. | Reading it tested |
| `sets view_portals 5` | Console | How many rooms ahead are drawn, 2 to 5. | Reading it tested |
| `sets detail_volumetriclight 2` | Console | Light shafts, 0 to 2. | Not tested |
| `sets detail_objects 100` | Console | Object detail, 0 to 100. | Not tested |
| `sets detail_effects 100` | Console | Effects detail, 1 to 100. | Not tested |
| `sets screen_gamma 50` | Console | Brightness, 0 to 100. | Not tested |
| `sets option_vaportrail true` | Console | Trails behind your plane. | Not tested |
| `sets option_actorshadows true` | Console | Shadows under planes and units. | Not tested |
| `sets option_lightmaps true` | Console | Light and shade on walls. | Not tested |

Notes:
- `autopilot` has a `p` in it, and `p` pauses the game. So the first time only pauses. The second time it works and the game runs again. To turn it off, type it twice again. `ai off` in the console also works.
- `admiral` writes the medals into your pilot file. Back up first with `./dogfighter --backup`.
- `hades` ends the mission as a failure, and `kill` counts as a crash. Both stay on your pilot.
- After `racerwagen` there is no dashboard. To get a plane back, use `type AcHurricane` and `spawn` in the console.
- `sets` values are kept in `game/user.ini` when you quit. The Options menu changes the same values.
- The launcher sets `view_distance` 450, `view_portals` 5 and `detail_volumetriclight` 2 at every start. A change to these three lasts until the next start, unless you start with `./dogfighter --original`.

## 5. House Editor

The House Editor makes your own levels in the Airfix house.
You place furniture, toys, planes, tanks, ships, pickups, locked doors and start points.
Your levels are the levels for multiplayer.

Open it from the main menu: "Redecorate the Airfix villa".
Or type `edithouse` in the console. Tested.

### Build a level

1. Press n and pick a house. There are nine; see the table in [section 6](#starter-houses). Tested.
2. Look around with the arrow keys. Space switches between the fixed and the free camera.
3. Press 1 for furniture, 2 for accessories, 3 for toys.
   Toys hold the planes, vehicles, ships, buildings, pickups and keys.
4. Place the object. A left click lets go of it. The right mouse button turns it and lifts it.
5. Place at least one Player start position. It is with the toys.
6. Press s to save. Give the level a name.

| Key | House Editor action |
| --- | --- |
| Arrow keys | Turn and zoom (fixed camera), or move (free camera) |
| Space | Fixed or free camera |
| + and - | One floor up or down |
| m | Map of the house on or off |
| n / l / s | New house / load a level / save the level |
| 1 / 2 / 3 | Pick furniture / an accessory / a toy |
| d | Copy the selected object |
| Delete | Remove the selected object |
| Shift | Turn in steps of 45 degrees |
| Esc | Undo the last move, or leave |

More you can set:
- Doors can be open, or locked with one of the six colour keys.
- Windows can be broken or bulletproof.
- Planes and vehicles get a team, a squad, a skill and how aggressive they are.
- Click a door to open it, or a light switch to turn it on or off.
- Right-click a doorway to move into the next room.

Not tested: saving and loading a level, and the settings in this list.

### Where levels are saved

Each level is two files in `game/User/Save/Levels`:
- `NAME.level` holds what you placed.
- `NAME.afs` is made by the game when you save. Do not edit it.

### Share a level

1. Quit the game.
2. Send both files, `NAME.level` and `NAME.afs`.
3. Your friend puts them in `game/User/Save/Levels`.

For multiplayer this is not needed. Players who join get the level from the host. Not tested.

### Limits

- A level without a Player start position cannot be saved. The game asks you to place one.
- A level uses one house. Some rooms are closed in some houses.
- Load has an "Add objects only" choice. It should add a saved level's objects to the open one.

These limits come from the game's own texts. They are not tested.

## 6. Multiplayer

How to connect over the internet is in the README: [Play with friends](../README.md#play-with-friends).

### Host a game

1. Click Multiplayer in the main menu.
2. Choose Start server.
3. Pick a game mode and a level, and name the server.
4. Settings has the most players, the time limit in minutes, the crash limit and Axis vs Allies teams.
5. Click Start server.

The level list shows only levels made in the House Editor.
A new install has none, so the list starts empty. Build a level first.

### Join a game

1. Click Multiplayer.
2. Pick a server under Available servers. Refresh list looks again.
3. A server outside your home network needs its address in the Address book.
4. Click Join game.

In the game, primary fire starts you, and secondary fire picks another plane.
Tab shows the score: callsigns, kills and deaths.

None of these menu steps are tested. They come from the game's own texts.

### Starter houses

Every level starts from one of the game's nine houses.
These are suggestions. Nobody has played them in multiplayer yet.

| House | Rooms | Suggested for |
| --- | --- | --- |
| Kids | One room | 2 or 3 players |
| Cellar | One room | 2 or 3 players |
| Bathroom, Sisters | Two rooms | 3 or 4 players |
| Living, Dining | Two rooms | 4 to 6 players |
| Backyard, Laundry | Garden and a room | 4 to 6 players |
| Front yard, Garage | Garden and a room | 4 to 6 players |
| Parents, Attic | Two floors | 4 to 6 players |
| Halls (flooded) | The halls, with water | 4 to 8 players |
| Living, Dining, Kitchen | Three rooms | 6 to 8 players |

A simple dogfight level:
- one Player start position for each player, spread over the rooms,
- a few weapon pickups, Repairs and Ammunition,
- no locked doors.

## 7. Tips and known quirks

- **Never press Cancel in the game's setup window.** The game then resets its settings and your pilot name. If you have a backup, quit and run `./dogfighter --restore`.
- **Two intro videos** play at the start on macOS 26.4 or later. Press Esc to skip each one.
- **The flight cheats need you in flight.** The console was only tried in flight too.
- **The `r` of `hacker`** stays in the console line. Press Backspace first.
- **`autopilot` pauses the game** the first time. Type it twice.
- **`fov` above 90** can show a stretched band at the bottom of the picture.
- **Back up before cheating**: `./dogfighter --backup`. Some cheats change your pilot for good.
- **Screenshots** are TGA pictures in `game/ScreenShots`. Fn+F12 takes one. Some Mac apps cannot open TGA.
- **Many missions end only after you land** on your own airfield and stop.
- **Pickups hide in breakables.** Shoot vases, plates and bottles.
- **Keys and settings** are saved when you quit the game cleanly. Use the game's own Quit.
