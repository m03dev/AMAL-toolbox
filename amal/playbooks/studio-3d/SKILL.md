---
name: studio-3d
description: Game-ready 3D models from words or a picture - a FLUX reference, built from its views (Pixal3D multi-view) or from one picture (TRELLIS.2, Pixal3D) on the GPU machine, Blender cleanup and a four-view check.
---
# 3D

This studio runs its recipe itself (studios/model3d.json): pictures -> the owner picks -> the model, made the way that
fits the job (its "How the model is made" value: a creature or anything to rig from its front, back and side views;
a prop or his own picture from one picture - and the next way when one does not pass) -> glb_finish -> a four-view
look -> rig. You are called only when a step fails: fix the cause, then finish the remaining steps the
same way - never a home-made clean-up instead of glb_finish (its unusable textures passed a file-exists check).

Never design the shape with parts or offsets: a proven generator or a picture model makes the shape, AMAL cleans it.

0. A proven free generator first (owner 2026-11-01: "if I ask you to make me a tree I would expect you to use the open
   source tree generator"). When the subject has a well-known open-source generator, install it (Blender extensions:
   Install from Disk; Python packages with pip) and drive it from a script - its own parameters, not hand-made parts:
   - trees, plants: Sapling Tree Gen (Blender extension, GPL) or tree-gen (friggog/tree-gen, GPL; its models may not be
     sold as assets on their own)
   - terrain: A.N.T. Landscape (Blender extension) - rocks: Rock Generator (Blender's Extra Objects)
   - buildings: Building Tools (ranjian0/building_tools, GPL) - people: MPFB2 (MakeHuman for Blender, GPL)
   - mechanical parts, furniture, props with exact sizes: build123d (code CAD)
   Anything else: `web` for an open-source generator of that kind of thing; use it when one exists and works headless,
   else steps 1-4. Not asset libraries or Infinigen (owner 2026-10-30: "those would be worst"). Generated models still
   go through step 3 and the step-4 check.

1. Reference picture. The OWNER'S PICTURE IS THE DESIGN: when he attached one (refs/), the `image` call below edits HIS
   picture (FLUX.1 Kontext in the GPU machine's ComfyUI; the first run downloads it, about 12 GB) - same creature,
   body plan, colours and art style; only the pose and background change. Leave the prompt out and it makes the picture
   model-ready by itself (whole, clear pose, nothing else in it); add one only to say more. Never send his own picture
   to TRELLIS as it is (a pose on a rock tears). Without one: `web` the subject if you don't know it, then ONE `image`
   call with style model-reference, count 1, size 1024x1024: it makes the same prompt in four 3D art styles (realistic,
   stylized, toon, chibi - owner 2026-11-01: "not all realistic - change it up"); `styles` [list] picks others
   (ref-hand-painted, ref-low-poly, ref-voxel, ref-clay) or the one style the brief or the owner names. The 3D, rig and
   textures follow the picked style. `look` at each: ONE subject, whole, every part ONCE (one tail, one head - a second
   tail or an extra limb fails the picture), plain background. The OWNER picks: ask_owner with the good ones as options
   {label: file name, image: its path}, and copy his pick to renders/ref.png. Never pick for him.
   A model that will be rigged is drawn standing upright in an A-pose, legs straight (not crouched or sitting), head up
   with the neck clear of the chest, arms out and down, wings spread high and behind, tail curving out behind to ONE
   side - nothing touching the body, and nothing overlapping anything else seen from the front: the 3D model is made from
   that one view, so parts in front of each other (arms across the wings, chin on the chest) are fused into one surface
   and tear when the rig moves them apart (the rig reports this as "touching" or "THE MODEL IS THE CAUSE").
2. Shape + texture, one of three ways (try another when one gives a bad model - never the same one again unchanged):
   - from its views (a character, a creature, anything to rig; needs a straight front picture): `views` {from:
     renders/ref.png, name} draws the back and the side from the front and checks each, then `comfy` graph
     `views_to_model` with {"front": "renders/<name>_front.png", "left": ..._left.png, "back": ..._back.png, "right":
     ..._right.png, "faces", "texture", "detail"} - a view that was not made is left out.
   - from one picture: `comfy` graph `picture_to_model` with {"image": "renders/ref.png", "mode": true (TRELLIS.2) or
     false (Pixal3D), "faces": <Generator faces>, "texture": <Texture size>, "detail": <Remesh detail>}.
   Each makes a .glb (minutes).
3. Make it an editable asset: `run` `blender -b --python-exit-code 1 --python scripts/glb_finish.py -- <the .glb> <name>
   <Triangle budget> <Height> <Texture size>` -> a clean low mesh with fresh UVs and maps baked from the generator's
   model (renders/<name>_basecolor.png, _normal.png, _ao.png), renders/<name>.fbx (the deliverable for Unreal, Unity
   and Maya - industry standard), renders/<name>.glb (the window's preview), scenes/<name>.blend,
   renders/<name>.png, renders/<name>_views.png. Never ship the generator's own texture maps.
4. `look` at renders/<name>_views.png against the brief. If the shape is wrong, the reference was the problem: make a
   clearer reference (one subject, simpler pose) or make it another way of step 2 - never patch the mesh by hand.
5. Rig + animate (when asked, or the interview says rigged): the `rig` tool, one call - `rig {mesh: renders/<name>.glb,
   name}`. It works for any model: it finds the skeleton from the shape (any number of legs, arms, wings, tails),
   then fits AdvancedSkeleton's own ready-made skeleton for that body - its names and labels are what give legs and
   arms IK, necks and tails spline controls, quadruped feet and wing fingers: wings -> dragon.ma (its front limbs are
   wings; arms are added as a copy of that limb), four legs -> horse.ma, two arms + two legs -> bipedGame.ma (others it
   ships: bird, cat, dinosaur, gorilla, bug, fish, UE5) - and builds the rig in Maya; a body no template fits gets a
   skeleton from the plan. Never rename AdvancedSkeleton's joints or invent labels. It skins it, writes one file
   per animation (renders/<name>_rig.fbx + renders/<name>@idle|walk|jump.fbx, previews .mp4/.glb) and checks the
   deformation. PASS = done. FAIL = never shown: its problems say what tears or folds. A model sitting or curled up
   cannot deform well - make it again standing with limbs clear of the body. When the rig says THE MODEL IS THE CAUSE,
   make a new reference (step 1) - never edit rig scripts or weights for it. The same when AdvancedSkeleton's model check says
   "not symmetrical": it turns the model to its own mirror plane first and mirrors only a model that is nearly
   symmetrical already - mirroring a lopsided one makes a different creature (two tails). A broken step = TROUBLESHOOT on the
   rig code it names (crates/amal-core/src/skeleton.rs, tools/maya/advanced_skeleton.py, tools/blender/rig_plan.py, creature_anim.py).
   **With Maya's tools in this job (`mcp__maya__…`, Settings › Connections › Maya through MCP) and Maya open on this
   machine,** the rig can be made in that open Maya instead of a new Maya started for the build: no cold start (the
   start that waited 15 minutes on a sign-in window), and every step can be looked at. Same script, same steps, same
   checks: `health.check` first; then its script tool runs, in Maya's Python, `import sys; sys.path.insert(0,
   "<toolbox>/job_scripts"); import advanced_skeleton as A; result = A.rig_here("<model>", "<name>", "<job folder>",
   body="biped|quadruped|winged", amald="<amald>", advanced_skeleton="<its folder>")` - the toolbox's own flow
   (prepare, model check, skeleton placed, built, bound, exported) with nothing of his open scene thrown away (unsaved
   changes stop it with that said). A viewport capture after it, looked at. The FBX lands at
   renders/<name>_as.fbx; the `rig` tool's deformation check still decides PASS. A failure stops with Maya's own
   error (rule 4). Without Maya's tools, or with Maya closed, it is the `rig` tool as above.
6. Checks: `asset:renders/<name>.glb` (the driver reads it: it imports, has normals, UVs and its textures, a
   size between 1 cm and 100 m, clean skin weights and named animations - its report gives the triangle count),
   `look:renders/<name>.png`; rigged: `file:renders/<name>_rig_report.json` with quality PASS. Attach the views and say the triangle count.
