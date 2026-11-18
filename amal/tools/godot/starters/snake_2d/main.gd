# Snake: steer with the arrow keys, WASD, or a swipe (mouse, touch or pen drag); eat the red food to grow; the walls
# and your own tail end the run; steer again to play again. The board is drawn here (`_draw`), one cell at a time.
# Touch and pen are already played: project.godot has pointing/emulate_mouse_from_touch on, so a finger arrives as a
# mouse click and drag, and a pen tablet sends mouse events - nothing to add for them.
extends Node2D

const CELL := 24
const COLS := 24
const ROWS := 24
const TOP := 80                    # the board starts below the score
const SWIPE := 30.0                # pixels a drag must cover to steer

enum State { READY, PLAYING, OVER }
var state := State.READY
var snake: Array[Vector2i] = []    # head first
var dir := Vector2i.RIGHT
var next_dir := Vector2i.RIGHT
var food := Vector2i.ZERO
var score := 0
var drag_from := Vector2.ZERO
var dragging := false

@onready var timer: Timer = $StepTimer
@onready var score_label: Label = $HUD/Score
@onready var message: Label = $HUD/Message


func _ready() -> void:
	timer.timeout.connect(step)
	reset()


func reset() -> void:
	snake = [Vector2i(8, 12), Vector2i(7, 12), Vector2i(6, 12)]
	dir = Vector2i.RIGHT
	next_dir = dir
	score = 0
	score_label.text = "0"
	place_food()
	queue_redraw()


func steer(d: Vector2i) -> void:
	if state == State.OVER:
		state = State.READY
		reset()
	if state == State.READY:
		state = State.PLAYING
		message.hide()
		timer.start()
	if d != -dir:                  # never straight back into yourself
		next_dir = d


func _unhandled_input(event: InputEvent) -> void:
	for a in [["move_up", Vector2i.UP], ["move_down", Vector2i.DOWN], ["move_left", Vector2i.LEFT], ["move_right", Vector2i.RIGHT]]:
		if event.is_action_pressed(a[0]):
			steer(a[1])
			return
	# a swipe: mouse, pen (sent as mouse) and touch (emulated as mouse) the same way
	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT:
		dragging = event.pressed
		drag_from = event.position
	elif event is InputEventMouseMotion and dragging:
		var d: Vector2 = event.position - drag_from
		if d.length() >= SWIPE:
			steer(Vector2i(signi(int(d.x)), 0) if absf(d.x) > absf(d.y) else Vector2i(0, signi(int(d.y))))
			drag_from = event.position


func step() -> void:
	dir = next_dir
	var head: Vector2i = snake[0] + dir
	if head.x < 0 or head.y < 0 or head.x >= COLS or head.y >= ROWS or head in snake.slice(0, snake.size() - 1):
		return game_over()
	snake.push_front(head)
	if head == food:
		score += 1
		score_label.text = str(score)
		place_food()
	else:
		snake.pop_back()
	queue_redraw()


func place_food() -> void:
	var free: Array[Vector2i] = []
	for x in COLS:
		for y in ROWS:
			if Vector2i(x, y) not in snake:
				free.append(Vector2i(x, y))
	food = free.pick_random()


func game_over() -> void:
	state = State.OVER
	timer.stop()
	message.text = "Score %d\nSteer to play again" % score
	message.show()


func _draw() -> void:
	draw_rect(Rect2(0, TOP, COLS * CELL, ROWS * CELL), Color("1c2733"))
	draw_rect(Rect2(food.x * CELL + 3, TOP + food.y * CELL + 3, CELL - 6, CELL - 6), Color("ef4444"))
	for i in snake.size():
		var c := Color("4ade80") if i == 0 else Color("22c55e").darkened(min(0.5, i * 0.02))
		draw_rect(Rect2(snake[i].x * CELL + 1, TOP + snake[i].y * CELL + 1, CELL - 2, CELL - 2), c)
