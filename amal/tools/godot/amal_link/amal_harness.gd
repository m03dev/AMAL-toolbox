extends Node
## AMAL's scenario harness inside a playing game (an autoload the AMAL Live Link plugin adds). It does nothing unless
## the editor left a scenario for this run (user://amal_scenario.json, read once and removed). A scenario:
##   inputs: [{"at": 0.5, "type": "action", "action": "jump", "hold": 0.2},
##            {"at": 1.0, "type": "key", "key": "Space"}, {"at": 1.2, "type": "mouse", "x": 640, "y": 360, "button": 1},
##            {"at": 1.5, "type": "click", "node": "UI/StartButton"}, {"at": 2.0, "type": "text", "node": "UI/Name", "text": "Amal"},
##            {"at": 2.2, "type": "drag", "x": 576, "y": 324, "dx": 0, "dy": -150, "by": "pen", "seconds": 0.25}]
##   (a drag is made by "mouse", "touch" - screen touch and drag events - or "pen" - mouse events with pen pressure, what a
##   tablet sends)
##   checks: [{"at": 3.0, "node": "Player", "property": "position:y", "op": "<", "value": 300}, {"at": 1, "node": "UI/Menu", "op": "exists"}]
##   shots:  [{"at": 2.5, "name": "after_jump"}]
##   seconds: how long the run lasts
## Every input is validated before the run starts, so a bad one is named with why (an action the project does not have,
## a key name Godot does not know, a mouse input without coordinates) instead of silently doing nothing. Positions are
## in the game's own viewport pixels and are mapped to the window, so a stretched window still hits the button. A held
## input lasts at least two physics frames (a shorter one can fall between them and never be seen). A text field is
## clicked until it really has focus before typing (a field given focus by code can drop keys). The report says what
## happened to each input, each check and each picture, and the slowest frame rate seen.

const SCENARIO := "user://amal_scenario.json"
const MIN_HOLD_FRAMES := 2

var _s: Dictionary = {}
var _t := 0.0
var _events: Array = []    # [time, callable, label]
var _report := {"ok": true, "inputs": [], "checks": [], "shots": [], "fps_min": 1000.0}
var _done := false


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	if not FileAccess.file_exists(SCENARIO):
		set_process(false)
		return
	var parsed = JSON.parse_string(FileAccess.get_file_as_string(SCENARIO))
	DirAccess.remove_absolute(ProjectSettings.globalize_path(SCENARIO))
	if typeof(parsed) != TYPE_DICTIONARY:
		set_process(false)
		return
	_s = parsed
	_report["scene"] = get_tree().current_scene.scene_file_path if get_tree().current_scene else ""
	var inputs: Array = _s.get("inputs", [])
	for i in inputs.size():
		var e: Dictionary = inputs[i]
		var why := _invalid(e)
		_report["inputs"].append({"i": i, "type": e.get("type", "action"), "ok": why.is_empty(), "why": why})
		if why.is_empty():
			_schedule_input(i, e)
	for c in _s.get("checks", []):
		_events.append([float(c.get("at", 0.0)), _check.bind(c), "check"])
	for sh in _s.get("shots", []):
		_events.append([float(sh.get("at", 0.0)), _shot.bind(sh), "shot"])
	_events.sort_custom(func(a, b): return a[0] < b[0])


func _invalid(e: Dictionary) -> String:
	match String(e.get("type", "action")):
		"action":
			var a := String(e.get("action", ""))
			if a.is_empty():
				return "an action input needs 'action'"
			if not InputMap.has_action(a):
				return "the project has no input action '%s' (Project Settings > Input Map has: %s)" % [a, ", ".join(PackedStringArray(InputMap.get_actions().filter(func(x): return not String(x).begins_with("ui_")).slice(0, 12)))]
		"key":
			if OS.find_keycode_from_string(String(e.get("key", ""))) == KEY_NONE:
				return "Godot does not know the key '%s' (names like Space, Enter, A, Left, Shift)" % e.get("key", "")
		"mouse":
			if not (e.has("x") and e.has("y")):
				return "a mouse input needs x and y in the game's viewport pixels"
		"click", "text":
			if String(e.get("node", "")).is_empty():
				return "a %s input needs 'node' (its path from the scene's root)" % e.get("type")
		"drag":
			if not (e.has("x") and e.has("y") and (e.has("dx") or e.has("dy"))):
				return "a drag needs x, y and dx or dy in the game's viewport pixels"
			if not String(e.get("by", "mouse")) in ["mouse", "touch", "pen"]:
				return "a drag is made by mouse, touch or pen, not '%s'" % e.get("by")
		"wait":
			pass
		_:
			return "unknown input type '%s' (action, key, mouse, click, text, drag, wait)" % e.get("type")
	return ""


func _schedule_input(i: int, e: Dictionary) -> void:
	var at := float(e.get("at", 0.0))
	var hold: float = max(float(e.get("hold", 0.08)), MIN_HOLD_FRAMES / float(Engine.physics_ticks_per_second))
	match String(e.get("type", "action")):
		"action":
			_events.append([at, func(): Input.action_press(e["action"]), "in"])
			_events.append([at + hold, func(): Input.action_release(e["action"]); _done_input(i, ""), "in"])
		"key":
			var code := OS.find_keycode_from_string(String(e["key"]))
			_events.append([at, func(): _key(code, true), "in"])
			_events.append([at + hold, func(): _key(code, false); _done_input(i, ""), "in"])
		"mouse":
			var p := _to_window(Vector2(float(e["x"]), float(e["y"])))
			var b := int(e.get("button", 1))
			_events.append([at, func(): _mouse(p, b, true), "in"])
			_events.append([at + hold, func(): _mouse(p, b, false); _done_input(i, ""), "in"])
		"click":
			_events.append([at, func(): _done_input(i, await _click_node(String(e["node"]))), "in"])
		"text":
			_events.append([at, func(): _done_input(i, await _type_into(String(e["node"]), String(e.get("text", "")))), "in"])
		"drag":
			var from := Vector2(float(e["x"]), float(e["y"]))
			var by := Vector2(float(e.get("dx", 0.0)), float(e.get("dy", 0.0)))
			var dev := String(e.get("by", "mouse"))
			var secs: float = max(float(e.get("seconds", 0.25)), 0.05)
			const STEPS := 6
			_events.append([at, func(): _drag(dev, _to_window(from), Vector2.ZERO, 0), "in"])
			for k in range(1, STEPS + 1):
				var t := float(k) / STEPS
				_events.append([at + secs * t, func(): _drag(dev, _to_window(from + by * t), _to_window(by / STEPS) - _to_window(Vector2.ZERO), 1), "in"])
			_events.append([at + secs + 0.02, func(): _drag(dev, _to_window(from + by), Vector2.ZERO, 2); _done_input(i, ""), "in"])
		"wait":
			_events.append([at, func(): _done_input(i, ""), "in"])


func _done_input(i: int, why: String) -> void:
	var rec: Dictionary = _report["inputs"][i]
	rec["done"] = why.is_empty()
	if not why.is_empty():
		rec["ok"] = false
		rec["why"] = why


func _to_window(p: Vector2) -> Vector2:
	# the game's viewport pixels -> the window's (stretch modes scale and offset the canvas)
	return get_tree().root.get_final_transform() * p


func _key(code: int, down: bool) -> void:
	var ev := InputEventKey.new()
	ev.keycode = code
	ev.physical_keycode = code
	ev.pressed = down
	Input.parse_input_event(ev)


func _mouse(p: Vector2, button: int, down: bool) -> void:
	var mv := InputEventMouseMotion.new()
	mv.position = p
	mv.global_position = p
	Input.parse_input_event(mv)
	var ev := InputEventMouseButton.new()
	ev.position = p
	ev.global_position = p
	ev.button_index = button
	ev.pressed = down
	Input.parse_input_event(ev)


# one moment of a drag: phase 0 press, 1 move, 2 release - as a finger (screen touch and drag), or as a mouse or a pen
# (a pen is mouse events with pressure, as a tablet sends them)
func _drag(dev: String, p: Vector2, rel: Vector2, phase: int) -> void:
	if dev == "touch":
		if phase == 1:
			var d := InputEventScreenDrag.new()
			d.index = 0
			d.position = p
			d.relative = rel
			d.velocity = rel * 60.0
			Input.parse_input_event(d)
		else:
			var t := InputEventScreenTouch.new()
			t.index = 0
			t.position = p
			t.pressed = phase == 0
			Input.parse_input_event(t)
		return
	if phase == 1:
		var mv := InputEventMouseMotion.new()
		mv.position = p
		mv.global_position = p
		mv.relative = rel
		mv.button_mask = MOUSE_BUTTON_MASK_LEFT
		if dev == "pen":
			mv.pressure = 0.5
		Input.parse_input_event(mv)
		return
	var ev := InputEventMouseButton.new()
	ev.position = p
	ev.global_position = p
	ev.button_index = MOUSE_BUTTON_LEFT
	ev.pressed = phase == 0
	Input.parse_input_event(ev)


func _node(path: String) -> Node:
	var scene := get_tree().current_scene
	if not scene:
		return null
	# the scene's own root by its name or "." ("Main", "Main/Bird" for a scene whose root is Main - a Snake's play
	# test checked "Main" and found nothing, 2026-11-13)
	if path == "." or path == "" or path == String(scene.name):
		return scene
	if path.begins_with(String(scene.name) + "/"):
		path = path.substr(String(scene.name).length() + 1)
	return scene.get_node_or_null(path)


func _centre(n: Node) -> Variant:
	if n is Control:
		return _to_window(n.get_global_rect().get_center())
	if n is Node2D:
		return _to_window(n.get_global_transform_with_canvas().origin)
	return null


func _click_node(path: String) -> String:
	var n := _node(path)
	if n == null:
		return "no node at '%s' when it was time to click it" % path
	var c = _centre(n)
	if c == null:
		return "'%s' is a %s - only a Control or a Node2D can be clicked" % [path, n.get_class()]
	if n is Control and not n.is_visible_in_tree():
		return "'%s' is hidden" % path
	_mouse(c, MOUSE_BUTTON_LEFT, true)
	await get_tree().physics_frame
	await get_tree().physics_frame
	_mouse(c, MOUSE_BUTTON_LEFT, false)
	return ""


func _type_into(path: String, text: String) -> String:
	var n := _node(path)
	if not (n is LineEdit or n is TextEdit):
		return "'%s' is not a text field" % path
	for attempt in 10:   # clicked until it really has focus
		if n.has_focus():
			break
		var why := await _click_node(path)
		if not why.is_empty():
			return why
		await get_tree().process_frame
	if not n.has_focus():
		return "'%s' never took the focus (is something covering it?)" % path
	for ch in text:
		var ev := InputEventKey.new()
		ev.unicode = ch.unicode_at(0)
		ev.pressed = true
		Input.parse_input_event(ev)
		await get_tree().process_frame
		ev = ev.duplicate()
		ev.pressed = false
		Input.parse_input_event(ev)
	return ""


func _check(c: Dictionary) -> void:
	var path := String(c.get("node", ""))
	var n := _node(path)
	var op := String(c.get("op", "=="))
	var rec := {"node": path, "property": c.get("property", ""), "op": op, "want": c.get("value"), "at": c.get("at", 0)}
	if op == "exists":
		rec["ok"] = n != null
	elif op == "missing":
		rec["ok"] = n == null
	elif n == null:
		rec["ok"] = false
		rec["why"] = "no node at '%s'" % path
	else:
		var got = n.get_indexed(NodePath(String(c.get("property", ""))))
		rec["got"] = var_to_str(got)
		var want = c.get("value")
		match op:
			"==": rec["ok"] = str(got) == str(want) or (typeof(got) in [TYPE_INT, TYPE_FLOAT] and is_equal_approx(float(got), float(want)))
			"!=": rec["ok"] = str(got) != str(want)
			">": rec["ok"] = float(got) > float(want)
			"<": rec["ok"] = float(got) < float(want)
			">=": rec["ok"] = float(got) >= float(want)
			"<=": rec["ok"] = float(got) <= float(want)
			_: rec["ok"] = false; rec["why"] = "unknown op '%s'" % op
	if not rec.get("ok", false):
		_report["ok"] = false
	_report["checks"].append(rec)


func _shot(sh: Dictionary) -> void:
	var dir := String(_s.get("shot_dir", ""))
	var name := String(sh.get("name", "shot_%d" % _report["shots"].size()))
	var path := (dir.path_join(name + ".png")) if not dir.is_empty() else "user://%s.png" % name
	var err := get_viewport().get_texture().get_image().save_png(path)
	_report["shots"].append({"name": name, "path": ProjectSettings.globalize_path(path), "ok": err == OK})


func _process(delta: float) -> void:
	if _done:
		return
	_t += delta
	if _t > 1.0 and delta > 0.0:   # the slowest frame after the first second (loading is not the game's pace)
		_report["fps_min"] = min(_report["fps_min"], snappedf(1.0 / delta, 0.1))
	while not _events.is_empty() and _events[0][0] <= _t:
		var ev = _events.pop_front()
		ev[1].call()
	if _t >= float(_s.get("seconds", 6.0)) and _events.is_empty():
		_finish()


func _finish() -> void:
	_done = true
	for rec in _report["inputs"]:
		if not rec.get("ok", false):
			_report["ok"] = false
	_report["seconds"] = _t
	var f := FileAccess.open(String(_s.get("report", "user://amal_run_report.json")), FileAccess.WRITE)
	f.store_string(JSON.stringify(_report))
	f.close()
	get_tree().quit()
