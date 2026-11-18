# Plays the Snake starter headless: steers to the food with the arrow keys (score at least 3), then steers by a mouse
# swipe (direction changes), then runs into the wall (the run ends) and steers again (it starts over).
extends SceneTree

var main: Node
var frame := 0
var phase := "eat"


func _initialize() -> void:
	main = load("res://main.tscn").instantiate()
	root.add_child(main)
	current_scene = main


func action(a: String) -> void:
	var e := InputEventAction.new()
	e.action = a
	e.pressed = true
	Input.parse_input_event(e)
	var up := InputEventAction.new()
	up.action = a
	Input.parse_input_event(up)


func swipe(from: Vector2, d: Vector2) -> void:
	var b := InputEventMouseButton.new()
	b.button_index = MOUSE_BUTTON_LEFT
	b.pressed = true
	b.position = from
	Input.parse_input_event(b)
	var m := InputEventMouseMotion.new()
	m.position = from + d
	m.button_mask = MOUSE_BUTTON_MASK_LEFT
	Input.parse_input_event(m)
	var r := InputEventMouseButton.new()
	r.button_index = MOUSE_BUTTON_LEFT
	r.position = from + d
	Input.parse_input_event(r)


func _physics_process(_delta: float) -> bool:
	frame += 1
	if frame == 5:
		action("move_right")
		return false
	if phase == "eat":
		var head: Vector2i = main.snake[0]
		var f: Vector2i = main.food
		var want := ""
		if f.x > head.x and main.dir != Vector2i.LEFT: want = "move_right"
		elif f.x < head.x and main.dir != Vector2i.RIGHT: want = "move_left"
		elif f.y > head.y and main.dir != Vector2i.UP: want = "move_down"
		elif f.y < head.y and main.dir != Vector2i.DOWN: want = "move_up"
		elif f.x == head.x: want = "move_down" if main.dir.x != 0 else ""
		else: want = "move_right" if main.dir.y != 0 else ""
		if want != "": action(want)
		if main.state == main.State.OVER:
			return finish("it ended while steering to the food (score %d)" % main.score)
		if main.score >= 3:
			phase = "swipe"
			var before: Vector2i = main.next_dir
			swipe(Vector2(300, 300), Vector2(0, 80) if main.dir.x != 0 else Vector2(80, 0))
			phase = "swiped"
			set_meta("before", before)
		elif frame > 3000:
			return finish("score %d after 50 s of steering to the food" % main.score)
	elif phase == "swiped":
		if main.next_dir == get_meta("before") and main.dir == get_meta("before"):
			return finish("a mouse swipe did not steer it")
		phase = "wall"
	elif phase == "wall":
		if main.state == main.State.OVER:
			action("move_up")
			phase = "again"
	elif phase == "again":
		return finish("" if main.state == main.State.PLAYING and main.score == 0 else "steering after the end did not start it again")
	return false


func finish(problem: String) -> bool:
	print("AMAL_CHECK %s %s" % ["PASS" if problem.is_empty() else "FAIL", problem if not problem.is_empty() else "ate with the keys, turned with a swipe, ended at the wall, started again"])
	quit(0 if problem.is_empty() else 1)
	return true
