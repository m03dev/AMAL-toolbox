# Flappy: tap, click or Space to flap through the gaps; one point per gap, a pipe or the ground ends the run.
# Main runs the game: its state, the pipes (made here, moved here), the score and the restart.
# Touch and pen are already played: project.godot has pointing/emulate_mouse_from_touch on, so a finger arrives as a
# mouse click and drag, and a pen tablet sends mouse events - nothing to add for them.
extends Node2D

const PIPE_SPEED := 170.0
const PIPE_WIDTH := 72.0
const GAP := 175.0
const GROUND_Y := 640.0

enum State { READY, PLAYING, OVER }
var state := State.READY
var score := 0
var best := 0

@onready var bird: Area2D = $Bird
@onready var pipes: Node2D = $Pipes
@onready var timer: Timer = $PipeTimer
@onready var score_label: Label = $HUD/Score
@onready var message: Label = $HUD/Message


func _ready() -> void:
	bird.hit.connect(game_over)
	timer.timeout.connect(spawn_pipes)


func _unhandled_input(event: InputEvent) -> void:
	if not event.is_action_pressed("flap"):
		return
	match state:
		State.READY:
			state = State.PLAYING
			message.hide()
			timer.start()
			spawn_pipes()
			bird.flap()
		State.PLAYING:
			bird.flap()
		State.OVER:
			get_tree().reload_current_scene()


func _process(delta: float) -> void:
	if state != State.PLAYING:
		return
	for pair in pipes.get_children():
		pair.position.x -= PIPE_SPEED * delta
		if not pair.get_meta("scored", false) and pair.position.x + PIPE_WIDTH < bird.position.x:
			pair.set_meta("scored", true)
			score += 1
			score_label.text = str(score)
		if pair.position.x < -PIPE_WIDTH - 10:
			pair.queue_free()
	if bird.position.y > GROUND_Y - 14 or bird.position.y < -40:
		game_over()


func spawn_pipes() -> void:
	var gap_center := randf_range(170.0, GROUND_Y - 170.0)
	var pair := Node2D.new()
	pair.position.x = get_viewport_rect().size.x + 20
	pair.add_child(make_pipe(0.0, gap_center - GAP / 2.0))
	pair.add_child(make_pipe(gap_center + GAP / 2.0, GROUND_Y))
	pipes.add_child(pair)


func make_pipe(top: float, bottom: float) -> Area2D:
	var pipe := Area2D.new()
	var shape := CollisionShape2D.new()
	var rect := RectangleShape2D.new()
	rect.size = Vector2(PIPE_WIDTH, bottom - top)
	shape.shape = rect
	shape.position = Vector2(PIPE_WIDTH / 2.0, (top + bottom) / 2.0)
	pipe.add_child(shape)
	var body := ColorRect.new()
	body.color = Color("4fb83f")
	body.position = Vector2(0, top)
	body.size = Vector2(PIPE_WIDTH, bottom - top)
	pipe.add_child(body)
	var lip := ColorRect.new()
	lip.color = Color("3a8f2e")
	lip.size = Vector2(PIPE_WIDTH + 10, 22)
	lip.position = Vector2(-5, bottom - 22 if top == 0.0 else top)
	pipe.add_child(lip)
	return pipe


func game_over() -> void:
	if state == State.OVER:
		return
	state = State.OVER
	timer.stop()
	bird.set_physics_process(false)
	best = maxi(best, score)
	message.text = "Score %d\nTap to play again" % score
	message.show()
