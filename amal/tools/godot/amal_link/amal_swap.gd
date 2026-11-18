extends SceneTree
## Puts a premade character in place of the one a game's player shows. Run by AMAL, headless:
##   godot --headless --path <project> --script res://addons/amal_link/amal_swap.gd -- res://characters/knight.glb [scene=res://player/player.tscn] [size=1.2] [turn=180]
## The game's own character is kept and hidden (its scripts and animation tree go on working on it, so nothing that
## names its nodes breaks); the new one stands where it stood, at its size, turned as it turns (amal_stand_in.gd), and
## plays its own idle, run and jump clips from how the body moves. Prints one line: AMAL_SWAP {json}.

const STAND_IN := "AmalStandIn"

## How big the new character is beside the game's own (1 = as tall as the body), and how far it is turned about its
## height, in degrees (180 for a model that faces the other way).
var size_by := 1.0
var turn_by := 0.0

func _init() -> void:
	var out := {"ok": false}
	var args := OS.get_cmdline_user_args()
	var model := String(args[0]) if args.size() > 0 else ""
	var scene := ""
	for i in range(1, args.size()):
		var kv := String(args[i])
		if kv.begins_with("scene="):
			scene = kv.substr(6)
		elif kv.begins_with("size="):
			size_by = clampf(kv.substr(5).to_float(), 0.05, 20.0)
		elif kv.begins_with("turn="):
			turn_by = kv.substr(5).to_float()
	var why := _swap(model, scene, out)
	if why != "":
		out["why"] = why
	else:
		out["ok"] = true
	print("AMAL_SWAP " + JSON.stringify(out))
	quit(0 if why == "" else 1)

func _swap(model: String, scene: String, out: Dictionary) -> String:
	if model == "" or not ResourceLoader.exists(model):
		return "Godot cannot read the model " + model + " (it is imported first; a format Godot does not import cannot be used)"
	var made = load(model)
	if not (made is PackedScene):
		return model + " is not a 3D model Godot imports as a scene"
	if scene == "":
		scene = _player_scene()
	if scene == "":
		return "no scene of this game has a CharacterBody3D at its root - name the scene that holds the player (scene)"
	out["scene"] = scene
	var packed = load(scene)
	if not (packed is PackedScene):
		return scene + " is not a scene"
	var root: Node = packed.instantiate()
	# an earlier stand-in goes, and what it stood in for shows again, so a second swap starts from the game's own
	var earlier := root.find_child(STAND_IN, true, false)
	if earlier:
		var to = earlier.get("follow")
		if to is NodePath:
			var was := earlier.get_node_or_null(to) as Node3D
			if was:
				was.visible = true
		earlier.get_parent().remove_child(earlier)
		earlier.free()
	var old := _model_of(root)
	if old == null:
		return "the scene " + scene + " shows no 3D model of its own to stand in for"
	out["replaced"] = String(old.name)
	var inst: Node = made.instantiate()
	if not (inst is Node3D):
		return model + " has no 3D root"
	# how tall the character is: the body's own collision shape says it (a skinned mesh's box does not - it is measured
	# before its skeleton scales it, and a knight sized from it came out the size of a coin, 2026-11-14)
	var body := _body_above(old, root)
	var to_parent := _chain(old.get_parent(), body if body else root)
	var target := _shape_box(body) if body else AABB()
	if target.size.y <= 0.0001:
		target = to_parent * (old.transform * _box(old))
	var b := _size_of(inst)
	if target.size.y <= 0.0001 or b.size.y <= 0.0001:
		return "the size of the game's character or of the new model could not be measured"
	var parent_scale: float = max(to_parent.basis.get_scale().y, 0.0001)
	# a first size from the scene's own numbers; in the running game the stand-in sizes itself to what is shown
	var s: float = target.size.y / b.size.y / parent_scale
	var holder := Node3D.new()
	holder.name = STAND_IN
	old.get_parent().add_child(holder)
	holder.owner = root
	# where the feet stand, in the space of the old model's parent; turned as the old model is turned, never scaled by it
	var feet := Vector3(target.position.x + target.size.x * 0.5, target.position.y, target.position.z + target.size.z * 0.5)
	holder.position = to_parent.affine_inverse() * feet
	holder.basis = old.transform.basis.orthonormalized()
	holder.add_child(inst)
	inst.owner = root
	inst.name = "Model"
	var n3 := inst as Node3D
	n3.scale = n3.scale * s
	var cb := b.position + b.size * 0.5
	n3.position = Vector3(-cb.x * s, -b.position.y * s, -cb.z * s)
	out["scale"] = snappedf(s, 0.001)
	out["height"] = snappedf(target.size.y, 0.001)
	old.visible = false
	holder.set_script(load("res://addons/amal_link/amal_stand_in.gd"))
	holder.set("follow", NodePath("../" + String(old.name)))
	holder.set("body", NodePath(_up_to_body(holder)))
	holder.set("size_by", size_by)
	holder.set("turn_by", turn_by)
	var clips := PackedStringArray()
	var player := _anim_player(inst)
	if player:
		clips = player.get_animation_list()
	out["clips"] = clips
	var idle := _clip(clips, ["idle"], ["2h", "block", "sit", "lie", "crouch", "melee", "ranged", "unarmed"])
	var run := _clip(clips, ["run", "jog", "sprint", "walk"], ["strafe", "back", "left", "right", "crouch"])
	var air := _clip(clips, ["jump_idle", "fall", "jump", "air"], ["land", "start", "full"])
	holder.set("clip_idle", idle)
	holder.set("clip_run", run)
	holder.set("clip_air", air)
	out["idle"] = idle
	out["run"] = run
	out["air"] = air
	# saved under the scene's own id, so everything that names this scene still finds it
	var path := ProjectSettings.globalize_path(scene)
	var before := FileAccess.get_file_as_string(path)
	var keep := DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path("res://.amal/before_swap"))
	if keep == OK:
		var f := FileAccess.open(ProjectSettings.globalize_path("res://.amal/before_swap/" + scene.get_file()), FileAccess.WRITE)
		if f:
			f.store_string(before)
			f.close()
	var again := PackedScene.new()
	var e := again.pack(root)
	if e != OK:
		return "the changed scene could not be packed (error " + str(e) + ")"
	e = ResourceSaver.save(again, scene)
	if e != OK:
		return "the changed scene could not be saved (error " + str(e) + ")"
	var uid_old := _uid(before)
	var after := FileAccess.get_file_as_string(path)
	var uid_new := _uid(after)
	if uid_old != "" and uid_new != "" and uid_old != uid_new:
		var w := FileAccess.open(path, FileAccess.WRITE)
		if w:
			w.store_string(after.replace(uid_new, uid_old))
			w.close()
	root.free()
	return ""

## The scene the player is: one with a CharacterBody3D at its root, the one named like a player first.
func _player_scene() -> String:
	var found := PackedStringArray()
	var stack := ["res://"]
	while not stack.is_empty():
		var d: String = stack.pop_back()
		var dir := DirAccess.open(d)
		if dir == null:
			continue
		for sub in dir.get_directories():
			if sub.begins_with(".") or (d == "res://" and sub == "addons"):
				continue
			stack.push_back(d.path_join(sub))
		for f in dir.get_files():
			if f.ends_with(".tscn"):
				var p := d.path_join(f)
				var ps = load(p)
				if ps is PackedScene and ps.get_state().get_node_count() > 0 and String(ps.get_state().get_node_type(0)) == "CharacterBody3D":
					found.append(p)
	if found.is_empty():
		return ""
	for p in found:
		if p.to_lower().contains("player") or p.to_lower().contains("character") or p.to_lower().contains("hero"):
			return p
	return found[0]

## The node that is the character's look: the highest node under the root that holds every mesh of the scene's own
## and is saved with this scene.
func _model_of(root: Node) -> Node3D:
	var meshes: Array[Node] = []
	_meshes(root, meshes)
	if meshes.is_empty():
		return null
	# the mesh with a skeleton above it is the character; without one, the largest
	var best: Node = null
	for m in meshes:
		if _skeleton_above(m, root):
			best = m
			break
	if best == null:
		var most := -1.0
		for m in meshes:
			var v := (m as MeshInstance3D).get_aabb().size
			var vol := v.x * v.y * v.z
			if vol > most:
				most = vol
				best = m
	# up to the node this scene itself owns, nearest the root but below it
	var n := best
	var top: Node = null
	while n and n != root:
		if n is Node3D and (n.owner == root or n.get_parent() == root):
			top = n
		n = n.get_parent()
	return top as Node3D

func _meshes(n: Node, into: Array[Node]) -> void:
	if n is MeshInstance3D and (n as MeshInstance3D).mesh != null:
		into.append(n)
	for c in n.get_children():
		_meshes(c, into)

func _skeleton_above(n: Node, root: Node) -> bool:
	var p := n.get_parent()
	while p and p != root:
		if p is Skeleton3D:
			return true
		p = p.get_parent()
	return false

## The box around every mesh under `top`, in `top`'s own space.
func _box(top: Node) -> AABB:
	var state := {"first": true, "box": AABB()}
	_grow(top, Transform3D.IDENTITY, state)
	return state["box"]

func _grow(n: Node, xf: Transform3D, state: Dictionary) -> void:
	if n is MeshInstance3D and (n as MeshInstance3D).mesh != null:
		var b: AABB = xf * (n as MeshInstance3D).get_aabb()
		if state["first"]:
			state["box"] = b
			state["first"] = false
		else:
			var had: AABB = state["box"]
			state["box"] = had.merge(b)
	for c in n.get_children():
		var t := xf
		if c is Node3D:
			t = xf * (c as Node3D).transform
		_grow(c, t, state)

## The physics body the model belongs to: the nearest above it, else the root when it is one.
func _body_above(n: Node, root: Node) -> Node3D:
	var p := n.get_parent()
	while p:
		if p is CollisionObject3D:
			return p
		if p == root:
			break
		p = p.get_parent()
	return null

## The transform from `top`'s space down to `n`'s own space origin: every transform from below `top` to `n`, multiplied.
func _chain(n: Node, top: Node) -> Transform3D:
	var xf := Transform3D.IDENTITY
	var p := n
	while p and p != top:
		if p is Node3D:
			xf = (p as Node3D).transform * xf
		p = p.get_parent()
	return xf

## The box of a body's collision shapes, in the body's space.
func _shape_box(body: Node3D) -> AABB:
	var box := AABB()
	var first := true
	for c in body.get_children():
		if not (c is CollisionShape3D) or (c as CollisionShape3D).shape == null:
			continue
		var cs := c as CollisionShape3D
		var half := Vector3.ZERO
		var sh = cs.shape
		if sh is CapsuleShape3D:
			half = Vector3(sh.radius, sh.height * 0.5, sh.radius)
		elif sh is CylinderShape3D:
			half = Vector3(sh.radius, sh.height * 0.5, sh.radius)
		elif sh is BoxShape3D:
			half = sh.size * 0.5
		elif sh is SphereShape3D:
			half = Vector3(sh.radius, sh.radius, sh.radius)
		else:
			continue
		var b: AABB = cs.transform * AABB(-half, half * 2.0)
		if first:
			box = b
			first = false
		else:
			box = box.merge(b)
	return box

## The size of a model in its own space: from its skeleton's bones when it has one (a head's worth added above the
## highest bone), else the box around its meshes.
func _size_of(top: Node) -> AABB:
	var sk := _skeleton(top)
	if sk == null or sk.get_bone_count() < 3:
		return _box(top)
	var xf := _chain(sk, top)
	var lo := Vector3(INF, INF, INF)
	var hi := Vector3(-INF, -INF, -INF)
	for i in sk.get_bone_count():
		var at: Vector3 = xf * sk.get_bone_global_rest(i).origin
		lo = Vector3(min(lo.x, at.x), min(lo.y, at.y), min(lo.z, at.z))
		hi = Vector3(max(hi.x, at.x), max(hi.y, at.y), max(hi.z, at.z))
	var tall := (hi.y - lo.y) * 1.12
	if tall <= 0.0001:
		return _box(top)
	return AABB(lo, Vector3(hi.x - lo.x, tall, hi.z - lo.z))

func _skeleton(n: Node) -> Skeleton3D:
	if n is Skeleton3D:
		return n
	for c in n.get_children():
		var got := _skeleton(c)
		if got:
			return got
	return null

func _anim_player(n: Node) -> AnimationPlayer:
	if n is AnimationPlayer:
		return n
	for c in n.get_children():
		var got := _anim_player(c)
		if got:
			return got
	return null

func _up_to_body(n: Node) -> String:
	var path := ".."
	var p := n.get_parent()
	while p:
		if p is CharacterBody3D or p is RigidBody3D:
			return path
		p = p.get_parent()
		path += "/.."
	return ".."

## The clip whose name holds one of `want` (earlier ones first) and none of `not_these`; the shortest such name.
func _clip(clips: PackedStringArray, want: Array, not_these: Array) -> String:
	for w in want:
		var best := ""
		for c in clips:
			var l := c.to_lower()
			if not l.contains(w):
				continue
			var skip := false
			for x in not_these:
				if l.contains(x):
					skip = true
			if skip:
				continue
			if best == "" or c.length() < best.length():
				best = c
		if best != "":
			return best
	for w in want:
		for c in clips:
			if c.to_lower().contains(w):
				return c
	return ""

func _uid(text: String) -> String:
	var line := text.get_slice("\n", 0)
	var at := line.find("uid=\"")
	if at < 0:
		return ""
	var rest := line.substr(at + 5)
	return rest.get_slice("\"", 0)
