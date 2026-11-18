# Plays the Breakout starter headless: the mouse moves the paddle, a click launches, the paddle follows the ball (score
# goes up as bricks break), the arrow keys move it too, a missed ball costs a life.
extends SceneTree

var main: Node
var frame := 0
var phase := "mouse"


func _initialize() -> void:
	main = load("res://main.tscn").instantiate()
	root.add_child(main)
	current_scene = main


# a point of the game (its own 640 x 720) where the window has it: the headless window is not the game's size
func at(x: float) -> Vector2:
	return root.get_final_transform() * Vector2(x, 600)


func mouse_to(x: float) -> void:
	var m := InputEventMouseMotion.new()
	m.position = at(x)
	Input.parse_input_event(m)


func click(x: float) -> void:
	var b := InputEventMouseButton.new()
	b.button_index = MOUSE_BUTTON_LEFT
	b.pressed = true
	b.position = at(x)
	Input.parse_input_event(b)


func _physics_process(_delta: float) -> bool:
	frame += 1
	match phase:
		"mouse":
			if frame == 5: mouse_to(150)
			if frame == 8:
				if absf(main.paddle_x - 150) > 1: return finish("the mouse did not move the paddle (at %.0f)" % main.paddle_x)
				click(150)
			if frame == 12:
				if main.vel == Vector2.ZERO: return finish("a click did not launch the ball")
				phase = "play"
		"play":
			mouse_to(main.ball.x)
			if main.score >= 50:
				phase = "keys"
				Input.action_press("move_right")
				set_meta("x", main.paddle_x)
			elif frame > 1800:
				return finish("score %d after 30 s with the paddle under the ball" % main.score)
		"keys":
			if frame % 10 == 0:
				Input.action_release("move_right")
				if main.paddle_x <= get_meta("x"): return finish("the right arrow did not move the paddle")
				phase = "miss"
				mouse_to(10 if main.ball.x > 320 else 630)
				set_meta("lives", main.lives)
		"miss":
			if main.lives < get_meta("lives"):
				return finish("")
			mouse_to(10 if main.ball.x > 320 else 630)
			if frame > 4000: return finish("a missed ball cost no life")
	return false


func finish(problem: String) -> bool:
	print("AMAL_CHECK %s %s" % ["PASS" if problem.is_empty() else "FAIL", problem if not problem.is_empty() else "mouse and keys move the paddle, a click launches, bricks break, a miss costs a life"])
	quit(0 if problem.is_empty() else 1)
	return true
