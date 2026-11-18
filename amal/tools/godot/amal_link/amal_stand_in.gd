extends Node3D
## A premade character standing in for the one a game came with (put here by amal_swap.gd). The game's own character
## is hidden and goes on being moved by the game's scripts; this one stands at the body's feet, turns as the hidden one is turned, and
## plays its own clips from how the body moves: idle on the floor, run when moving, the air clip off the floor.

@export var follow: NodePath
@export var body: NodePath
@export var clip_idle := ""
@export var clip_run := ""
@export var clip_air := ""
## How big it stands beside the game's own character (1 = as tall as that one is shown).
@export var size_by := 1.0
## Degrees it is turned about its height on top of the facing it finds itself (180 when he says it faces backwards).
@export var turn_by := 0.0

var _old: Node3D
var _body: Node
var _anim: AnimationPlayer
var _now := ""
var _model: Node3D
var _frames := 0
var _fitted := false
## How far this model is turned about its height so that its front (+Z, as glTF models are made) is the front of the
## game's own character - first read from where the camera looks, then from the way the body really moves.
var _turn := 0.0
var _front_known := false
var _votes := 0
var _vote := 0.0

func _ready() -> void:
	_old = get_node_or_null(follow) as Node3D
	_body = get_node_or_null(body)
	_anim = _player(self)
	for c in get_children():
		if c is Node3D:
			_model = c
			break
	# shown once it has been sized to the game's own character as the game shows it
	visible = false
	if _anim:
		for c in [clip_idle, clip_run]:
			if c != "" and _anim.has_animation(c):
				_anim.get_animation(c).loop_mode = Animation.LOOP_LINEAR
	_play(clip_idle)

func _process(_delta: float) -> void:
	_frames += 1
	if not _fitted and _frames >= 3:
		_fit()
	if _old:
		position = _old.position
		# turned as the game turns its own character; its place and size are this one's own
		basis = _old.transform.basis.orthonormalized() * Basis(Vector3.UP, _turn + deg_to_rad(turn_by))
		_learn_front()
		if _old.visible:
			_old.visible = false
	if _body == null or _anim == null:
		return
	var want := clip_idle
	var on_floor := true
	if _body.has_method("is_on_floor"):
		on_floor = _body.call("is_on_floor")
	var v = _body.get("velocity")
	if v == null:
		v = _body.get("linear_velocity")
	if not on_floor and clip_air != "":
		want = clip_air
	elif v is Vector3 and Vector2(v.x, v.z).length() > 0.3 and clip_run != "":
		want = clip_run
	_play(want)

func _play(clip: String) -> void:
	if _anim == null or clip == "" or clip == _now or not _anim.has_animation(clip):
		return
	_now = clip
	_anim.play(clip, 0.15)

func _player(n: Node) -> AnimationPlayer:
	if n is AnimationPlayer:
		return n
	for c in n.get_children():
		var got := _player(c)
		if got:
			return got
	return null

## Sized and placed from the game's own character as it stands in the running game - after the game's scripts have
## scaled and placed it - measured the same way for both (their skeletons' bones, else their meshes).
func _fit() -> void:
	_fitted = true
	visible = true
	if _old == null or _model == null:
		return
	position = _old.position
	# the camera of a game seen from behind looks the way its character faces
	var cam := get_viewport().get_camera_3d()
	if cam:
		_turn = _angle_of(-cam.global_transform.basis.z)
	basis = _old.transform.basis.orthonormalized() * Basis(Vector3.UP, _turn + deg_to_rad(turn_by))
	var a := _extent(_old)
	var b := _extent(_model)
	if a.size.y <= 0.0001 or b.size.y <= 0.0001:
		return
	var k: float = a.size.y * size_by / b.size.y
	_model.scale = _model.scale * k
	b = _extent(_model)
	var ca := a.position + a.size * 0.5
	var cb := b.position + b.size * 0.5
	_model.global_position += Vector3(ca.x - cb.x, a.position.y - b.position.y, ca.z - cb.z)

## The box around a model in the world, as the renderer itself bounds it: a skinned mesh by the boxes of what each
## bone moves (bone, pose and bind applied - the mesh's own box is from before its skeleton sizes it, and a rig's
## control bones stand far from the body: a knight sized from either came out a coin or a giant, 2026-11-14); a plain
## mesh by its own box.
func _extent(top: Node3D) -> AABB:
	var pts: Array[Vector3] = []
	_corners(top, pts)
	if pts.is_empty():
		return AABB()
	var lo := pts[0]
	var hi := pts[0]
	for p in pts:
		lo = Vector3(min(lo.x, p.x), min(lo.y, p.y), min(lo.z, p.z))
		hi = Vector3(max(hi.x, p.x), max(hi.y, p.y), max(hi.z, p.z))
	return AABB(lo, hi - lo)

func _corners(n: Node, into: Array[Vector3]) -> void:
	if n is MeshInstance3D and (n as MeshInstance3D).mesh != null:
		var m := n as MeshInstance3D
		if not _skinned(m, into):
			var box := m.get_aabb()
			for i in 8:
				into.append(m.global_transform * box.get_endpoint(i))
	for c in n.get_children():
		_corners(c, into)

## The corners of a skinned mesh's per-bone boxes, in the world. False when it is not skinned or has no such boxes.
func _skinned(m: MeshInstance3D, into: Array[Vector3]) -> bool:
	var sk := m.get_node_or_null(m.skeleton) as Skeleton3D
	if sk == null:
		return false
	var skin := m.skin
	var added := false
	for s in m.mesh.get_surface_count():
		var d: Dictionary = RenderingServer.mesh_get_surface(m.mesh.get_rid(), s)
		var boxes: Array = d.get("bone_aabbs", [])
		for bi in boxes.size():
			var ab: AABB = boxes[bi]
			if ab.size.x < 0.0 or ab.size == Vector3.ZERO:
				continue
			var bone := bi
			var bind := Transform3D.IDENTITY
			if skin and bi < skin.get_bind_count():
				bone = skin.get_bind_bone(bi)
				if bone < 0:
					bone = sk.find_bone(skin.get_bind_name(bi))
				bind = skin.get_bind_pose(bi)
			elif bi < sk.get_bone_count():
				bind = sk.get_bone_global_rest(bi).affine_inverse()
			if bone < 0 or bone >= sk.get_bone_count():
				continue
			var xf := sk.global_transform * sk.get_bone_global_pose(bone) * bind
			for i in 8:
				into.append(xf * ab.get_endpoint(i))
			added = true
	return added

## The quarter turn about the height that brings +Z onto a direction in the world, seen from the game's own character.
func _angle_of(world_dir: Vector3) -> float:
	var f := _old.global_transform.basis.orthonormalized().inverse() * world_dir
	f.y = 0.0
	if f.length() < 0.3:
		return _turn
	return snappedf(atan2(f.x, f.z), PI * 0.5)

## The way the body really moves is the way the game's own character faces: five moving frames that agree set the turn.
func _learn_front() -> void:
	if _front_known or not _fitted or _body == null:
		return
	var v = _body.get("velocity")
	if not (v is Vector3):
		return
	var flat := Vector3(v.x, 0.0, v.z)
	if flat.length() < 1.0:
		return
	var want := _angle_of(flat.normalized())
	if _votes > 0 and absf(angle_difference(want, _vote)) < 0.1:
		_votes += 1
	else:
		_vote = want
		_votes = 1
	if _votes >= 5:
		_turn = _vote
		_front_known = true

