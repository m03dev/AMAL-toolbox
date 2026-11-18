@tool
extends EditorPlugin
## AMAL inside the Godot editor: a dock that is AMAL itself - its own window's page, shown by the system's web view
## (AmalWebView, AMAL's Godot extension in bin/, built from crates/amal-godot) at AMAL's address; where that extension is not built yet, the dock is a plain Godot-drawn chat (amal_dock.gd). AMAL's
## own window is left as it is. And a small server on 127.0.0.1:7733 that AMAL drives while you work (the
## a job's `live` tool). One JSON object per line in, one JSON line out:
##   {"op": "ping"}                  the Godot version, the project and the scene open now
##   {"op": "scene"}                 the open scene as a tree: path, type, script, groups, children - and its signal
##                                   connections, so AMAL sees how the nodes talk to each other, not only where they sit
##   {"op": "exec", "code": "..."}   GDScript run in the editor (the body of a function; `return` gives a value back);
##                                   a script that does not compile says so with its line
##   {"op": "shot", "path": "..."}   a picture of the editor as it is now
##   {"op": "run", "scene": "res://x.tscn", "inputs": [...], "checks": [...], "shots": [...], "seconds": 6, "path": "..."}
##                                   plays the scene with a scenario (amal_harness.gd runs it inside the game) and
##                                   answers with its report: each input done or why not, each check passed or not, the
##                                   pictures taken, the game's errors

const PORT := 7733
const HARNESS := "res://addons/amal_link/amal_harness.gd"
const SCENARIO := "user://amal_scenario.json"
const REPORT := "user://amal_run_report.json"

var _server := TCPServer.new()
var _clients: Array = []      # [StreamPeerTCP, buffer]
var _waiting_run = null        # [StreamPeerTCP, deadline_msec, shot path] while a scene plays
var _dock: Control = null      # AMAL in the editor: its page (AmalWebView) or the plain chat (amal_dock.gd)
var _web = null                # the AmalWebView inside the dock, while it is the page
var _web_check := 0.0          # seconds left before checking the page started

## Where AMAL answers (Editor Settings > AMAL > Address); this computer's AMAL unless set.
static func address() -> String:
	var es := EditorInterface.get_editor_settings()
	if not es.has_setting("amal/address"):
		es.set_setting("amal/address", "http://127.0.0.1:7717")
		es.set_initial_value("amal/address", "http://127.0.0.1:7717", false)
	return String(es.get_setting("amal/address")).trim_suffix("/")


func _enter_tree() -> void:
	if not ProjectSettings.has_setting("autoload/AmalHarness"):
		add_autoload_singleton("AmalHarness", HARNESS)
	_dock = _make_dock()
	add_control_to_dock(DOCK_SLOT_RIGHT_UL, _dock)
	_show_dock.call_deferred()
	var err := _server.listen(PORT, "127.0.0.1")
	if err != OK:
		push_warning("AMAL live link: could not listen on %d (another Godot editor has it)" % PORT)
	else:
		print("AMAL live link: listening on 127.0.0.1:%d" % PORT)


## AMAL's own page when its web view extension is here, else the plain chat.
func _make_dock() -> Control:
	if ClassDB.class_exists("AmalWebView"):
		var box := MarginContainer.new()
		box.name = "AMAL"
		box.custom_minimum_size = Vector2(300, 320)
		_web = ClassDB.instantiate("AmalWebView")
		_web.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		_web.size_flags_vertical = Control.SIZE_EXPAND_FILL
		_web.set("url", "%s/?embed=godot&project=%s" % [address(), ProjectSettings.globalize_path("res://").uri_encode()])
		box.add_child(_web)
		_web_check = 4.0
		return box
	_web = null
	return preload("res://addons/amal_link/amal_dock.gd").new()


## AMAL's tab is the one shown in its dock when the editor opens (a new dock tab would sit behind the Inspector).
func _show_dock() -> void:
	var tabs := _dock.get_parent() if _dock else null
	if tabs is TabContainer:
		tabs.current_tab = tabs.get_tab_idx_from_control(_dock)


## The web view could not start on this system: the plain chat takes the dock's place.
func _fall_back() -> void:
	push_warning("AMAL: its page could not be shown here - the dock uses the plain chat")
	remove_control_from_docks(_dock)
	_dock.queue_free()
	_web = null
	_dock = preload("res://addons/amal_link/amal_dock.gd").new()
	add_control_to_dock(DOCK_SLOT_RIGHT_UL, _dock)
	_show_dock.call_deferred()


func _exit_tree() -> void:
	_web = null
	if _dock:
		remove_control_from_docks(_dock)
		_dock.queue_free()
		_dock = null
	_server.stop()
	for c in _clients:
		c[0].disconnect_from_host()
	_clients.clear()


func _process(delta: float) -> void:
	if _web != null and _web_check > 0.0:
		_web_check -= delta
		if _web.call("has_failed"):
			_web_check = 0.0
			_fall_back()
	while _server.is_connection_available():
		_clients.append([_server.take_connection(), ""])
	for entry in _clients.duplicate():
		var peer: StreamPeerTCP = entry[0]
		peer.poll()
		if peer.get_status() != StreamPeerTCP.STATUS_CONNECTED:
			_clients.erase(entry)
			continue
		var n := peer.get_available_bytes()
		if n > 0:
			entry[1] += peer.get_utf8_string(n)
		var nl: int = entry[1].find("\n")
		if nl >= 0:
			_clients.erase(entry)
			var line: String = entry[1].substr(0, nl)
			var req = JSON.parse_string(line)
			if typeof(req) != TYPE_DICTIONARY:
				_send(peer, {"ok": false, "error": "not JSON"})
			elif req.get("op", "") == "run":
				_start_run(peer, req)
			else:
				_send(peer, _answer(req))
	_check_run()


func _send(peer: StreamPeerTCP, ans: Dictionary) -> void:
	peer.put_data((JSON.stringify(ans) + "\n").to_utf8_buffer())
	peer.disconnect_from_host()


func _answer(req: Dictionary) -> Dictionary:
	match String(req.get("op", "")):
		"ping":
			var root := EditorInterface.get_edited_scene_root()
			return {"ok": true, "app": "godot", "version": Engine.get_version_info().get("string", ""),
				"project": ProjectSettings.get_setting("application/config/name", ""),
				"path": ProjectSettings.globalize_path("res://"), "scene": root.scene_file_path if root else "",
				"playing": EditorInterface.is_playing_scene(),
				"selected": EditorInterface.get_selection().get_selected_nodes().map(func(n): return str(root.get_path_to(n)) if root else str(n.name))}
		"scene":
			return _scene()
		"exec":
			return _exec(String(req.get("code", "")))
		"shot":
			var path := String(req.get("path", ""))
			if path.is_empty():
				return {"ok": false, "error": "a path to save the picture is needed"}
			var img := EditorInterface.get_base_control().get_viewport().get_texture().get_image()
			var err := img.save_png(path)
			return {"ok": err == OK, "path": path, "error": "" if err == OK else error_string(err)}
	return {"ok": false, "error": "unknown op; one of ping, scene, exec, shot, run"}


func _scene() -> Dictionary:
	var root := EditorInterface.get_edited_scene_root()
	if root == null:
		return {"ok": true, "scene": "", "nodes": [], "note": "no scene is open"}
	var nodes: Array = []
	var links: Array = []
	_walk(root, root, nodes, links)
	return {"ok": true, "scene": root.scene_file_path, "nodes": nodes, "signals": links}


func _walk(n: Node, root: Node, nodes: Array, links: Array) -> void:
	var path := String(root.get_path_to(n))
	var item := {"path": path, "type": n.get_class(), "children": n.get_child_count()}
	var s = n.get_script()
	if s:
		item["script"] = s.resource_path
	var groups := n.get_groups().filter(func(g): return not String(g).begins_with("_"))
	if not groups.is_empty():
		item["groups"] = groups
	if n is Node2D:
		item["position"] = [n.position.x, n.position.y]
	elif n is Node3D:
		item["position"] = [n.position.x, n.position.y, n.position.z]
	nodes.append(item)
	for sig in n.get_signal_list():
		for c in n.get_signal_connection_list(sig["name"]):
			if (int(c["flags"]) & CONNECT_PERSIST) == 0:
				continue   # the engine's own wiring, not the project's
			var target = c["callable"].get_object()
			if target is Node and (target == root or root.is_ancestor_of(target)):
				links.append({"from": path, "signal": sig["name"], "to": String(root.get_path_to(target)), "method": c["callable"].get_method()})
	for child in n.get_children():
		if child.owner == root or child == root:
			_walk(child, root, nodes, links)


func _exec(code: String) -> Dictionary:
	var body := ""
	for l in code.split("\n"):
		body += "\t" + l + "\n"
	var src := "@tool\nextends RefCounted\nfunc run():\n" + (body if not code.strip_edges().is_empty() else "\tpass\n")
	var gd := GDScript.new()
	gd.source_code = src
	var err := gd.reload()
	if err != OK:
		return {"ok": false, "error": "the code does not compile (%s) - check its indentation and names; it runs as the body of func run()" % error_string(err)}
	var obj = gd.new()
	var res = obj.run()
	return {"ok": true, "result": var_to_str(res) if res != null else null}


func _start_run(peer: StreamPeerTCP, req: Dictionary) -> void:
	var scene := String(req.get("scene", ""))
	if scene.is_empty():
		var root := EditorInterface.get_edited_scene_root()
		scene = root.scene_file_path if root else String(ProjectSettings.get_setting("application/run/main_scene", ""))
	if scene.is_empty() or not ResourceLoader.exists(scene):
		_send(peer, {"ok": false, "error": "no scene to play: name one (res://...) or open it"})
		return
	var seconds := float(req.get("seconds", 6.0))
	var shot_dir := String(req.get("path", "")).get_base_dir()
	var scenario := {"inputs": req.get("inputs", []), "checks": req.get("checks", []), "shots": req.get("shots", []),
		"seconds": seconds, "shot_dir": shot_dir, "report": REPORT}
	if FileAccess.file_exists(REPORT):
		DirAccess.remove_absolute(ProjectSettings.globalize_path(REPORT))
	var f := FileAccess.open(SCENARIO, FileAccess.WRITE)
	f.store_string(JSON.stringify(scenario))
	f.close()
	if EditorInterface.is_playing_scene():
		EditorInterface.stop_playing_scene()
	EditorInterface.play_custom_scene(scene)
	_waiting_run = [peer, Time.get_ticks_msec() + int((seconds + 20.0) * 1000.0), scene]


func _check_run() -> void:
	if _waiting_run == null:
		return
	var peer: StreamPeerTCP = _waiting_run[0]
	if FileAccess.file_exists(REPORT):
		var rep = JSON.parse_string(FileAccess.get_file_as_string(REPORT))
		var scene: String = _waiting_run[2]
		_waiting_run = null
		if EditorInterface.is_playing_scene():
			EditorInterface.stop_playing_scene()
		if typeof(rep) == TYPE_DICTIONARY:
			if String(rep.get("scene", "")).is_empty():
				rep["scene"] = scene
			_send(peer, rep)
		else:
			_send(peer, {"ok": false, "error": "the game's report could not be read"})
	elif Time.get_ticks_msec() > _waiting_run[1]:
		_waiting_run = null
		if EditorInterface.is_playing_scene():
			EditorInterface.stop_playing_scene()
		_send(peer, {"ok": false, "error": "the game sent no report in time - it may have crashed on start (see Godot's Output and Debugger)"})
