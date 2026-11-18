# Plays the Flappy starter headless (godot --headless --path <starter> -s <this>): flaps through the gaps for ten
# seconds (score at least 3), then lets the bird fall (the run ends), then a flap starts again. Prints AMAL_CHECK PASS
# or AMAL_CHECK FAIL with why.
extends SceneTree

var main: Node
var frame := 0
var phase := "fly"
var why := ""


func _initialize() -> void:
	main = load("res://main.tscn").instantiate()
	root.add_child(main)
	current_scene = main   # as when the game runs: the restart reloads it


func press() -> void:
	var e := InputEventAction.new()
	e.action = "flap"
	e.pressed = true
	Input.parse_input_event(e)
	var up := InputEventAction.new()
	up.action = "flap"
	Input.parse_input_event(up)


func _physics_process(_delta: float) -> bool:
	frame += 1
	if phase == "again":
		if frame > 900:
			var now: Node = current_scene
			return finish("" if now != null and is_instance_valid(now) and now.get("state") == 0 else "a flap after the end did not start it again")
		return false
	var bird: Node2D = main.get_node("Bird")
	if frame == 10:
		press()
	elif phase == "fly" and frame > 10:
		# aim for the middle of the next gap
		var target := 330.0
		for pair in main.get_node("Pipes").get_children():
			if pair.position.x + 72 > bird.position.x - 20:
				var top: CollisionShape2D = pair.get_child(0).get_child(0)
				target = top.position.y + top.shape.size.y / 2.0 + 175.0 / 2.0 + 25.0
				break
		if bird.position.y > target and bird.velocity > 0:
			press()
		if frame == 610:
			if main.score < 3 or main.state != main.State.PLAYING:
				return finish("flew 10 s: score %d, state %d (wanted 3+ and still playing)" % [main.score, main.state])
			phase = "fall"
	elif phase == "fall":
		if main.state == main.State.OVER:
			phase = "again"
			press()
		elif frame > 610 + 240:
			return finish("left alone the bird never ended the run")
	return false


func finish(problem: String) -> bool:
	print("AMAL_CHECK %s %s" % ["PASS" if problem.is_empty() else "FAIL", problem if not problem.is_empty() else "flew through gaps, ended on falling, started again"])
	quit(0 if problem.is_empty() else 1)
	return true
