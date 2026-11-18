# Breakout: move the paddle with the mouse, a finger, a pen or the arrow keys / A-D; click, tap or Space launches the
# ball; clear every brick; three lives. The game is simple shapes moved and drawn here, so it is easy to change.
# Touch and pen are already played: project.godot has pointing/emulate_mouse_from_touch on, so a finger arrives as a
# mouse click and drag, and a pen tablet sends mouse events - nothing to add for them.
extends Node2D

const W := 640.0
const H := 720.0
const PADDLE := Vector2(110, 16)
const PADDLE_Y := 660.0
const PADDLE_SPEED := 620.0
const BALL_R := 8.0
const BALL_SPEED := 430.0
const BRICK := Vector2(56, 22)
const COLS := 10
const ROWS := 6
const COLORS := ["ef4444", "f97316", "eab308", "22c55e", "3b82f6", "a855f7"]

enum State { READY, PLAYING, OVER, WON }
var state := State.READY
var paddle_x := W / 2.0
var ball := Vector2.ZERO
var vel := Vector2.ZERO
var bricks: Array[Rect2] = []
var brick_colors: Array[Color] = []
var score := 0
var lives := 3

@onready var score_label: Label = $HUD/Score
@onready var lives_label: Label = $HUD/Lives
@onready var message: Label = $HUD/Message


func _ready() -> void:
	reset()


func reset() -> void:
	bricks.clear()
	brick_colors.clear()
	for r in ROWS:
		for c in COLS:
			bricks.append(Rect2(Vector2(24 + c * (BRICK.x + 4), 90 + r * (BRICK.y + 6)), BRICK))
			brick_colors.append(Color(COLORS[r]))
	score = 0
	lives = 3
	update_hud()
	hold_ball()


func hold_ball() -> void:
	vel = Vector2.ZERO
	ball = Vector2(paddle_x, PADDLE_Y - BALL_R - 2)


func launch() -> void:
	if state == State.OVER or state == State.WON:
		reset()
	state = State.PLAYING
	message.hide()
	if vel == Vector2.ZERO:
		vel = Vector2(randf_range(-0.6, 0.6), -1).normalized() * BALL_SPEED


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseMotion:
		paddle_x = clampf(event.position.x, PADDLE.x / 2, W - PADDLE.x / 2)
	if event.is_action_pressed("launch") or (event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT):
		if event is InputEventMouseButton:
			paddle_x = clampf(event.position.x, PADDLE.x / 2, W - PADDLE.x / 2)
		if vel == Vector2.ZERO:
			launch()


func _physics_process(delta: float) -> void:
	paddle_x = clampf(paddle_x + Input.get_axis("move_left", "move_right") * PADDLE_SPEED * delta, PADDLE.x / 2, W - PADDLE.x / 2)
	if vel == Vector2.ZERO:
		ball = Vector2(paddle_x, PADDLE_Y - BALL_R - 2)
		queue_redraw()
		return
	ball += vel * delta
	if ball.x < BALL_R or ball.x > W - BALL_R:
		vel.x = -vel.x
		ball.x = clampf(ball.x, BALL_R, W - BALL_R)
	if ball.y < 60 + BALL_R:
		vel.y = absf(vel.y)
	var pad := Rect2(Vector2(paddle_x - PADDLE.x / 2, PADDLE_Y), PADDLE)
	if vel.y > 0 and pad.grow(BALL_R).has_point(ball):
		# where it lands on the paddle sets the angle
		var off := (ball.x - paddle_x) / (PADDLE.x / 2)
		vel = Vector2(off * 0.8, -1).normalized() * BALL_SPEED
	for i in bricks.size():
		if bricks[i].grow(BALL_R).has_point(ball):
			var b := bricks[i]
			if ball.x < b.position.x or ball.x > b.end.x: vel.x = -vel.x
			else: vel.y = -vel.y
			bricks.remove_at(i)
			brick_colors.remove_at(i)
			score += 10
			update_hud()
			if bricks.is_empty():
				end(State.WON, "You cleared it! Score %d\nClick to play again" % score)
			break
	if ball.y > H + 20:
		lives -= 1
		update_hud()
		if lives <= 0:
			end(State.OVER, "Game over - score %d\nClick to play again" % score)
		else:
			hold_ball()
	queue_redraw()


func end(s: State, text: String) -> void:
	state = s
	vel = Vector2.ZERO
	message.text = text
	message.show()


func update_hud() -> void:
	score_label.text = "Score %d" % score
	lives_label.text = "Lives %d" % lives


func _draw() -> void:
	for i in bricks.size():
		draw_rect(bricks[i], brick_colors[i])
	draw_rect(Rect2(Vector2(paddle_x - PADDLE.x / 2, PADDLE_Y), PADDLE), Color("e2e8f0"))
	draw_circle(ball, BALL_R, Color.WHITE)
