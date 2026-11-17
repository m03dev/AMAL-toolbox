"""creature_anim - turn a rigged creature into game-ready animation files: idle, walk, jump. Every job gets it in scripts/.

    blender --background --python-exit-code 1 --python scripts/creature_anim.py -- <rigged .fbx/.glb> <name> [seconds] [clips]

Works on any skeleton (UniRig output has no bone names to rely on): the bones are split into chains from the root and
each chain is classified by where it points - wings go out sideways and up, the tail goes back, legs go down, the neck
and head go forward/up, the rest is the body. Every move is given in WORLD terms (swing forward, flap up, wag
sideways) and turned into each bone's own axes, so it does not matter how the rig's bones are rolled. The creature
faces -Y (TRELLIS / UniRig models do).

Skin weights: the rig's own weights are kept when they pass; Blender's bone heat is tried only for a rig without good
weights of its own (never for an AdvancedSkeleton rig - the rig tool sets AMAL_NO_HEAT: Maya weights it), then limited
to 4 influences a vertex, normalised and smoothed (what game engines expect). AMAL_SKIN_WEIGHTS=<.npz> adds learned
weights for the same rig (the toolbox's skin_weights) as one more candidate; whichever deforms best is kept.

Quality gate (owner 2026-10-31: "industry standards ... this is not a workable thing, why would you give it to me"):
every clip is checked at five frames - how far the worst 1% of edges stretch (joints collapsing or tearing), how many
edges stretch past 1.6x, how much goes under the floor, how much of the mesh no bone moves. AMAL_INFO says PASS or
FAIL with the reasons, and a FAIL is never shown to the owner as a result: fix the model or the rig first.

Clips (`clips`, default "idle,walk,jump"; each loops or ends where it starts):
  idle - breathing, a slow wing flap, an S-wave down the tail, a head that looks around (`seconds` long, default 4)
  walk - a trot in place: diagonal leg pairs swing and lift, the body bobs, tail and head counter-sway (2 strides/s)
  jump - crouch, push off, tuck the legs and spread the wings in the air, land, settle (1.6 s)
  flap - hovering wing beats: full strokes (a quick downstroke, a slower upstroke, the tips trailing), the body rising
         on each downstroke, legs tucked, tail streaming (2 beats/s, loops). Only when a job asks for it (not a default); needs wings
Files, one per animation (the Unity / Unreal convention):
  renders/<name>_rig.fbx          the skinned mesh and skeleton in bind pose, no animation
  renders/<name>@<clip>.fbx       the skeleton with that one animation (the engine puts it on the rig)
  renders/<name>_<clip>.glb       mesh + that one animation (web / quick look)
  renders/<name>_<clip>.mp4       a preview of that clip
  renders/<name>_rig_report.json  the quality report; scenes/<name>_rig.blend; renders/<name>_rig.png
"""
import json, math, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bpy  # noqa: E402
from mathutils import Matrix, Quaternion, Vector  # noqa: E402
import amal_bpy as L  # noqa: E402

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
if len(args) < 2:
    raise SystemExit("usage: creature_anim.py -- rigged.fbx name [seconds] [clips]")
ROOT = os.path.dirname(HERE)
src = args[0] if os.path.isabs(args[0]) else os.path.join(ROOT, args[0])
name = args[1]
seconds = float(args[2]) if len(args) > 2 else 4.0
wanted = [c.strip() for c in (args[3] if len(args) > 3 else "idle,walk,jump").split(",") if c.strip()]
# the old 4th argument listed idle moves ("breathe,wings,tail,head,legs"): that means the idle clip
if wanted and all(c in ("breathe", "wings", "tail", "head", "legs") for c in wanted):
    wanted = ["idle"]
wanted = [c for c in wanted if c in ("idle", "walk", "jump", "flap")] or ["idle"]

L.start(os.path.join(HERE, "creature_anim.py"))
if src.lower().endswith(".fbx"):
    bpy.ops.import_scene.fbx(filepath=src, automatic_bone_orientation=True)
else:
    bpy.ops.import_scene.gltf(filepath=src)
arm = next((o for o in bpy.context.scene.objects if o.type == "ARMATURE"), None)
if arm is None:
    print("AMAL_SPEC_ERROR the file has no skeleton (rig it first)")
    raise SystemExit(2)
# the skin: meshes the skeleton deforms that are shown. A rig file also carries hidden helper meshes (AdvancedSkeleton's
# placeholders) - weight tools cannot edit a hidden object ("Cannot edit hidden object", 2026-11-03) and they are not
# the character
meshes = [o for o in bpy.context.scene.objects if o.type == "MESH" and not o.hide_get() and not o.hide_viewport]
skinned = [o for o in meshes if any(m.type == "ARMATURE" for m in o.modifiers)]
meshes = skinned or meshes
if not meshes:   # everything hidden: show the deformed ones
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH" and any(m.type == "ARMATURE" for m in o.modifiers)]
    for o in meshes:
        o.hide_set(False)
        o.hide_viewport = False


def has_image(o):
    return any(n.type == "TEX_IMAGE" and n.image is not None and (n.image.has_data or n.image.filepath or n.image.packed_file)
               for m in o.data.materials if m and m.use_nodes for n in m.node_tree.nodes)


def restore_textures():
    """A rig file can arrive without its pictures (an FBX written without embedding them: every animated clip of the
    Blender route came out untextured, 2026-11-14). The model the rig was made from still has them, and the rig keeps its
    UVs, so its materials go back on: one textured mesh -> its materials on every skin mesh, in slot order."""
    if all(has_image(o) for o in meshes):
        return
    before = set(bpy.data.objects)
    for path in [p for p in os.environ.get("AMAL_TEXTURE_SRC", "").split(os.pathsep) if p and os.path.isfile(p)]:
        try:
            bpy.ops.import_scene.gltf(filepath=path) if path.lower().endswith((".glb", ".gltf")) else bpy.ops.import_scene.fbx(filepath=path)
        except Exception as e:
            print(f"AMAL_NOTE textures: could not read {path}: {e}")
            continue
        new = [o for o in bpy.data.objects if o not in before]
        donor = next((o for o in new if o.type == "MESH" and has_image(o)), None)
        if donor is not None:
            for o in meshes:
                if has_image(o):
                    continue
                if not o.data.uv_layers:
                    print(f"AMAL_NOTE textures: {o.name} has no UVs - left untextured")
                    continue
                o.data.materials.clear()
                for m in donor.data.materials:
                    o.data.materials.append(m)
            print(f"AMAL_NOTE textures: put back from {os.path.basename(path)}")
        for o in new:
            bpy.data.objects.remove(o, do_unlink=True)
        if donor is not None:
            return
    print("AMAL_NOTE textures: the rig has no pictures and none could be put back")


restore_textures()

# the model stands on the floor at the origin
pts = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
for o in [o for o in bpy.context.scene.objects if o.parent is None]:
    o.location -= Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z))
bpy.context.view_layer.update()
size = (hi - lo).length
height = hi.z - lo.z
centre = Vector((0, 0, height / 2))

# -------------------------------------------------- chains and what they are
bones = arm.data.bones
W = arm.matrix_world


def chains_from(b, chain, out):
    chain = chain + [b]
    kids = list(b.children)
    if len(kids) == 1:
        chains_from(kids[0], chain, out)
    else:
        out.append(chain)
        for k in kids:
            chains_from(k, [], out)


chains = []
for r in [b for b in bones if b.parent is None]:
    chains_from(r, [], chains)


def head(b):
    return W @ b.head_local


def tail(b):
    return W @ b.tail_local


front = Vector((0, -1, 0))
kinds = {}


def named_kind(name):
    """What a bone is by the standard names riggers give (AdvancedSkeleton's documented names - Root_M, Hip_R, Knee_L,
    Shoulder_R, Chest_M ... - and the common game names: pelvis, thigh, calf, upperarm, forearm, clavicle); None when its
    name says nothing. A named skeleton is read by its names: AdvancedSkeleton's 79-bone biped was read by shape alone,
    its one-bone root came out "small", every chain below it followed, and nothing but the root moved (2026-11-06)."""
    n = name.lower()
    for suf in ("_m", "_r", "_l", ".r", ".l", "_left", "_right", "left", "right"):
        if n.endswith(suf):
            n = n[: -len(suf)]
            break
    def has(*w):
        return any(x in n for x in w)
    if has("finger", "thumb", "index", "middle", "ring", "pinky", "toe", "eye", "jaw", "tongue", "teeth", "end", "nub"):
        return "small"
    if has("tail"):
        return "tail"
    if has("wing"):
        return "wing"
    if has("hip", "thigh", "upleg", "knee", "calf", "shin", "ankle", "foot", "leg"):
        return "leg"
    if has("scapula", "clavicle", "shoulder", "upperarm", "elbow", "forearm", "wrist", "hand", "arm"):
        return "arm"
    if has("neck", "head"):
        return "head"
    if has("root", "pelvis", "hips", "spine", "chest", "torso", "body"):
        return "body"
    return None


for i, ch in enumerate(chains):
    known = named_kind(ch[0].name)
    if known:
        kinds[i] = known
        continue
    a, z = head(ch[0]), tail(ch[-1])
    d = z - a
    if sum((tail(b) - head(b)).length for b in ch) < size * 0.04:
        kinds[i] = "small"
        continue
    drop, run = a.z - z.z, Vector((d.x, d.y, 0)).length
    d.normalize()
    if z.z < height * 0.12 and drop > height * 0.1 and drop >= run * 0.5:
        # a limb that comes down to the floor carries the body: a leg, splayed or straight (a stylized fox's legs reach
        # forward and out - 58 degrees from straight down - and were taken for "body", so it walked on nothing, 2026-11-06)
        kinds[i] = "leg"
    elif abs(d.x) > 0.6 and z.z > centre.z * 0.8:
        kinds[i] = "wing"
    elif d.z < -0.6:
        # an upright creature's arms hang down too: a leg is a limb that reaches the floor (it carries the body), an arm
        # ends above it. Where a limb starts said nothing for a big-headed character: a chibi fox's shoulders sit under
        # half its height, its arms were rigged as front legs and trotted (2026-11-06)
        kinds[i] = "leg" if z.z < height * 0.12 else "arm"
    elif d.dot(front) < -0.5 and z.z < centre.z * 1.3:
        kinds[i] = "tail"
    elif (d.dot(front) > 0.3 or d.z > 0.6) and z.z > centre.z:
        kinds[i] = "head"
    else:
        kinds[i] = "body"
# where a chain sits in the skeleton says more than which way it points (a 57-bone auto-rig of a fox, 2026-11-06: its
# hips were swung as a tail, the spine turned like a head, ten fingers walked as arms, one ear flapped as a wing):
chain_of = {b.name: i for i, ch in enumerate(chains) for b in ch}
parent_chain = {i: chain_of.get(ch[0].parent.name) if ch[0].parent else None for i, ch in enumerate(chains)}
children = {i: [j for j, p in parent_chain.items() if p == i] for i in range(len(chains))}
for i, ch in enumerate(chains):
    if ch[0].parent is None:
        kinds[i] = "body"          # the root's chain is the hips: everything hangs from it (however short it is)
    elif kinds[i] in ("head", "body", "tail") and sum(1 for j in children[i] if kinds[j] in ("arm", "wing", "leg")) >= 2:
        kinds[i] = "body"          # the arms (or wings, or legs) branch from it: the spine, not the head
# chains are listed parents first, so a parent's kind is settled before its children's
for i in range(len(chains)):
    p = parent_chain[i]
    if p is not None and kinds[p] in ("arm", "leg", "head", "small") and kinds[i] != "small":
        kinds[i] = "small"         # fingers and toes off a hand or foot, ears and a jaw off the head: they follow it
# the bones a chain's motion is shared among: twist and roll helpers (AdvancedSkeleton's HipPart1_R, ElbowPart1_L) follow
# their limb and a scapula / clavicle starts the arm without swinging it - counted as a joint, they took the hip's swing
# and the knee's bend landed on a twist bone
# two legs and two arms: a person (a knight, a goblin) - its clips move like one
UPRIGHT = sum(1 for k in kinds.values() if k == "leg") == 2 and sum(1 for k in kinds.values() if k == "arm") >= 2


def moves(b):
    n = b.name.lower()
    return not (("part" in n and any(c.isdigit() for c in n)) or "twist" in n or "roll" in n or "scapula" in n or "clavicle" in n)


chains = [[b for b in ch if moves(b)] or ch for ch in chains]
legs = [i for i, k in kinds.items() if k == "leg"]
mid_y = sum(head(chains[i][0]).y for i in legs) / len(legs) if legs else 0.0

sc = bpy.context.scene
fps = 24
sc.render.fps = fps
bpy.context.view_layer.objects.active = arm
bpy.ops.object.mode_set(mode="POSE")
for pb in arm.pose.bones:
    pb.rotation_mode = "QUATERNION"
TAU = 2 * math.pi
W3 = W.to_3x3().inverted()
X, Y, Z = Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1))
root_bones = [b for b in bones if b.parent is None]


def turn(b, world_axis, angle):
    """A bone's rest-relative rotation for `angle` radians about a WORLD axis (+X: swings a down-pointing bone back
    toward +Y and lifts a tail; +Y: lowers a right wing / raises a left one; +Z: turns toward +X... seen from above)."""
    ax = b.matrix_local.to_3x3().inverted() @ (W3 @ world_axis)
    if ax.length < 1e-9 or abs(angle) < 1e-9:
        return Quaternion()
    return Quaternion(ax.normalized(), angle)


def pose(f, rot, lift=0.0):
    """Key frame f: rot = {bone name: [(world axis, angle), ...]}; lift = how far the whole body rises (metres)."""
    for pb in arm.pose.bones:
        q = Quaternion()
        for axis, ang in rot.get(pb.name, []):
            q = turn(pb.bone, axis, ang) @ q
        pb.rotation_quaternion = q
        pb.keyframe_insert("rotation_quaternion", frame=f)
    for b in root_bones:
        pb = arm.pose.bones[b.name]
        pb.location = b.matrix_local.to_3x3().inverted() @ (W3 @ Vector((0, 0, lift)))
        pb.keyframe_insert("location", frame=f)


def add(rot, bone, axis, ang):
    rot.setdefault(bone.name, []).append((axis, ang))


def side(b):
    return 1 if head(b).x >= 0 else -1


def share(k, depth, n):
    """How much of a chain's total turn one bone takes: a wing moves mostly at the shoulder, a neck or tail bends
    evenly (totals stay the same however many bones UniRig gave the chain)."""
    if k == "wing":
        return 0.7 if depth == 0 else 0.3 / max(1, n - 1)
    return 1.0 / n


def idle(t):
    rot = {}
    for i, ch in enumerate(chains):
        k = kinds[i]
        for depth, b in enumerate(ch):
            s, w = side(b), share(k, depth, len(ch))
            if k == "wing":
                add(rot, b, Y, -s * w * 0.45 * math.sin(TAU * 2 * t - depth * 0.5))
            elif k == "tail":
                add(rot, b, Z, w * 0.7 * math.sin(TAU * t - depth * 0.7))
                add(rot, b, X, w * 0.2 * math.sin(TAU * t - depth * 0.6))
            elif k == "head":
                # a person standing glances, a creature looks about: a 20-degree sweep on a knight pressed its helmet's
                # chin into its breastplate and the idle tore there (Jaw_M + Spine1_M, 2026-11-14)
                turn_, nod = (0.12, 0.05) if UPRIGHT else (0.35, 0.12)
                add(rot, b, Z, w * turn_ * math.sin(TAU * t))
                add(rot, b, X, w * nod * math.sin(TAU * t + 0.4))
            elif k == "body":
                add(rot, b, X, w * 0.04 * math.sin(TAU * 2 * t))
    return rot, height * 0.006 * math.sin(TAU * 2 * t)


def walk(t):
    """t 0..1 = one stride; two diagonal pairs half a stride apart (a trot)."""
    rot = {}
    for i, ch in enumerate(chains):
        k = kinds[i]
        for depth, b in enumerate(ch):
            s, w = side(b), share(k, depth, len(ch))
            if k == "leg":
                is_front = head(ch[0]).y < mid_y
                ph = TAU * (t + (0.0 if (is_front == (s > 0)) else 0.5))
                swing = math.sin(ph)                           # +1 = foot forward
                up = max(0.0, math.cos(ph))                    # lifting while it swings forward
                if depth == 0:
                    add(rot, b, X, -0.42 * swing)
                elif depth == 1:
                    add(rot, b, X, (0.55 if is_front else -0.55) * up)
                else:
                    add(rot, b, X, 0.25 * up * (1 if is_front else -1))
            elif k == "arm":
                if depth == 0:
                    add(rot, b, X, 0.25 * math.sin(TAU * t + (math.pi if s > 0 else 0.0)))
            elif k == "tail":
                add(rot, b, Z, w * 0.5 * math.sin(TAU * t - depth * 0.6))
            elif k == "head":
                add(rot, b, X, w * 0.14 * math.sin(TAU * 2 * t + 0.6))
            elif k == "wing":
                add(rot, b, Y, -s * w * 0.15 * math.sin(TAU * 2 * t))   # folded, a little bounce
            elif k == "body":
                add(rot, b, Z, w * 0.06 * math.sin(TAU * t))
    return rot, height * 0.035 * abs(math.sin(TAU * t))


def jump(t):
    """0-.25 crouch, .25-.35 push off, .35-.75 in the air, .75-.85 land, .85-1 settle."""
    def ease(x):
        return x * x * (3 - 2 * x)
    if t < 0.25:
        crouch, lift = ease(t / 0.25), 0.0
    elif t < 0.35:
        crouch, lift = 1 - ease((t - 0.25) / 0.1), 0.0
    elif t < 0.75:
        u = (t - 0.35) / 0.4
        crouch, lift = 0.0, 4 * u * (1 - u)
    elif t < 0.85:
        crouch, lift = ease((t - 0.75) / 0.1) * 0.8, 0.0
    else:
        crouch, lift = 0.8 * (1 - ease((t - 0.85) / 0.15)), 0.0
    air = lift
    rot = {}
    for i, ch in enumerate(chains):
        k = kinds[i]
        for depth, b in enumerate(ch):
            s, w = side(b), share(k, depth, len(ch))
            if k == "leg":
                is_front = head(ch[0]).y < mid_y
                bend = crouch * 0.5 + air * 0.6              # crouch on the ground, tuck in the air
                if depth == 0:
                    add(rot, b, X, -bend * (1 if is_front else -0.6))
                elif depth == 1:
                    add(rot, b, X, bend * 1.4 * (1 if is_front else -1))
            elif k == "wing":
                flap = math.sin(TAU * 2 * max(0.0, t - 0.3)) if 0.3 < t < 0.8 else 0.0
                add(rot, b, Y, -s * w * (0.8 * air + 0.35 * flap - 0.15 * crouch))
            elif k == "arm":
                if depth == 0:
                    add(rot, b, X, -0.35 * air + 0.1 * crouch)
            elif k == "tail":
                add(rot, b, X, w * (0.5 * air - 0.25 * crouch))
            elif k == "head":
                add(rot, b, X, w * (-0.2 * air + 0.2 * crouch))
            elif k == "body":
                add(rot, b, X, w * (0.12 * crouch - 0.08 * air))
    return rot, -height * 0.08 * crouch + height * 0.45 * lift


def flap(t):
    """t 0..1 = one wing beat of a hovering flight cycle: downstroke 0-.4 (fast), upstroke .4-1 (slower). Bones further
    out lag the shoulder; legs and tail swing a little after the body; the head stays level while the body pitches.
    (Folding the wing on the upstroke stretched a generated membrane 2-3x, 2026-11-02: left out.)"""
    def stroke(u):
        u %= 1.0
        # +1 = wings up, -1 = wings down
        return math.cos(math.pi * u / 0.4) if u < 0.4 else -math.cos(math.pi * (u - 0.4) / 0.6)

    rot = {}
    pitch = 0.07 * stroke(t - 0.1)                            # the body's nod with each beat
    for i, ch in enumerate(chains):
        k = kinds[i]
        for depth, b in enumerate(ch):
            s, w = side(b), share(k, depth, len(ch))
            if k == "wing":
                lag = t - depth * 0.08
                add(rot, b, Y, -s * w * (0.2 + 0.8 * stroke(lag)))
            elif k == "leg":
                is_front = head(ch[0]).y < mid_y
                dangle = 0.12 * stroke(t - 0.3)                  # legs hang and swing after the body
                if depth == 0:
                    add(rot, b, X, -0.35 * (1 if is_front else -0.6) + dangle)
                elif depth == 1:
                    add(rot, b, X, 0.6 * (1 if is_front else -1) + dangle * 0.6)
            elif k == "arm":
                if depth == 0:
                    add(rot, b, X, -0.3 + 0.08 * stroke(t - 0.3))
            elif k == "tail":
                add(rot, b, X, w * (0.25 + 0.16 * stroke(t - 0.25 - depth * 0.1)))
                add(rot, b, Z, w * 0.12 * math.sin(TAU * t - depth * 0.6))
            elif k == "head":
                add(rot, b, X, -w * pitch)                      # the head stays level
            elif k == "body":
                add(rot, b, X, w * pitch)
    # the body rises while the wings beat down, sinks a little on the way up
    return rot, height * (0.3 - 0.05 * stroke(t - 0.2))


def plant_feet(act, n, clip):
    """Feet that stay on the ground, as in shipped games: each leg reaches for a target that is planted while the body
    moves over it (stance) and lifts and swings forward (swing) - a trot, diagonal pairs half a stride apart; for idle
    the targets stay where the feet stand. Blender's IK bends the knees; the result is baked into plain keyframes."""
    legs_ch = [chains[i] for i in legs if len(chains[i]) >= 3]
    if not legs_ch:
        return
    fwd = front                                           # the way the creature faces (see front above)
    targets, cons = [], []
    for ch in legs_ch:
        foot = ch[-2] if len(ch) >= 4 else ch[-1]          # the bone whose tail is on the ground (ankle -> ball)
        k = ch.index(foot) + 1
        tip = tail(foot)
        leg_len = sum((tail(b) - head(b)).length for b in ch[:k])
        e = bpy.data.objects.new(f"AMAL_foot_{foot.name}", None)
        sc.collection.objects.link(e)
        is_front = head(ch[0]).y < mid_y
        lag = 0.0 if (is_front == (side(ch[0]) > 0)) else 0.5
        for f in range(0, n + 1):
            if clip == "walk":
                u = ((f / n) * cycles[clip] + lag) % 1.0
                stride, lift = leg_len * 0.45, leg_len * 0.22
                if u < 0.6:                                   # planted: the body passes over it
                    along, up = stride * (0.5 - u / 0.6), 0.0
                else:                                         # lifted and carried forward
                    v = (u - 0.6) / 0.4
                    along, up = stride * (-0.5 + v), lift * math.sin(math.pi * v)
            else:
                along, up = 0.0, 0.0
            # each foot is planted where it stands in the model: the model already stands on the floor (its lowest point
            # is at 0), and the bone's tip is above the sole - pulling the tip down to 0 pushed a fox's paws through the
            # floor (0.9% of the mesh in idle, 2026-11-06); a foot held up (front claws of a leaping pose) keeps its
            # height too - pulling it down stretched the shoulders 2.1x (2026-11-02)
            base_z = tip.z
            e.location = Vector((tip.x, tip.y, base_z)) + fwd * along + Vector((0, 0, up))
            e.keyframe_insert("location", frame=f + 1)
        c = arm.pose.bones[foot.name].constraints.new("IK")
        c.target, c.chain_count, c.use_tail = e, k, True
        targets.append(e)
        cons.append((foot.name, c))
    arm.animation_data.action = act
    bpy.ops.object.mode_set(mode="POSE")
    bpy.ops.pose.select_all(action="SELECT")
    bpy.ops.nla.bake(frame_start=1, frame_end=n + 1, only_selected=False, visual_keying=True, clear_constraints=False,
                     use_current_action=True, bake_types={"POSE"})
    for name, c in cons:
        arm.pose.bones[name].constraints.remove(c)
    for e in targets:
        bpy.data.objects.remove(e)
    print(f"{clip}: feet planted with IK on {len(cons)} legs")


def ground_clip(act, n, clip):
    """No frame goes through the floor: where the lowest point of the skin is under it, the whole body is raised by
    exactly that much on that frame (a toe that pitches down in a stride, a paw below its bone). Root bones only, so the
    pose is kept; a frame already on or above the floor is left as it is."""
    arm.animation_data.action = act
    raised = 0
    for f in range(1, n + 2):
        sc.frame_set(f)
        dg = bpy.context.evaluated_depsgraph_get()
        low = math.inf
        for o in meshes:
            e = o.evaluated_get(dg).to_mesh()
            mw = o.matrix_world
            low = min(low, min(((mw @ v.co).z for v in e.vertices), default=math.inf))
            o.evaluated_get(dg).to_mesh_clear()
        if low >= -1e-4 * height or low == math.inf:
            continue
        for b in root_bones:
            pb = arm.pose.bones[b.name]
            pb.location = pb.location + b.matrix_local.to_3x3().inverted() @ (W3 @ Vector((0, 0, -low)))
            pb.keyframe_insert("location", frame=f)
        raised += 1
    sc.frame_set(1)
    if raised:
        print(f"{clip}: raised the body on {raised} of {n + 1} frames so nothing goes under the floor")


# an upright character's arms rest level (a T-pose, how it is modelled and rigged) and stayed so in every clip - a
# goblin walked with its arms straight out (2026-11-12). In every clip they are brought down from the shoulder to the
# angle a relaxed arm holds; arms already hanging are left. AMAL_ARMS_DOWN sets that angle (degrees below level, 0 off)
ARMS_DOWN = math.radians(float(os.environ.get("AMAL_ARMS_DOWN", "30") or 0))
arm_drop = {}
if ARMS_DOWN > 0 and UPRIGHT:
    for i, ch in enumerate(chains):
        if kinds[i] != "arm" or not ch:
            continue
        # where the arm points: shoulder joint to the joint two down its main line (the wrist on AdvancedSkeleton's
        # Shoulder -> Elbow -> Wrist, past the twist bones). A bone's tail says nothing: FBX has none, and Blender's
        # guess at it decided whether a level arm counted as level
        x = ch[-1]
        for _ in range(2):
            kids = list(x.children)
            if not kids:
                break
            x = max(kids, key=lambda c: len(c.children_recursive))
        d = (head(x) if x is not ch[-1] else tail(ch[-1])) - head(ch[0])
        elev = math.atan2(d.z, math.hypot(d.x, d.y))       # 0 = level, negative = hanging
        if elev > -ARMS_DOWN + math.radians(10):
            arm_drop[ch[0].name] = (ch[0], elev + ARMS_DOWN)
    if arm_drop:
        print("arms: brought down %s from level in every clip (%d arm(s))" % (
            ", ".join("%d deg" % round(math.degrees(a)) for _, a in arm_drop.values()), len(arm_drop)))


def arms_rest(rot):
    for name, (b, ang) in arm_drop.items():
        # about world +Y a point at +X goes down for a positive angle, one at -X for a negative one
        rot.setdefault(name, []).insert(0, (Y, side(b) * ang))
    return rot


makers = {"idle": (idle, max(1.0, seconds)), "walk": (walk, 2.0), "jump": (jump, 1.6), "flap": (flap, 3.0)}
cycles = {"idle": 1, "walk": 2, "jump": 1, "flap": 3}       # strides / beats per clip
if "flap" in wanted and "wing" not in kinds.values():
    print("flap: this rig has no wing chains - no flap clip")
    wanted = [c for c in wanted if c != "flap"] or ["idle"]
arm.animation_data_create()
actions = {}
for clip in wanted:
    fn, secs = makers[clip]
    n = max(12, int(round(secs * fps)))
    act = bpy.data.actions.new(clip)
    act.use_fake_user = True
    arm.animation_data.action = act
    for f in range(0, n + 1):
        t = (f / n) * cycles[clip] % 1.0 if f < n else 0.0
        rot, lift = fn(t)
        pose(f + 1, arms_rest(rot), lift)
    actions[clip] = (act, n)
    if clip in ("walk", "idle"):
        plant_feet(act, n, clip)
        ground_clip(act, n, clip)
arm.animation_data.action = None
bpy.ops.object.mode_set(mode="OBJECT")
REN = os.path.join(ROOT, "renders")
os.makedirs(REN, exist_ok=True)

# -------------------------------------------------- skin weights: the better of the rig's own and Blender's bone heat
roots = {b.name for b in root_bones}


def deform_check(clip_list):
    """How badly the mesh deforms, against the bind pose, at five frames of each clip:
    p999 / max = the stretch of the worst 0.1% of edges and the very worst one (1.0 = perfect; joints that collapse or
    tear show up here), flips = share of faces turned inside out (a collapsed knee), floor = share of vertices pushed
    under the floor. Also the share of vertices with no weights at all (they would not move) and the share that only
    rides on a root bone (a tail or legs without bones of their own)."""
    def grab(rest=None):
        dg = bpy.context.evaluated_depsgraph_get()
        out = []
        for k, o in enumerate(meshes):
            e = o.evaluated_get(dg).to_mesh()
            co = [o.matrix_world @ v.co for v in e.vertices]
            if rest is None:
                # the edges of the triangles an engine draws, not only the polygon outlines: a large flat cap hid a 13x
                # stretch across its middle and the rig passed with a visible hole in the throat (2026-11-02)
                e.calc_loop_triangles()
                tri = sorted({(min(a, b), max(a, b)) for t in e.loop_triangles for a, b in zip(t.vertices, (t.vertices[1], t.vertices[2], t.vertices[0]))})
                polys = [tuple(p.vertices[:3]) for p in e.polygons]
            else:
                # posed, the same triangles as at rest: triangulated again, a bent quad splits along its other diagonal,
                # the edge list shifts by one and every length after it is compared with another edge's - the gate read
                # 7-15x tears on edges whose two ends had the same weights (2026-11-07)
                _, polys, tri = rest[k]
            out.append((co, polys, tri))
            o.evaluated_get(dg).to_mesh_clear()
        return out

    def nrm(co, p):
        return (co[p[1]] - co[p[0]]).cross(co[p[2]] - co[p[0]])
    # the bone that drives each vertex most (to say where a tear is)
    owner = []
    # and the bone far away in the skeleton (5+ steps: an arm on a leg, a wing on a shoulder) that also pulls it: weight
    # from such a bone means the two parts touch in the model - the mesh is one surface there and tears when they move
    # apart, whatever the weights (owner 2026-11-01: say what really fails instead of patching weights for hours)
    chain = {b.name: [x.name for x in reversed(b.parent_recursive)] + [b.name] for b in arm.data.bones}

    def hops(a, b):
        A, B = chain.get(a, [a]), chain.get(b, [b])
        k = 0
        while k < min(len(A), len(B)) and A[k] == B[k]:
            k += 1
        return len(A) - k + len(B) - k
    far = []
    for o in meshes:
        names = {g.index: g.name for g in o.vertex_groups}
        owner.append([names.get(max(v.groups, key=lambda g: g.weight).group, "?") if len(v.groups) else "(no weights)" for v in o.data.vertices])
        row = []
        for v, d in zip(o.data.vertices, owner[-1]):
            fb = [names[g.group] for g in v.groups if g.weight > 0.05 and g.group in names and hops(d, names[g.group]) >= 5]
            row.append(fb[0] if fb else None)
        far.append(row)
    arm.data.pose_position = "REST"
    bpy.context.view_layer.update()
    rest = grab()
    rest_n = [[nrm(co, p) for p in polys] for co, polys, _ in rest]
    # an edge shorter than half the typical one counts as half the typical one: a sliver the mesh reduction left (a third
    # of the median) that stretched 3.6x in a tucked armpit was still only 1.2 typical edges long - no visible tear - and
    # failed the rig, while a real tear (a 13x spike at the wing root) still reads 13x (2026-11-02)
    rest_l = []
    for co, _, edges in rest:
        ls = [(co[a] - co[b]).length for a, b in edges]
        floor = max(sorted(ls)[len(ls) // 2] * 0.5, 1e-7) if ls else 1e-7
        rest_l.append((ls, floor))
    arm.data.pose_position = "POSE"
    out = {}
    for clip in clip_list:
        act, n = actions[clip]
        arm.animation_data.action = act
        ratios, flips, nf, under, nv, moved = [], 0, 0, 0, 0, 0.0
        bad = {}   # bone -> how many over-stretched edges sit on vertices it mostly drives: WHERE it tears
        fused = {}  # (bone, far bone) -> torn edges on vertices pulled by both
        for f in sorted({n // 4 + 1, n // 2 + 1, 3 * n // 4 + 1, n // 8 + 1, 5 * n // 8 + 1}):
            sc.frame_set(f)
            for k, (co, polys, edges) in enumerate(grab(rest)):
                rco = rest[k][0]
                moved = max(moved, max((c - r).length for c, r in zip(co, rco)))
                ls, floor = rest_l[k]
                rs = [max(x, 1 / max(x, 1e-6)) for x in (max((co[a] - co[b]).length, floor) / max(l, floor) for (a, b), l in zip(edges, ls))]
                ratios += rs
                for (a, b), x in zip(edges, rs):
                    if x > 1.6:
                        g = owner[k][a]
                        bad[g] = bad.get(g, 0) + 1
                        if far[k][a]:
                            key = tuple(sorted((g, far[k][a])))
                            fused[key] = fused.get(key, 0) + 1
                flips += sum(1 for p, n0 in zip(polys, rest_n[k]) if n0.length > 1e-12 and nrm(co, p).dot(n0) < 0)
                nf += len(polys)
                if clip not in ("jump", "flap"):
                    under += sum(1 for c in co if c.z < -0.02 * height)
                nv += len(co)
        ratios.sort()
        tot = sum(bad.values())
        where = ", ".join(f"{g} {c * 100 // max(tot, 1)}%" for g, c in sorted(bad.items(), key=lambda x: -x[1])[:4])
        nb = sum(bad.values())
        touch = [f"{a} + {b}" for (a, b), c in sorted(fused.items(), key=lambda x: -x[1]) if c >= max(5, nb * 0.1)][:3]
        # how many edges are past the worst-edge limit, of how many measured: three slivers at a mouth corner and a torn
        # shoulder both read "worst 4x" - the count tells them apart (two rigs failed on the worst edge alone, 2026-11-10)
        over = sum(1 for x in ratios if x > 3.0)
        out[clip] = {"where": where, "touching": touch, "p999": round(ratios[int(len(ratios) * 0.999)], 2), "max": round(ratios[-1], 2),
                     "over": over, "edges": len(ratios),
                     "flips": round(flips / max(1, nf), 4), "floor": round(under / max(1, nv), 4), "moved": round(moved / max(height, 1e-6), 3)}
    arm.animation_data.action = None
    sc.frame_set(1)
    total = stiff = none = 0
    for o in meshes:
        names = {g.index: g.name for g in o.vertex_groups}
        for v in o.data.vertices:
            ws = [g for g in v.groups if g.weight > 1e-4 and g.group in names]
            total += 1
            if not ws:
                none += 1
            elif names[max(ws, key=lambda g: g.weight).group] in roots:
                stiff += 1
    return out, round(stiff / max(1, total), 3), round(none / max(1, total), 3)


def score(res, none):
    """Lower is better; a mesh that does not follow the bones at all is the worst."""
    if none > 0.05 or max(r["moved"] for r in res.values()) < 0.01:
        return 1e9
    return max(r["p999"] for r in res.values()) + 200 * max(r["flips"] for r in res.values()) + 20 * none


def tidy_weights(repeat=2):
    """Game-engine rules: at most 4 influences a vertex, normalised, lightly smoothed (`repeat` smoothing passes)."""
    for o in meshes:
        bpy.ops.object.select_all(action="DESELECT")
        o.select_set(True)
        bpy.context.view_layer.objects.active = o
        if not o.vertex_groups:
            continue
        bpy.ops.object.mode_set(mode="WEIGHT_PAINT")
        try:
            bpy.ops.object.vertex_group_smooth(group_select_mode="ALL", factor=0.5, repeat=repeat)
            bpy.ops.object.vertex_group_limit_total(group_select_mode="ALL", limit=4)
            bpy.ops.object.vertex_group_normalize_all(group_select_mode="ALL", lock_active=False)
        except Exception as e:  # noqa: BLE001
            print("weights: tidy skipped:", e)
        bpy.ops.object.mode_set(mode="OBJECT")


test_clips = ([c for c in ("walk", "jump", "idle") if c in actions] or list(actions))[:2]   # any clips made (a flap-only request had none and crashed)


def snapshot():
    """The meshes' weights as they are now (each candidate's, kept so the one that scores best can be put back)."""
    out = {}
    for o in meshes:
        names = {g.index: g.name for g in o.vertex_groups}
        groups = {n: [] for n in names.values()}
        for v in o.data.vertices:
            for g in v.groups:
                if g.group in names:
                    groups[names[g.group]].append((v.index, g.weight))
        out[o.name] = groups
    return out


def restore(snap):
    for o in meshes:
        o.vertex_groups.clear()
        for gname, vals in snap[o.name].items():
            g = o.vertex_groups.new(name=gname)
            for vi, w in vals:
                g.add([vi], w, "REPLACE")


def learned_weights(path):
    """Weights made elsewhere for this same rig file (the toolbox's skin_weights: SkinTokens, a learned skinning model):
    per vertex up to 4 joints by name, matched by mesh name and vertex index. A joint this skeleton does not have gives
    its share to the others. False when none of its meshes is here."""
    import numpy as np
    d = np.load(path)
    names = [str(x) for x in d["joint_names"]]
    here = {b.name for b in arm.data.bones}
    start, done = 0, 0
    for mname, n in zip(d["mesh_names"], d["mesh_counts"]):
        mname, n = str(mname), int(n)
        rows = slice(start, start + n)
        start += n
        o = next((m for m in meshes if m.name == mname), None)
        if o is None or len(o.data.vertices) != n:
            print(f"weights: learned weights skip {mname} ({'not here' if o is None else 'its vertex count differs'})")
            continue
        for g in [g for g in o.vertex_groups if g.name in here]:
            o.vertex_groups.remove(g)
        vg = {}
        for vi, (ii, ww) in enumerate(zip(d["idx"][rows], d["w"][rows])):
            got = {}
            for j, x in zip(ii, ww):
                if x > 1e-4 and names[int(j)] in here:
                    got[names[int(j)]] = got.get(names[int(j)], 0.0) + float(x)
            tot = sum(got.values())
            for bn, x in got.items():
                if bn not in vg:
                    vg[bn] = o.vertex_groups.new(name=bn)
                vg[bn].add([vi], x / tot, "REPLACE")
        done += 1
    return done > 0


def is_helper(name):
    """A twist / roll helper bone (AdvancedSkeleton's ElbowPart1_R, ShoulderPart2_L; other rigs' Twist / Roll bones)."""
    n = name.lower()
    return "part" in n and any(c.isdigit() for c in n) or "twist" in n or "roll" in n


def heat_weights():
    """Blender's bone heat, solved on a clean voxel-remeshed copy (heat fails on the open, self-touching meshes image-to-3D
    makes) and carried over to the real mesh by nearest surface - the usual way riggers skin a messy scan."""
    for o in meshes:
        bpy.ops.object.select_all(action="DESELECT")
        o.select_set(True)
        bpy.context.view_layer.objects.active = o
        proxy = o.copy()
        proxy.data = o.data.copy()
        sc.collection.objects.link(proxy)
        for m in list(proxy.modifiers):
            proxy.modifiers.remove(m)
        proxy.vertex_groups.clear()
        proxy.parent = None
        proxy.matrix_world = o.matrix_world.copy()
        r = proxy.modifiers.new("Voxel", "REMESH")
        r.mode = "VOXEL"
        # the voxel size is in the mesh's own units: an AdvancedSkeleton FBX comes in centimetres under a 0.01 scale, and
        # a size meant in metres made a remesh 100 times too fine that ran out of memory without a word (2026-11-03)
        r.voxel_size = r_size = max(height / 100, 1e-4) / max(1e-6, max(proxy.matrix_world.to_scale()))
        bpy.ops.object.select_all(action="DESELECT")
        proxy.select_set(True)
        bpy.context.view_layer.objects.active = proxy
        bpy.ops.object.modifier_apply(modifier=r.name)
        # heat's memory grows with vertices x bones: a proxy bigger than the model itself (60k faces against a 15k
        # vertex dragon) ran Blender out of memory with ~100 bones (Windows: exit 0xc0000409, no message)
        # (the twist helpers sit the solve out, so they do not count; a 114-bone dragon with a 12k-face proxy still ran a
        # 7 GB machine out of memory, 2026-11-03: about a million face-bones is the budget)
        heat_bones = sum(1 for b in arm.data.bones if b.use_deform and not (deforming > 150 and is_helper(b.name)))
        cap = int(min(40000, max(6000, min(len(o.data.polygons) * 0.8, 1_000_000 / max(1, heat_bones)))))
        if len(proxy.data.polygons) > cap:
            # coarser voxels, not a decimate: a decimated proxy's ragged triangles made heat fail on every bone
            # (0 of 8144 vertices weighted; the same proxy remeshed and not decimated: all of them, 2026-11-03)
            coarser = r_size * (len(proxy.data.polygons) / cap) ** 0.5 * 1.05
            proxy.data = o.data.copy()
            r = proxy.modifiers.new("Voxel", "REMESH")
            r.mode = "VOXEL"
            r.voxel_size = coarser
            bpy.ops.object.modifier_apply(modifier=r.name)
        bpy.ops.object.select_all(action="DESELECT")
        proxy.select_set(True)
        arm.select_set(True)
        bpy.context.view_layer.objects.active = arm
        # heat over every twist helper (AdvancedSkeleton's ...Part1/Part2 bones) ran past the bone budget and was never
        # tried, so a tearing rig kept its own weights (158 bones, 2026-11-03): the helpers sit out the heat solve and
        # the limb bones they ride on take their share
        helpers = [b for b in arm.data.bones if b.use_deform and is_helper(b.name)] if deforming > 150 else []
        for b in helpers:
            b.use_deform = False
        # bone heat fails on small models ("failed to find solution", every vertex left unweighted): a 0.65 m dragon in
        # an AdvancedSkeleton FBX got no weights at all, and the same at 65 units got every one (2026-11-03). It is solved
        # at about 50 units tall, then the rig and the proxy go back to their size.
        k = 50.0 / max(height, 1e-6)
        saved = (arm.matrix_world.copy(), proxy.matrix_world.copy())
        S = Matrix.Scale(k, 4)
        arm.matrix_world = S @ saved[0]
        proxy.matrix_world = S @ saved[1]
        pose_was = arm.data.pose_position
        arm.data.pose_position = "REST"   # heat is solved on the rest pose, not on whatever frame a clip left it in
        bpy.context.view_layer.update()
        try:
            bpy.ops.object.parent_set(type="ARMATURE_AUTO", keep_transform=True)
        finally:
            for b in helpers:
                b.use_deform = True
            proxy.parent = None
            for m in [m for m in proxy.modifiers if m.type == "ARMATURE"]:
                proxy.modifiers.remove(m)
            arm.matrix_world = saved[0]
            proxy.matrix_world = saved[1]
            arm.data.pose_position = pose_was
            bpy.context.view_layer.update()
        if not any(len(g.name) for g in proxy.vertex_groups):
            bpy.data.objects.remove(proxy)
            return False
        o.vertex_groups.clear()
        for g in proxy.vertex_groups:
            o.vertex_groups.new(name=g.name)
        dt = o.modifiers.new("Weights", "DATA_TRANSFER")
        dt.object = proxy
        dt.use_vert_data = True
        dt.data_types_verts = {"VGROUP_WEIGHTS"}
        dt.vert_mapping = "POLYINTERP_NEAREST"
        dt.layers_vgroup_select_src = "ALL"
        dt.layers_vgroup_select_dst = "NAME"
        bpy.ops.object.select_all(action="DESELECT")
        o.select_set(True)
        bpy.context.view_layer.objects.active = o
        while o.modifiers[0] != dt:
            bpy.ops.object.modifier_move_up(modifier=dt.name)
        bpy.ops.object.modifier_apply(modifier=dt.name)
        bpy.data.objects.remove(proxy)
    return True


def gate(res_all, stiff, none):
    """The quality gate: what is wrong with a rig's deformation (empty = PASS)."""
    problems = []
    for clip, r in res_all.items():
        if r["moved"] < 0.01:
            problems.append(f"{clip}: the mesh does not follow the skeleton")
        if r["p999"] > 1.6 or r["max"] > 3.0:
            problems.append(f"{clip}: joints tear or collapse (worst 0.1% of edges stretch {r['p999']}x, worst {r['max']}x; limits 1.6 / 3.0"
                            + (f"; {r['over']} of {r['edges']} measured edges are past 3x" if r.get("edges") else "") + ")"
                            + (f" - mostly on vertices driven by {r['where']}" if r.get("where") else ""))
            if r.get("touching"):
                problems.append(f"{clip}: the tear is where parts touch in the model ({'; '.join(r['touching'])}): the mesh is one "
                                "surface there, so no rig or weights can pull them apart cleanly - make the model again with "
                                "the limbs, wings and tail clear of the body (an A-pose)")
        if r["flips"] > 0.003:
            problems.append(f"{clip}: {r['flips'] * 100:.1f}% of faces fold inside out (collapsed joints; limit 0.3%)")
        if r["floor"] > 0.002:
            problems.append(f"{clip}: {r['floor'] * 100:.1f}% of the mesh goes under the floor")
    if stiff > 0.12:
        problems.append(f"{stiff * 100:.0f}% of the mesh has no bone of its own (a tail or legs without bones; limit 12%)")
    if none > 0.01:
        problems.append(f"{none * 100:.0f}% of the mesh has no skin weights at all")
    return problems


tidy_weights()
rig_res, rig_stiff, rig_none = deform_check(test_clips)
candidates = [("rig", rig_res, rig_stiff, rig_none)]
snaps = {"rig": snapshot()}
deforming = sum(1 for b in arm.data.bones if b.use_deform)
# Bone heat is only a second opinion for weights that fail: a production rig's own weights (AdvancedSkeleton's
# geodesic voxel bind) that already pass are kept, and heat over hundreds of bones (279 in an AdvancedSkeleton
# rig, with its twist helpers) ran Blender out of memory without a word.
rig_problems = gate(rig_res, rig_stiff, rig_none)
print("weights: the rig's own -", "; ".join(rig_problems) or "pass")
main_bones = sum(1 for b in arm.data.bones if b.use_deform and not is_helper(b.name))
need_heat = bool(rig_problems) and main_bones <= 150 and os.environ.get("AMAL_NO_HEAT") != "1"
if not need_heat:
    print("weights: keeping the rig's own" + ("" if main_bones <= 150 else f" ({main_bones} deforming bones besides twist helpers: too many for bone heat)"))
# the rig's own weights smoothed harder - what a rigger does where a learned or automatic skin creases at the joints
# (Maya's Smooth Skin Weights): one more candidate, kept only if it deforms better (SkinTokens' dragon rig stretched
# 1.86x at its joints against a 1.6 limit, 2026-11-04)
if rig_problems:
    try:
        tidy_weights(repeat=8)
        candidates.append(("rig, smoothed", *deform_check(test_clips)))
        snaps["rig, smoothed"] = snapshot()
        restore(snaps["rig"])
    except Exception as e:  # noqa: BLE001
        print("weights: smoothing more failed:", e)
try:
    if need_heat and heat_weights():
        tidy_weights()
        h = deform_check(test_clips)
        candidates.append(("bone heat", *h))
        snaps["bone heat"] = snapshot()
except Exception as e:  # noqa: BLE001 - keep the rig's own weights
    print("weights: bone heat failed:", e)
# learned weights (AMAL_SKIN_WEIGHTS: the rig tool asks the toolbox's skin_weights for them when this rig's weights failed
# the gate) are one more candidate, measured the same way: they are kept only if they deform better
learned = os.environ.get("AMAL_SKIN_WEIGHTS", "")
learned = learned if not learned or os.path.isabs(learned) else os.path.join(ROOT, learned)
if learned and os.path.isfile(learned):
    try:
        if learned_weights(learned):
            tidy_weights()
            candidates.append(("learned", *deform_check(test_clips)))
            snaps["learned"] = snapshot()
    except Exception as e:  # noqa: BLE001 - keep the others
        print("weights: learned weights failed:", e)
for c in candidates:
    print("weights:", c[0], "score", round(score(c[1], c[3]), 3), json.dumps(c[1]), "stiff", c[2], "unweighted", c[3])
weights = min(candidates, key=lambda c: score(c[1], c[3]))[0]
restore(snaps[weights])


NEAR = 2   # bones a vertex may blend: its own strongest and those up to two steps from it (as advanced_skeleton.limit_weights)


def separate_fused():
    """Each patch of skin follows one limb, and parts that are one surface only because they touched in the model (a
    claw on the throat, a folded wing on the chest) are cut apart and each side closed, as a modeller would before
    rigging. Smoothing - Maya's seam pass, then tidy_weights - spreads weight across such a contact (a wing-root vertex
    took 26% from a finger four bones away) and nothing was cut, so the skin there stretched 4-13x whenever the wing
    moved (2026-11-02). So, in one place and after all smoothing: each vertex keeps only bones within NEAR steps of its
    strongest, is smoothed with its neighbours under the same rule (no single row takes a whole change), keeps at most
    four, and a face whose corners follow bones more than NEAR steps apart is a contact and is cut."""
    import bmesh
    import numpy as np
    bones = [b.name for b in arm.data.bones]
    chain = {b.name: [x.name for x in reversed(b.parent_recursive)] + [b.name] for b in arm.data.bones}

    def hops(a, b):
        A, B = chain.get(a, [a]), chain.get(b, [b])
        k = 0
        while k < min(len(A), len(B)) and A[k] == B[k]:
            k += 1
        return len(A) - k + len(B) - k
    near = np.array([[hops(a, b) <= NEAR for b in bones] for a in bones])
    col = {n: i for i, n in enumerate(bones)}
    total = moved = 0
    for o in meshes:
        groups = {g.index: g.name for g in o.vertex_groups if g.name in col}
        nv = len(o.data.vertices)
        w = np.zeros((nv, len(bones)))
        for v in o.data.vertices:
            for g in v.groups:
                if g.group in groups:
                    w[v.index, col[groups[g.group]]] = g.weight
        weighted = w.sum(1) > 1e-6
        dom = w.argmax(1)
        before = w.copy()
        ends = np.array([e.vertices[:] for e in o.data.edges], dtype=np.int64).reshape(-1, 2)
        a, b = np.r_[ends[:, 0], ends[:, 1]], np.r_[ends[:, 1], ends[:, 0]]
        deg = np.maximum(np.bincount(a, minlength=nv), 1)[:, None]
        for _ in range(3):
            w *= near[dom]
            w /= np.maximum(w.sum(1, keepdims=True), 1e-9)
            avg = np.zeros_like(w)
            np.add.at(avg, a, w[b])
            w = 0.5 * w + 0.5 * avg / deg
        w *= near[dom]
        if w.shape[1] > 4:
            np.put_along_axis(w, np.argsort(w, axis=1)[:, :-4], 0.0, axis=1)
        w /= np.maximum(w.sum(1, keepdims=True), 1e-9)
        w[~weighted] = 0
        moved += int((np.abs(w - before).max(1) > 0.01).sum())
        vg = {n: o.vertex_groups.get(n) or o.vertex_groups.new(name=n) for n in bones}
        for g in o.vertex_groups:
            if g.name in col:
                g.remove(list(range(nv)))
        for k, n in enumerate(bones):
            idx = np.nonzero(w[:, k] > 1e-4)[0]
            for i in idx:
                vg[n].add([int(i)], float(w[i, k]), "REPLACE")
        names = {g.index: g.name for g in o.vertex_groups}
        dname = [bones[d] if ok else None for d, ok in zip(dom, weighted)]
        bm = bmesh.new()
        bm.from_mesh(o.data)
        bad = [f for f in bm.faces if any(dname[p.index] and dname[q.index] and hops(dname[p.index], dname[q.index]) > NEAR
                                          for p, q in zip(f.verts, list(f.verts[1:]) + [f.verts[0]]))]
        # the contacts are marked before welding (welding renumbers the vertices the test above reads)
        for f in bm.faces:
            f.select = False
        for f in bad:
            f.select = True
        # one surface first: an imported model is split at every UV seam, and filling "every open edge" after the cut
        # capped those seams too and worked out the facing per loose piece - a fox came out with 772 open edges, in four
        # pieces, patches inside out (2026-11-06). Welding keeps the UVs (they are on the faces' corners).
        bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=size * 1e-5)
        bad = [f for f in bm.faces if f.select]
        if bad:
            cut = {v for f in bad for v in f.verts}
            bmesh.ops.delete(bm, geom=bad, context="FACES")
            # only the openings this cut made are closed (an opening the model has - a mouth - stays open)
            caps = bmesh.ops.holes_fill(bm, edges=[e for e in bm.edges if e.is_boundary and all(v in cut for v in e.verts)], sides=0)["faces"]
            # the caps are cut into even triangles and turned to face outward with the rest of the skin: a cap facing
            # in showed as a dark hole in the throat when the claw moved off it (a game engine would not draw it at all)
            if caps:
                bmesh.ops.triangulate(bm, faces=caps, quad_method="BEAUTY", ngon_method="BEAUTY")
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
            total += len(bad)
        # the welded surface goes back even when nothing was cut: one surface skins and exports cleanly
        bm.to_mesh(o.data)
        o.data.update()
        bm.free()
    print(f"weights: {moved} vertices kept to their own limb and smoothed; {total} faces where far-apart parts touched were cut and closed")


# cutting contacts is a repair for skins that tear where parts touch - measured like every other weight step and kept
# only if the rig deforms better with it: a fox's own weights passed (stretch 1.31x idle, 1.40x walk, no folds) and
# came out of the cut failing (1.67x, 2.27x, 0.3% folded), so it would have been thrown away (2026-11-06)
before = {o.name: o.data.copy() for o in meshes}
pre_res, pre_stiff, pre_none = deform_check(list(actions))
separate_fused()
res_all, stiff, none = deform_check(list(actions))
if score(res_all, none) > score(pre_res, pre_none):
    for o in meshes:
        cut_mesh = o.data
        o.data = before[o.name]
        bpy.data.meshes.remove(cut_mesh)
    bpy.context.view_layer.update()
    res_all, stiff, none = pre_res, pre_stiff, pre_none
    print(f"weights: cutting the contacts deformed worse ({score(res_all, none):.2f} kept against the cut's) - the skin as it was")
else:
    for m in before.values():
        bpy.data.meshes.remove(m)
problems = gate(res_all, stiff, none)
quality = "PASS" if not problems else "FAIL"
if problems and not os.environ.get("AMAL_KEEP_FAILED"):
    # a rig that fails is never shown or exported: no clips, previews or FBX - and the ones an earlier try left are erased,
    # so nothing broken reaches the owner (2026-11-01: torn, mirrored clips sat in the job's pictures). The report says why.
    import glob
    for f in [os.path.join(ROOT, "renders", f"{name}_rig.fbx"), os.path.join(REN, f"{name}_rig.png")] + \
            glob.glob(os.path.join(REN, f"{name}@*.fbx")) + [os.path.join(REN, f"{name}_{c}.{x}") for c in wanted for x in ("glb", "mp4")]:
        if os.path.exists(f):
            os.remove(f)
    info = {"name": name, "quality": quality, "problems": problems, "weights": weights, "deform": res_all,
            "stiff_share": stiff, "unweighted": none, "bones": len(bones), "files": {}}
    with open(os.path.join(REN, f"{name}_rig_report.json"), "w") as fh:
        json.dump(info, fh, indent=1)
    print("AMAL_INFO " + json.dumps(info))
    print("AMAL_QUALITY_FAIL " + "; ".join(problems))
    raise SystemExit(1)

# -------------------------------------------------- show it: one preview per clip, the creature fills the frame
L.ground(max(20.0, size * 30), L.mat("Floor", "#3b3b3b", rough=0.85))
cam = L.frame(objs=meshes, fill=1.5 if not {"jump", "flap"} & set(wanted) else 1.3)
L.lights()
pivot = bpy.data.objects.new("AMAL_turn", None)
sc.collection.objects.link(pivot)
pivot.location = centre
cam.parent = pivot
cam.location = cam.location - centre      # parented to the pivot: the same place in the world
sc.frame_set(1)
blend, png = L.finish(name + "_rig", sheet=False) if not os.environ.get("AMAL_NO_RENDER") else (None, None)
if hasattr(sc.render.image_settings, "media_type"):
    sc.render.image_settings.media_type = "VIDEO"   # Blender 5: video is its own media type
sc.render.image_settings.file_format = "FFMPEG"
sc.render.ffmpeg.format = "MPEG4"
sc.render.ffmpeg.codec = "H264"
sc.render.ffmpeg.constant_rate_factor = "HIGH"
sc.render.resolution_x, sc.render.resolution_y = 960, 960

# -------------------------------------------------- game-ready files, one per animation (the Unity / Unreal convention)
files = {"rig": f"renders/{name}_rig.fbx"}


def only(objs):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]


fbx_common = dict(use_selection=True, add_leaf_bones=False, primary_bone_axis="Y", secondary_bone_axis="X",
                  axis_forward="-Z", axis_up="Y", apply_scale_options="FBX_SCALE_ALL", mesh_smooth_type="FACE")
only([arm] + meshes)
bpy.ops.export_scene.fbx(filepath=os.path.join(ROOT, files["rig"]), object_types={"ARMATURE", "MESH"}, bake_anim=False,
                         path_mode="COPY", embed_textures=True, **fbx_common)
for clip, (act, n) in actions.items():
    arm.animation_data.action = act
    sc.frame_start, sc.frame_end = 1, n
    only([arm])
    # <name>@<clip>.fbx: the skeleton and this animation only - the engine puts it on the rig above
    bpy.ops.export_scene.fbx(filepath=os.path.join(REN, f"{name}@{clip}.fbx"), object_types={"ARMATURE"}, bake_anim=True,
                             bake_anim_use_all_actions=False, bake_anim_use_nla_strips=False, bake_anim_force_startend_keying=True,
                             bake_anim_simplify_factor=0.0, **fbx_common)
    only([arm] + meshes)
    glb = os.path.join(REN, f"{name}_{clip}.glb")
    try:
        bpy.ops.export_scene.gltf(filepath=glb, use_selection=True, export_format="GLB", export_animations=True, export_animation_mode="ACTIVE_ACTIONS")
    except TypeError:
        bpy.ops.export_scene.gltf(filepath=glb, use_selection=True, export_format="GLB", export_animations=True)
    pivot.animation_data_clear()
    pivot.rotation_euler = (0, 0, 0)
    pivot.keyframe_insert("rotation_euler", frame=1)
    pivot.rotation_euler = (0, 0, math.radians(35))
    pivot.keyframe_insert("rotation_euler", frame=n)
    sc.render.filepath = os.path.join(REN, f"{name}_{clip}.mp4")
    if not os.environ.get("AMAL_NO_RENDER"):      # a quick test checks the motion, not the pictures
        bpy.ops.render.render(animation=True)
    files[clip] = {"fbx": f"renders/{name}@{clip}.fbx", "glb": f"renders/{name}_{clip}.glb", "mp4": f"renders/{name}_{clip}.mp4", "frames": n}
arm.animation_data.action = None
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(ROOT, "scenes", f"{name}_rig.blend"))
count = {}
for v in kinds.values():
    count[v] = count.get(v, 0) + 1
info = {"name": name, "quality": quality, "problems": problems, "weights": weights, "deform": res_all,
        "stiff_share": stiff, "unweighted": none, "bones": len(bones), "chains": count, "fps": fps, "files": files,
        # what an engine needs to put shared clips on it: its bones by name (the Godot bone map is made from them) and
        # its height standing in the bind pose
        "bone_names": [b.name for b in bones], "height_m": round(height, 4)}
with open(os.path.join(REN, f"{name}_rig_report.json"), "w") as fh:
    json.dump(info, fh, indent=1)
print("AMAL_INFO " + json.dumps(info))
if quality != "PASS":
    # kept for the owner's review only (AMAL_KEEP_FAILED): the step still fails, so the job does not call it done
    print("AMAL_QUALITY_FAIL " + "; ".join(problems))
    raise SystemExit(1)
