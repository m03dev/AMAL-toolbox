---
name: game-prototype
description: Any Godot 4 game - one order from template to a build that plays: a blockout that plays first, then one checked feature at a time (add-ons such as GodotSteam, local co-op, multiplayer, export), with rigged, animated characters from the 3D line when asked.
---
# Godot games

## Any Godot game: one order, a working copy first

Owner 2026-11-11: a bare-bones game in no more than 10 minutes, a working copy within the first five, blockouts made
first. The same order for every game, small or big; each step is checked before the next starts. No design document,
asset list or research comes before the game runs.

1. **Project**: AMAL has already made it from the nearest template (`godot_project`, the line's opening move) - it
   loads and runs. Read what it has; never write project.godot or a `.tscn` scene by hand as text - their resource
   lines (`ext_resource`, `sub_resource`, ids) break and Godot cannot read the file (2026-11-13: a blockout's
   player.tscn and main.tscn written as text stopped the job for turns). Let Godot write its own scenes:
   - **a blockout**: the nodes made in the main scene's script when it starts - `CharacterBody3D.new()`, a
     `MeshInstance3D` with a `CapsuleMesh` / `BoxMesh`, a `CollisionShape3D`, a `Camera3D`, `add_child(...)`;
   - **a scene to keep**: a builder script run once,
     `godot --headless --path "<project>" --script res://tools/build_<scene>.gd` (extends SceneTree), that makes the
     nodes, sets `owner` on each, then `PackedScene.new().pack(root)` and `ResourceSaver.save(scene, "res://<scene>.tscn")`
     and `quit()`.
   Paths always in quotes (AMAL's projects folder has a space in its name).
2. **Blockout that plays** - the first task of every plan: the smallest version of what he asked, with grey boxes,
   capsules and placeholder text for everything (player, enemies, goal, level) - the player moves, the main thing to do
   works, a scene runs (`run/main_scene` set). `godot_check` must say "played 300 frames; no errors", then `godot_play`
   it and show him the running game (`tell_owner`). No art, no add-ons, no research in this step.
3. **One feature at a time**, each followed by `godot_check` (and `godot_play` when it needs input): movement and
   camera, the goal, enemies that notice, approach, attack, take hits and die, the UI (score, health, a win and a lose
   screen). Plan at most five tasks (the line sends a longer plan back); detail grows from a game that already plays.
   - **Add-ons** (only when asked): the official release for THIS Godot version (`godot --version`) into
     `addons/<name>/`, enabled in project.godot, then `godot_check`. GodotSteam: the GDExtension build for the installed
     Godot; `steam_appid.txt` with 480 (Valve's test app) next to project.godot while testing; `Steam.steamInitEx()` in
     an autoload with `Steam.run_callbacks()` every frame; without the Steam client running it says so and still plays.
   - **Local co-op** = two players on one machine: an input action set per player (`p1_*` keyboard, `p2_*` joypad
     device 0 or a second key set), a player scene with an exported `player_id`, a shared camera that frames both or
     split screen with two SubViewports.
   - **Online / Steam co-op**: lobbies and P2P through GodotSteam's networking (SteamMultiplayerPeer when the build has
     it, else ENet for LAN tests) with Godot's MultiplayerAPI - read the multiplayer skills first.
4. **Characters and props** come the way the line's Characters setting says - the job is told it every turn (THE
   LINE'S SETTINGS, ASSETS):
   - **Ask me** (the default): one `interview` question with the first plan - premade or made from scratch (and, for
     from scratch, whether AMAL draws the reference pictures or he gives his own); the job goes on with premade
     when he is away. His choice goes into the plan's task titles.
   - **Premade assets**: right after the blockout plays. One `premade` search for each thing, the first find that is
     ready here (`ready: true`); KayKit and Quaternius packs are CC0, rigged and animated, with their clips. The
     work is the look, not the rig: scale and facing, the clip for each action (idle, walk, run, attack, hit, death)
     wired to the AnimationPlayer / AnimationTree, materials, lights, the camera. Nothing ready fits: the placeholder
     stays and the job goes on - never a second search for the same thing. Ten minutes from request to a game that
     plays with rigged, animated characters is the measure (owner 2026-11-13).
   - **Made by the 3D line**: after the game plays with placeholders (see "Characters from the 3D line" below).
   - **Placeholders**: shapes only.
5. **Build**: `godot_export` - a program that runs by itself, in the Library's Apps; run it once headless to see it
   start without errors. A failed export stops here with Godot's errors.
6. **Hand-over**: the build, the project folder, `notes.md` (how to run, controls, what is next).

Never take out or stub a part he asked for (the add-on, the co-op) to make a check pass - fix the cause or say what
stands in the way. Add nothing he did not ask for: "make a 3d game" is a small, complete 3D game of the model's choosing,
not a D&D prototype.

## Characters from the 3D line (when asked)

A game is judged as a game, not as a pile of assets: a character you control moves and fights with its own
animations, at least one enemy reacts, and the space reads as the place it is meant to be.

- **Through the 3D line** (studio-3d), in the game's one art style: reference picture -> the owner picks -> model ->
  clean-up -> four-view check -> rig -> clips. Premade assets (the Assets workspace, CC0 / CC-BY, credited) first when
  one fits. Every clip is its own `.fbx` beside the character's `.fbx` rig, named the way engines expect (`idle`,
  `walk`, `run`, `attack_melee`, `attack_cast`, `hit`, `death`, plus what the game needs). Before a character counts:
  the rig passes its checks (no joint past its limits, knees and elbows bend the right way, no stretched skin) and each
  clip is looked at from the front and the side in a render.
- **In Godot**: the FBX files imported; an `AnimationTree` state machine per character driven by its clips (idle <->
  walk <-> run, attack, hit, death), swapped in for the placeholder in the scene that already plays.
- **Environment kit** (when the level needs more than boxes): modular pieces on one grid (2 m floor and wall tiles, a
  door, pillars, props) - a proven generator first (Building Tools, A.N.T. Landscape, Sapling), the 3D line for hero
  pieces, one texture set or trim sheet so it reads as one place.
- **Play check**: `godot_check`, then a scripted play-through (move the player to the enemy, attack until it dies)
  recorded as frames and looked at: the player moves, the attack plays, the enemy's hit and death play. A game whose
  characters slide or T-pose is not finished.

## D&D templates (when he asks for D&D, or as a starting idea for a fight)

- **Goblin ambush** (top-down): a fighter with sword and shield (idle, walk, run, attack_melee, block, hit, death)
  against three goblins (idle, run, attack_melee, hit, death) in a ruined forest road; loop: move, block, strike.
- **Tavern brawl** (third-person): a dwarf brawler (idle, walk, punch, kick, dodge, hit, death) against two drunk
  bandits; a tavern kit (tables, benches, bar, barrels, hearth) that breaks into pieces on hits.
- **Lich's crypt** (isometric): a wizard (idle, walk, attack_cast, hit, death) with a fire bolt against skeleton
  warriors (rise_from_ground, walk, attack_melee, hit, collapse) in a crypt kit (sarcophagi, pillars, candles, gates).
- **Owlbear hunt** (third-person): a ranger with a bow (idle, walk, run, draw_bow, shoot, dodge, hit, death) against
  an owlbear - a quadruped rig (idle, prowl, charge, swipe, roar, hit, death); a forest clearing from Sapling trees.
- **Dragon's lair** (third-person boss): a paladin (idle, walk, run, attack_melee, block, hit, death) against a young
  red dragon - wings and tail in the rig (idle, walk, bite, tail_swipe, fly, breath, hit, death); a cave kit with a gold
  hoard. The hardest: a winged quadruped rig and secondary motion on wings and tail.

## Getting harder each time

Each new prototype takes on one thing the last one did not: a second enemy type, a quadruped, a flying creature, a
spell with an effect, a boss with phases, two players. What failed last time is fixed in AMAL first (the cause, in
general) - never worked around inside one prototype.

Levels: a dungeon, cave, maze or town layout grows from rules with `use` `markovjunior.generate` (DungeonGrowth,
BasicDijkstraDungeon, Cave, ModernHouse, SeaVilla ...; 2D gives PNG maps to build the Godot scene from, 3D gives .vox
voxel buildings) - pick the layout that fits the design, then build it with the environment kit. A Godot scene is
checked with `godot_check` after every change.
