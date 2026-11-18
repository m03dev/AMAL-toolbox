@tool
extends VBoxContainer
## AMAL inside the Godot editor, drawn by Godot - the dock's fallback where AMAL's web view extension (AmalWebView, which
## shows AMAL's own window in the dock) is not built. A dock with AMAL's chat for this project: each message starts an AMAL
## job (or talks to the one running) in this project's folder, with what is open in the editor - the project, the scene,
## the selected nodes. The job works in this editor through the live link (plugin.gd, port 7733: the scene tree, GDScript
## run in the editor, pictures, scenes played with checks) and its steps show here as it goes.

var DRIVER := "http://127.0.0.1:7717"   # Editor Settings > AMAL > Address (plugin.gd)
const POLL_SEC := 1.5

var _log: RichTextLabel
var _input: TextEdit
var _send: Button
var _stop: Button
var _status: Label
var _http_send: HTTPRequest
var _http_poll: HTTPRequest
var _job := ""
var _job_status := ""
var _seen := 0
var _poll_left := 0.0
var _polling := false


func _ready() -> void:
	name = "AMAL"
	var es := EditorInterface.get_editor_settings()
	if es.has_setting("amal/address"):
		DRIVER = String(es.get_setting("amal/address")).trim_suffix("/")
	custom_minimum_size = Vector2(240, 200)
	var head := HBoxContainer.new()
	var title := Label.new()
	title.text = "AMAL"
	title.add_theme_font_size_override("font_size", 15)
	head.add_child(title)
	_status = Label.new()
	_status.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_status.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	_status.modulate = Color(1, 1, 1, 0.6)
	head.add_child(_status)
	add_child(head)
	_log = RichTextLabel.new()
	_log.bbcode_enabled = true
	_log.scroll_following = true
	_log.selection_enabled = true
	_log.size_flags_vertical = Control.SIZE_EXPAND_FILL
	add_child(_log)
	_input = TextEdit.new()
	_input.placeholder_text = "Ask AMAL to change this project…  (Ctrl+Enter sends)"
	_input.custom_minimum_size = Vector2(0, 64)
	_input.wrap_mode = TextEdit.LINE_WRAPPING_BOUNDARY
	_input.gui_input.connect(_on_key)
	add_child(_input)
	var row := HBoxContainer.new()
	_stop = Button.new()
	_stop.text = "Stop"
	_stop.tooltip_text = "Stop the job working on this project"
	_stop.disabled = true
	_stop.pressed.connect(_on_stop)
	row.add_child(_stop)
	var gap := Control.new()
	gap.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(gap)
	_send = Button.new()
	_send.text = "Send"
	_send.tooltip_text = "Send to AMAL - a new job, or to the job already working here"
	_send.pressed.connect(_on_send)
	row.add_child(_send)
	add_child(row)
	_http_send = HTTPRequest.new()
	_http_send.timeout = 30
	add_child(_http_send)
	_http_send.request_completed.connect(_on_sent)
	_http_poll = HTTPRequest.new()
	_http_poll.timeout = 10
	add_child(_http_poll)
	_http_poll.request_completed.connect(_on_polled)
	_say("[i]Ask for a change to this game: AMAL sees the open scene and the selected nodes, works in this editor and shows each step here.[/i]")


func _on_key(e: InputEvent) -> void:
	if e is InputEventKey and e.pressed and e.keycode == KEY_ENTER and (e.ctrl_pressed or e.meta_pressed):
		_input.accept_event()
		_on_send()


## What is open in the editor, given with each message so the job starts from where the owner is.
static func editor_context() -> String:
	var lines: Array[String] = []
	lines.append("Godot project: %s (%s)" % [ProjectSettings.globalize_path("res://"), ProjectSettings.get_setting("application/config/name", "")])
	var root := EditorInterface.get_edited_scene_root()
	if root:
		lines.append("Open scene: %s (root %s, a %s)" % [root.scene_file_path, root.name, root.get_class()])
	var sel := EditorInterface.get_selection().get_selected_nodes()
	if not sel.is_empty() and root:
		var names: Array[String] = []
		for n in sel:
			names.append("%s (%s)" % [str(root.get_path_to(n)), n.get_class()])
		lines.append("Selected: " + ", ".join(names))
	lines.append("Work in this open editor through the `live` tool (app 'godot': scene, exec, shot, run) and check each change by playing the scene.")
	return "\n".join(lines)


func _on_send() -> void:
	var text := _input.text.strip_edges()
	if text.is_empty() or _send.disabled:
		return
	_send.disabled = true
	_say("[b]You:[/b] " + text)
	_input.text = ""
	var headers := ["Content-Type: application/json"]
	var running := _job != "" and _job_status in ["planning", "running", "resting", "waiting"]
	if running:
		var path := "/runs/%s/%s" % [_job, "reply" if _job_status == "waiting" else "say"]
		var body := {"approve": false, "note": text} if _job_status == "waiting" else {"text": text}
		_http_send.request(DRIVER + path, headers, HTTPClient.METHOD_POST, JSON.stringify(body))
	else:
		var goal := text + "\n\n" + editor_context()
		var body := {"goal": goal, "workspace": ProjectSettings.globalize_path("res://"), "studio": "code"}
		_http_send.request(DRIVER + "/runs", headers, HTTPClient.METHOD_POST, JSON.stringify(body))


func _on_sent(result: int, code: int, _h: PackedStringArray, body: PackedByteArray) -> void:
	_send.disabled = false
	if result != HTTPRequest.RESULT_SUCCESS:
		_say("[color=#e07070]AMAL is not answering on this computer - is it open?[/color]")
		return
	if code >= 300:
		_say("[color=#e07070]%s[/color]" % body.get_string_from_utf8().left(300))
		return
	var v = JSON.parse_string(body.get_string_from_utf8())
	if typeof(v) == TYPE_DICTIONARY and v.has("id"):
		_job = str(v["id"])
		_seen = 0
		_job_status = "planning"
		_stop.disabled = false
		_poll_left = 0.1


func _on_stop() -> void:
	if _job == "":
		return
	_http_send.request(DRIVER + "/runs/%s/stop" % _job, ["Content-Type: application/json"], HTTPClient.METHOD_POST, "{}")


func _process(delta: float) -> void:
	if _job == "" or _polling:
		return
	_poll_left -= delta
	if _poll_left > 0:
		return
	_polling = true
	_http_poll.request(DRIVER + "/runs/%s/chat" % _job)


func _on_polled(result: int, code: int, _h: PackedStringArray, body: PackedByteArray) -> void:
	_polling = false
	_poll_left = POLL_SEC
	if result != HTTPRequest.RESULT_SUCCESS or code >= 300:
		_status.text = "not answering"
		return
	var v = JSON.parse_string(body.get_string_from_utf8())
	if typeof(v) != TYPE_DICTIONARY:
		return
	var items: Array = v.get("items", [])
	for i in range(_seen, items.size()):
		var it: Dictionary = items[i]
		if it.get("kind") == "msg" and it.get("from") != "owner":
			_say("[b]AMAL:[/b] " + str(it.get("text", "")))
		elif it.get("kind") == "tool":
			var ok: bool = it.get("ok", true)
			_say("[color=%s]• %s[/color] %s" % ["#9aa0a6" if ok else "#e07070", it.get("tool", ""), _short(it.get("args", {}))])
	_seen = items.size()
	var st := str(v.get("status", v.get("run", {}).get("status", "")))
	if st != "":
		_job_status = st
	_status.text = _job_status
	if _job_status in ["done", "stopped", "failed"]:
		_stop.disabled = true
		_say("[i]Job %s.[/i]" % _job_status)
		_job = ""


static func _short(args) -> String:
	if typeof(args) != TYPE_DICTIONARY:
		return ""
	for k in ["path", "op", "template", "task", "command", "goal"]:
		if args.has(k):
			return str(args[k]).left(90)
	return ""


func _say(t: String) -> void:
	_log.append_text(t + "\n")
