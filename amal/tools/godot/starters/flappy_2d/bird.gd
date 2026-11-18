# The bird: falls, flaps up on `flap()`, tells Main when it touches a pipe (`hit`).
extends Area2D

signal hit

const GRAVITY := 1500.0
const FLAP_SPEED := -460.0
const RADIUS := 16.0

var velocity := 0.0
var falling := false   # false until the game starts: the bird floats in place


func _ready() -> void:
	area_entered.connect(func(_other: Area2D) -> void: hit.emit())


func flap() -> void:
	falling = true
	velocity = FLAP_SPEED


func _physics_process(delta: float) -> void:
	if not falling:
		position.y += sin(Time.get_ticks_msec() / 200.0) * 0.4
		return
	velocity += GRAVITY * delta
	position.y += velocity * delta
	rotation = clampf(velocity / 700.0, -0.45, 1.2)


func _draw() -> void:
	draw_circle(Vector2.ZERO, RADIUS, Color("ffd23f"))
	draw_circle(Vector2(-4, 4), 7, Color("f4a81d"))          # wing
	draw_circle(Vector2(7, -5), 5, Color.WHITE)               # eye
	draw_circle(Vector2(8, -5), 2.5, Color.BLACK)
	draw_colored_polygon(PackedVector2Array([Vector2(13, -1), Vector2(25, 3), Vector2(13, 8)]), Color("ff7b1c"))   # beak
