"""advanced_skeleton - rig ANY model with AdvancedSkeleton in Maya, without anyone at the interface. The rig tool runs it:

    mayapy advanced_skeleton.py <model.glb|.gltf|.fbx|.obj|.ma> <name> <workspace>      (env AMAL_AMALD: the driver, for skeleton plans)

1. prepare()   import the model, merge it, stand it on the floor, face +Z (AdvancedSkeleton's front), centimetres;
   model_check() AdvancedSkeleton's Model Checker and Cleaner: default transforms, no history, symmetrical (made so)
2. AdvancedSkeleton places the skeleton, the way its own workflow does: its ready-made FitSkeleton for the body
   (AMAL_RIG_BODY: biped -> bipedGame, quadruped -> horse, winged -> dragon), then its own AutoPlace - which fits a
   biped by itself (crotch, arm pits, neck, wrists, fingers) and scales any other template to the model.
   A body AutoPlace cannot fit by itself uses AMAL's plan (`amald skeleton`, crates/amal-core/src/skeleton.rs) to move the template's joints onto
   the parts it found; if that plan cannot be made, AdvancedSkeleton's scaled template is built as it is.
4. build()     in full Maya (AdvancedSkeleton's build reads its window's controls): build the rig, bind the mesh to the
               deformation joints with geodesic voxel weights (max 4 influences), export FBX, save the scene.
Maya's own error lines come back from build(); the cause of any failure is in them.
"""
import json
import os
import subprocess
import sys

import maya.api.OpenMaya as om
import maya.cmds as cmds

AS = os.environ.get("AMAL_ADVANCED_SKELETON", r"D:/amal/harness_data/addons/AdvancedSkeletonMaya").replace("\\", "/")
HERE = os.path.dirname(os.path.abspath(__file__))
_MESH = None
# meshes that follow the model through every turn and move prepare() and model_check() give it, so they keep lying
# exactly on it: the light proxy the skin weights are made on (AMAL_AS_PROXY, made by Blender)
_FOLLOW = []


def _all(mesh):
    return [mesh] + [f for f in _FOLLOW if cmds.objExists(f)]
_MIRRORED = True   # the model was made symmetrical: AdvancedSkeleton fits one side and mirrors it


def _fn(mesh):
    sel = om.MSelectionList()
    sel.add(mesh)
    return om.MFnMesh(sel.getDagPath(0))


def _points(mesh):
    return [om.MVector(p.x, p.y, p.z) for p in _fn(mesh).getPoints(om.MSpace.kWorld)]


def prepare(path, name=None):
    """Import a mesh (GLB/glTF/FBX/OBJ/MA), merge it to one object, stand it on the floor at the origin and turn it to face +Z.
    Returns the mesh name. The front is where the head is: the top fifth of the mesh leans forward of the body."""
    global _MESH
    cmds.currentUnit(linear="cm")
    if path.lower().endswith(".fbx") and not cmds.pluginInfo("fbxmaya", q=True, loaded=True):
        cmds.loadPlugin("fbxmaya")
    before = set(cmds.ls(type="mesh", long=True))
    if path.lower().endswith((".glb", ".gltf")):
        # Maya has no glTF importer: AMAL's own reader, no other program in between
        sys.path.insert(0, HERE)
        import gltf_in
        gltf_in.load(path, tex_dir=os.path.join(os.getcwd(), "scenes"))
    else:
        cmds.file(path, i=True, ignoreVersion=True, mergeNamespacesOnClash=True, namespace=":")
    shapes = [s for s in cmds.ls(type="mesh", long=True) if s not in before and not cmds.getAttr(s + ".intermediateObject")]
    if not shapes:
        raise RuntimeError(f"no mesh came in from {path}")
    xforms = list({cmds.listRelatives(s, parent=True, fullPath=True)[0] for s in shapes})
    mesh = cmds.polyUnite(xforms, ch=False, n=name or "body")[0] if len(xforms) > 1 else xforms[0]
    cmds.makeIdentity(mesh, apply=True, t=True, r=True, s=True)
    mesh = cmds.rename(mesh, name or "body") if name else cmds.ls(mesh)[0]
    proxy = os.environ.get("AMAL_AS_PROXY", "")
    if proxy and os.path.isfile(proxy) and proxy.lower().endswith((".glb", ".gltf")):
        # the light copy comes in the same way, in the same place, and takes every turn and move the model takes
        seen = set(cmds.ls(type="mesh", long=True))
        sys.path.insert(0, HERE)
        import gltf_in
        gltf_in.load(proxy, tex_dir=os.path.join(os.getcwd(), "scenes"))
        pshapes = [s for s in cmds.ls(type="mesh", long=True) if s not in seen and not cmds.getAttr(s + ".intermediateObject")]
        if pshapes:
            px = list({cmds.listRelatives(s, parent=True, fullPath=True)[0] for s in pshapes})
            pm = cmds.polyUnite(px, ch=False, n="amalProxy")[0] if len(px) > 1 else px[0]
            cmds.makeIdentity(pm, apply=True, t=True, r=True, s=True)
            pm = cmds.rename(pm, "amalProxy")
            cmds.delete(pm, ch=True)
            cmds.setAttr(pm + ".visibility", 0)       # out of AdvancedSkeleton's way until the weights are made
            _FOLLOW[:] = [pm]
            print(f"AMAL_AS_STEP light copy for the skin weights: {cmds.polyEvaluate(pm, f=True)} faces")
    pts = _points(mesh)
    lo = om.MVector(min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts))
    hi = om.MVector(max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts))
    # Y up: the tallest axis of a standing creature is up; if Z is far taller, the file came in Z-up
    if (hi.z - lo.z) > 1.6 * (hi.y - lo.y):
        for m in _all(mesh):
            cmds.rotate(-90, 0, 0, m, r=True, ws=True)
            cmds.makeIdentity(m, apply=True, r=True)
        pts = _points(mesh)
    cy = min(p.y for p in pts)
    h = max(p.y for p in pts) - cy
    centre = sum(pts, om.MVector()) / len(pts)
    top = [p for p in pts if p.y > cy + 0.8 * h]
    head = sum(top, om.MVector()) / max(1, len(top))
    d = head - centre
    turn = 0
    # the head tells the front only where it clearly leans out over the body (a quadruped, a dragon). On an upright body
    # it sits over the middle and its lean is noise: the model keeps the facing it was made with - glTF's front is +Z,
    # and the generator and the clean-up keep it (upright goblins were turned 180 and -90 degrees on that noise, and
    # AdvancedSkeleton's AutoPlace then could not read them, 2026-11-12)
    if max(abs(d.x), abs(d.z)) < 0.08 * h:
        pass
    elif abs(d.x) > abs(d.z):
        turn = -90 if d.x > 0 else 90
    elif d.z < 0:
        turn = 180
    if turn:
        for m in _all(mesh):
            cmds.rotate(0, turn, 0, m, r=True, ws=True, pivot=(0, 0, 0))
            cmds.makeIdentity(m, apply=True, r=True)
        pts = _points(mesh)
    lo = om.MVector(min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts))
    hi = om.MVector(max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts))
    for m in _all(mesh):
        cmds.move(-(lo.x + hi.x) / 2, -lo.y, -(lo.z + hi.z) / 2, m, r=True, ws=True)
        cmds.makeIdentity(m, apply=True, t=True)
    _MESH = mesh
    print(f"prepared {mesh}: height {hi.y - lo.y:.1f} cm, turned {turn} deg to face +Z, {len(pts)} vertices")
    return mesh


SYMMETRY_NEEDED = 0.9   # share of the model whose mirror image lands on it: below this, mirroring fuses parts that cross the middle (a three-quarter dragon at ~70-80% got its wing tips joined at the centre line, 2026-11-02)


def symmetry_plane_of(pts, step=2):
    """The turn about Y (degrees, Maya's sense) that makes a point cloud's left and right halves match best, the X of the
    mirror plane after that turn, and the match (share of points whose mirror image lands on the cloud). Any body plan."""
    import numpy as np
    pts = np.asarray(pts, dtype=float)
    h = float(np.ptp(pts[:, 1])) or 1.0
    cell = h * 0.02
    sample = pts[np.random.default_rng(0).choice(len(pts), min(len(pts), 4000), replace=False)]
    offs = np.array([(a, b, c) for a in (-1, 0, 1) for b in (-1, 0, 1) for c in (-1, 0, 1)])

    def key(q):
        q = q + (1 << 20)
        return (q[:, 0] << 42) | (q[:, 1] << 21) | q[:, 2]

    def match(deg):
        a = np.radians(deg)
        rot = np.array([[np.cos(a), 0, np.sin(a)], [0, 1, 0], [-np.sin(a), 0, np.cos(a)]])
        p = pts @ rot.T
        mid = float(np.median(p[:, 0]))
        cells = np.floor((p - [mid, 0, 0]) / cell).astype(np.int64)
        occupied = np.unique(key((cells[:, None, :] + offs[None, :, :]).reshape(-1, 3)))
        m = sample @ rot.T - [mid, 0, 0]
        m[:, 0] *= -1
        return (deg, mid, float(np.isin(key(np.floor(m / cell).astype(np.int64)), occupied).mean()))

    best = max((match(d) for d in range(-90, 90, step)), key=lambda b: b[2])
    # then to half a degree around the best turn
    return max((match(best[0] + d / 2) for d in range(-2 * step, 2 * step + 1)), key=lambda b: b[2])


def symmetry_plane(mesh):
    import numpy as np
    return symmetry_plane_of(np.array(cmds.xform(f"{mesh}.vtx[*]", q=True, ws=True, t=True)).reshape(-1, 3))


def _face_front(mesh):
    """After the turn to the mirror plane, the model faces +Z or -Z: the head end (the top fifth leaning out of the body)
    goes to +Z, as prepare() does."""
    import numpy as np
    pts = np.array(cmds.xform(f"{mesh}.vtx[*]", q=True, ws=True, t=True)).reshape(-1, 3)
    cy, h = pts[:, 1].min(), np.ptp(pts[:, 1])
    top = pts[pts[:, 1] > cy + 0.8 * h]
    if len(top) and top[:, 2].mean() < pts[:, 2].mean():
        for m in _all(mesh):
            cmds.rotate(0, 180, 0, m, r=True, ws=True, pivot=(0, 0, 0))
            cmds.makeIdentity(m, apply=True, r=True)


def model_check(mesh, symmetrize=True):
    """AdvancedSkeleton's Model Checker (asModelChecker in AdvancedSkeleton.mel), headless, after its Model Cleaner's
    fixes: (1) the mesh and every parent at default transforms - translate, rotate and pivots 0, scale 1; (2) no
    construction history; (3) the model symmetrical across X (each vertex at -X has a mirror vertex within 0.001 cm).
    A generated model is never exactly symmetrical, so it is made so first the way modellers do before rigging: cut
    at X = 0 and mirror one half onto the other. Raises with every rule still broken -
    owner 2026-11-01: "go through all the AdvancedSkeleton checks; if it fails, it's bad - follow those rules and it works."
    """
    import numpy as np
    cmds.delete(mesh, ch=True)                                    # Model Cleaner: construction history off
    if symmetrize:
        # the mirror plane must be the model's own: a generated model stands turned the way its picture was (three-quarter),
        # and mirroring it across X = 0 as it stood cut the dragon diagonally and gave it two tails (2026-11-01). So the
        # model is first turned until its left and right halves match, and mirrored only when they nearly do.
        turn, mid, score = symmetry_plane(mesh)
        for m in _all(mesh):
            cmds.rotate(0, turn, 0, m, r=True, ws=True, pivot=(0, 0, 0))
            cmds.move(-mid, 0, 0, m, r=True, ws=True)
            cmds.makeIdentity(m, apply=True, t=True, r=True)
        _face_front(mesh)
        print(f"AMAL_AS_STEP symmetry plane: turned {turn} deg, {round(score * 100)}% of the model mirrors onto itself")
        symmetrize = score >= SYMMETRY_NEEDED
        global _MIRRORED
        _MIRRORED = symmetrize
        if not symmetrize:
            # mirroring a lopsided model makes a different creature (two tails); it is rigged as it is, centred on its own
            # mirror plane - AdvancedSkeleton's mirrored joints still fit, only its mirror-weights tool needs exact symmetry
            print(f"AMAL_AS_STEP the model is {round(score * 100)}% symmetrical (mirrored from {round(SYMMETRY_NEEDED * 100)}%): rigged as it is, not mirrored")
    if symmetrize:
        cmds.polyMirrorFace(mesh, ws=True, cutMesh=True, axis=0, mirrorAxis=2, mirrorPosition=0, mergeMode=1, mergeThreshold=0.001)
        cmds.delete(mesh, ch=True)
    cmds.makeIdentity(mesh, apply=True, t=True, r=True, s=True)
    for a in ("rotatePivot", "scalePivot"):
        cmds.setAttr(f"{mesh}.{a}", 0, 0, 0)
    broken = []
    path = cmds.ls(mesh, long=True)[0].split("|")[1:]
    for i in range(len(path)):
        node = "|" + "|".join(path[:i + 1])
        for attr, want in (("t", 0), ("r", 0), ("s", 1), ("rp", 0), ("sp", 0)):
            vals = cmds.getAttr(f"{node}.{attr}")[0]
            if any(abs(v - want) > 1e-6 for v in vals):
                broken.append(f"{node}.{attr} = {tuple(round(v, 4) for v in vals)}, should be {want}")
    allowed = ("skinCluster", "blendShape", "tweak", "deltaMush")
    hist = [h for h in (cmds.listHistory(mesh, pdo=True, il=2) or []) if cmds.objectType(h) not in allowed]
    if hist:
        broken.append("construction history: " + ", ".join(hist[:6]))
    pts = np.array(cmds.xform(f"{mesh}.vtx[*]", q=True, ws=True, t=True)).reshape(-1, 3)
    left = pts[pts[:, 0] <= 0.001]
    mirrored = left * np.array([-1.0, 1.0, 1.0])
    off = 0
    for k in range(0, len(mirrored), 256):                        # nearest vertex to each mirrored one, in chunks
        d = ((mirrored[k:k + 256, None, :] - pts[None, :, :]) ** 2).sum(-1).min(1)
        off += int((d > 0.001 ** 2).sum())
    if off and symmetrize:
        broken.append(f"not symmetrical: {off} of {len(left)} vertices on the right have no mirror vertex on the left")
    print(f"AMAL_AS_STEP AdvancedSkeleton model check: " + ("passed" if not broken else "; ".join(broken)))
    if broken:
        raise RuntimeError("AdvancedSkeleton's model check failed: " + "; ".join(broken))
    return True


SEAM_ROUNDS = 3   # rounds of averaging across a seam between bones: each spreads it over one more row of edges


def limit_weights(mesh, hops=2, limbs=True):
    """With limbs=False only the four-bones-per-vertex limit is applied (the full model after it took the light copy's
    weights: the limbs and their seams were made on the copy, where three rows of edges are a few centimetres - on the
    full model three rows were millimetres, hard seams that tore at 7x, 2026-11-07).
Each patch of skin follows one limb, the way riggers paint weights: a vertex keeps only the joints within `hops` of
    its strongest joint in the skeleton. A generated model is one surface where parts touch (a claw on the throat, a head
    over the chest), and the bind and the Delta Mush spread the neck's weights onto the claw and the claw's onto the neck -
    every move dragged the other part along and tore (2026-11-01). Returns how many vertices changed."""
    import numpy as np
    import maya.api.OpenMayaAnim as oma
    sc = [h for h in (cmds.listHistory(mesh, pdo=True) or []) if cmds.objectType(h) == "skinCluster"]
    if not sc:
        return 0
    sel = om.MSelectionList()
    sel.add(sc[0])
    sel.add(mesh)
    fn = oma.MFnSkinCluster(sel.getDependNode(0))
    path = sel.getDagPath(1).extendToShape()
    comp = om.MFnSingleIndexedComponent()
    verts = comp.create(om.MFn.kMeshVertComponent)
    comp.setCompleteData(om.MFnMesh(path).numVertices)
    flat, n = fn.getWeights(path, verts)
    names = [p.fullPathName() for p in fn.influenceObjects()]
    # joints a few steps apart in the skeleton (through any joint, influence or not)
    link = {}
    for j in cmds.ls(type="joint", long=True):
        par = cmds.listRelatives(j, parent=True, fullPath=True, type="joint")
        if par:
            link.setdefault(j, set()).add(par[0])
            link.setdefault(par[0], set()).add(j)
    w = np.array(flat).reshape(-1, n)
    if not limbs:
        if n > 4:
            drop = np.argsort(w, axis=1)[:, :-4]
            np.put_along_axis(w, drop, 0.0, axis=1)
        w /= np.maximum(w.sum(1, keepdims=True), 1e-9)
        fn.setWeights(path, verts, om.MIntArray(list(range(n))), om.MDoubleArray(w.ravel().tolist()), False)
        print("AMAL_AS_STEP the model's weights kept to four bones a vertex")
        return 0
    near = np.zeros((n, n), dtype=bool)
    for a, name in enumerate(names):
        seen, edge = {name}, {name}
        for _ in range(hops):
            edge = {m for e in edge for m in link.get(e, ())} - seen
            seen |= edge
        near[a] = [m in seen for m in names]
    keep = near[w.argmax(1)]
    changed = int(((w > 1e-4) & ~keep).any(1).sum())
    w = w * keep
    w /= np.maximum(w.sum(1, keepdims=True), 1e-9)
    # then the seams are smoothed, as riggers do: where neighbouring vertices follow different bones, a few rounds of
    # averaging with the neighbours spread the change over several rows of edges instead of one (the wing membrane met
    # the chest on a single row and stretched 1.6-2.3x there, 2026-11-02)
    mfn = om.MFnMesh(path)
    ends = np.array([mfn.getEdgeVertices(e) for e in range(mfn.numEdges)], dtype=np.int64)
    a, b = np.r_[ends[:, 0], ends[:, 1]], np.r_[ends[:, 1], ends[:, 0]]
    deg = np.bincount(a, minlength=len(w)).astype(float)
    dom = w.argmax(1)
    band = np.zeros(len(w), dtype=bool)
    band[a[dom[a] != dom[b]]] = True
    for _ in range(SEAM_ROUNDS - 1):                 # the seam widened by a row each round
        grow = band.copy()
        grow[a[band[b]]] = True
        band = grow
    for _ in range(SEAM_ROUNDS * 2):
        avg = np.zeros_like(w)
        np.add.at(avg, a, w[b])
        avg /= np.maximum(deg, 1)[:, None]
        w[band] = avg[band]
    # at most four bones per vertex, as game engines take
    if n > 4:
        drop = np.argsort(w, axis=1)[:, :-4]
        np.put_along_axis(w, drop, 0.0, axis=1)
    w /= np.maximum(w.sum(1, keepdims=True), 1e-9)
    fn.setWeights(path, verts, om.MIntArray(list(range(n))), om.MDoubleArray(w.ravel().tolist()), False)
    print(f"AMAL_AS_STEP weights kept to each limb: {changed} vertices no longer pulled by another limb")
    return changed


def plan(mesh=None, out=None):
    """The model's skeleton plan, in this scene's coordinates: the mesh is written as OBJ and read by the driver
    (`amald skeleton`, AMAL_AMALD)."""
    mesh = mesh or _MESH
    if not cmds.pluginInfo("objExport", q=True, loaded=True):
        cmds.loadPlugin("objExport")
    obj = os.path.abspath(out or "scenes/_plan_mesh.obj")
    os.makedirs(os.path.dirname(obj), exist_ok=True)
    cmds.select(mesh, r=True)
    cmds.file(obj, force=True, options="groups=0;ptgroups=0;materials=0;smoothing=0;normals=0", typ="OBJexport", pr=True, es=True)
    js = os.path.splitext(obj)[0] + ".json"
    r = subprocess.run([os.environ.get("AMAL_AMALD") or "amald", "skeleton", obj, js], capture_output=True, text=True, timeout=600)
    if r.returncode != 0 or not os.path.isfile(js):
        raise RuntimeError("amald skeleton failed:\n" + (r.stdout + r.stderr)[-3000:])
    print(r.stdout.strip())
    with open(js) as fh:
        return json.load(fh)


# AdvancedSkeleton's labels for each joint role, as its own templates set them (biped.ma, dragon.ma):
# (joint type, other type). Spline chains (necks of 2+, tails) number their joints "0Neck"/"0Tail", "1", "2"...
LABELS = {"root": (1, "Mid"), "chest": (18, "Chest"), "hip": (2, ""), "ankle": (4, ""), "toes": (18, "Toes"),
          "toes_end": (18, "ToesEnd"), "scapula": (0, "PropA1"), "shoulder": (10, ""), "elbow": (18, "22"),
          "wrist": (12, ""), "head_end": (18, "23")}


# AdvancedSkeleton's own FitSkeleton for each body (its fitSkeletons/*.ma)
TEMPLATES = {"biped": "bipedGame.ma", "quadruped": "horse.ma", "winged": "dragon.ma"}


def import_template(tpl):
    """AdvancedSkeleton's ready-made FitSkeleton, imported the way its Import button does (its template name kept on
    FitSkeleton, which AutoPlace reads to know the body)."""
    if cmds.objExists("FitSkeleton"):
        cmds.delete("FitSkeleton")
    cmds.file(f"{AS}/AdvancedSkeletonFiles/fitSkeletons/{tpl}", i=True, ignoreVersion=True, mergeNamespacesOnClash=True, namespace=":")
    if not cmds.attributeQuery("fitSkeletonTemplate", node="FitSkeleton", exists=True):
        cmds.addAttr("FitSkeleton", ln="fitSkeletonTemplate", dt="string")
    cmds.setAttr("FitSkeleton.fitSkeletonTemplate", os.path.splitext(tpl)[0], type="string")


def pick_template(p):
    """AdvancedSkeleton's own ready-made FitSkeleton for the body the plan found (its names, labels and settings), or
    None: wings -> dragon (its front limbs are wings), four legs -> horse, two arms + two legs -> the game biped."""
    kinds = [c["kind"] for c in p["chains"]]
    n = kinds.count
    if n("wing") >= 2:
        return "dragon.ma"
    if n("leg") >= 4:
        return "horse.ma"
    if n("leg") == 2 and n("arm") == 2:
        return "bipedGame.ma"
    return None


def _one_side():
    """Every side joint on the template's side of the middle line. AdvancedSkeleton fits one side and mirrors it; a joint
    placed across the line (a plan's arm joined to a wing on one side, its elbow landing on the other) stops the build
    ("ArmElbow is on the Left side, FitSkeleton side-joints must start on the Right side", 2026-11-03). On a symmetrical
    model the mirror image of such a joint is where it belongs. Parents first, so each joint is read where it now is."""
    if not cmds.objExists("Hip"):
        return
    want = 1.0 if _wpos("Hip").x > 0 else -1.0
    joints = cmds.listRelatives("FitSkeleton", allDescendents=True, type="joint", fullPath=True) or []
    joints.sort(key=lambda j: j.count("|"))
    moved = []
    for j in joints:
        w = _wpos(j)
        if abs(w.x) > 1e-3 and (w.x > 0) != (want > 0):
            cmds.xform(j, ws=True, t=(-w.x, w.y, w.z))
            moved.append(j.split("|")[-1])
    if moved:
        print(f"AMAL_AS_STEP {len(moved)} joint(s) were across the middle line and were mirrored to the fitted side: {', '.join(moved[:8])}")


def _wpos(j):
    return om.MVector(*cmds.xform(j, q=True, ws=True, t=True))


def _path(top, bottom):
    chain, x = [bottom], bottom
    while x != top:
        x = cmds.listRelatives(x, parent=True)[0]
        chain.append(x)
    return chain[::-1]


def _deepest(start, prefix):
    best, depth = start, 0
    for d in cmds.listRelatives(start, allDescendents=True, type="joint") or []:
        if d.startswith(prefix):
            k = len(_path(start, d))
            if k > depth:
                best, depth = d, k
    return best


def _along(pts, f):
    seg = [(pts[i + 1] - pts[i]).length() for i in range(len(pts) - 1)]
    tot = sum(seg)
    if tot <= 0:
        return pts[0]
    d = f * tot
    for i, L in enumerate(seg):
        if d <= L or i == len(seg) - 1:
            return pts[i] + (pts[i + 1] - pts[i]) * (min(d, L) / max(L, 1e-9))
        d -= L
    return pts[-1]


def _place(chain, pts):
    """Move a template chain onto a line through the plan's joints, its joints spaced as the template spaces them."""
    if len(pts) < 2 or len(chain) < 2:
        return
    W = [_wpos(j) for j in chain]
    L = [0.0]
    for a, b in zip(W, W[1:]):
        L.append(L[-1] + (b - a).length())
    for j, w, l in zip(chain, W, L):
        q = _along(pts, l / (L[-1] or 1.0))
        # a joint on the template's middle line stays exactly on it: a head end placed a hair to one side is a "Left
        # side" joint to AdvancedSkeleton, and its build stops ("HeadEnd is on the Left side", 2026-11-03)
        x = 0.0 if abs(w.x) < 1e-3 else q.x
        if any(cmds.listConnections(f"{j}.{a}", source=True, destination=False) for a in ("t", "tx", "ty", "tz")):
            continue                     # driven by the template: it follows its driver
        cmds.xform(j, ws=True, t=(x, q.y, q.z))


def fit_template(p, mesh=None):
    """AdvancedSkeleton's documented workflow: start from its ready-made FitSkeleton for this kind of body and move its
    joints onto the model - its own joint names and labels (IK legs and arms, spline neck and tail, quadruped feet,
    wing fingers), not names of AMAL's. The plan (amald skeleton) gives where each part goes. A part the template has twice
    over (a dragon with arms as well as wings) is added as a copy of the template's limb; a part the model lacks is
    removed. Returns the template's name, or raises (fit_plan is the fallback)."""
    if not p.get("mirrored", _MIRRORED):
        # the templates are fitted on one side and mirrored: a lopsided model needs each side fitted to its own limbs
        raise RuntimeError("the model is not symmetrical: each side is fitted on its own (fit_plan)")
    tpl = pick_template(p)
    if not tpl:
        raise RuntimeError("no ready-made AdvancedSkeleton template fits this body")
    import_template(tpl)
    cx = p["centre_x"]
    J = {j["name"]: j for j in p["joints"]}
    kids = {}
    for j in p["joints"]:
        kids.setdefault(j["parent"], []).append(j["name"])
    side = "L" if _wpos("Hip").x - cx > 0 else "R"          # the side the template is built on (it mirrors the other)
    V = lambda j: om.MVector(J[j]["pos"][0] - cx, J[j]["pos"][1], J[j]["pos"][2])
    def chain_from(name, stop_roles=()):
        out = [name]
        while True:
            nxt = [k for k in kids.get(out[-1], []) if J[k]["role"] not in ("finger",) and J[k]["role"] not in stop_roles]
            if not nxt:
                return out
            out.append(nxt[0])
    def by_role(role, prefix="", sd=None):
        return [n for n, j in J.items() if j["role"] == role and n.startswith(prefix) and (sd is None or j["side"] == sd)]
    # the template to the model's size first (fingers, toes and feet keep their proportions)
    roots = by_role("root")
    if not roots:
        raise RuntimeError("the plan has no root")
    k = V(roots[0]).y / max(_wpos("Root").y, 1e-6)
    # some templates ship joints with their translate locked (bipedGame.ma's HeadEnd): unlocked here, the way
    # AdvancedSkeleton's own Fit tools move them - a locked one stopped every biped fit ("A child attribute of
    # 'HeadEnd.translate' is locked", 2026-11-13) and sent the knight to the weaker fall-back
    for j in cmds.listRelatives("FitSkeleton", allDescendents=True, type="joint") or []:
        for a in ("t", "tx", "ty", "tz"):
            if cmds.getAttr(f"{j}.{a}", lock=True):
                cmds.setAttr(f"{j}.{a}", lock=False)
    for j in cmds.listRelatives("FitSkeleton", allDescendents=True, type="joint") or []:
        if any(cmds.listConnections(f"{j}.{a}", source=True, destination=False) for a in ("t", "tx", "ty", "tz")):
            continue                     # driven by the template itself: it follows its driver
        t = cmds.getAttr(j + ".t")[0]
        cmds.setAttr(j + ".t", t[0] * k, t[1] * k, t[2] * k)
    # body: root -> chest, chest -> head end, the tail
    chest = by_role("chest")
    spine_pts = [V(roots[0])] + [V(n) for n in sorted(by_role("spine"), key=lambda n: J[n]["pos"][1])] + ([V(chest[0])] if chest else [])
    _place(_path("Root", "Chest"), spine_pts)
    neck = sorted(by_role("neck"), key=lambda n: J[n]["pos"][1])
    head_pts = [V(chest[0])] if chest else []
    head_pts += [V(n) for n in neck + by_role("head") + by_role("head_end")]
    _place(_path("Chest", "HeadEnd"), head_pts)
    tails = by_role("tail")
    if cmds.objExists("Tail0"):
        if tails:
            first = min((n for n in tails if J[n]["parent"] in roots), key=lambda n: n, default=None) or tails[0]
            _place(_path("Tail0", _deepest("Tail0", "Tail")), [V(n) for n in chain_from(first)])
        else:
            cmds.delete("Tail0")
    # limbs: the template's leg = the back legs; its front limb = wings (dragon), front legs (horse) or arms (biped)
    hips = sorted(by_role("hip", sd=side), key=lambda n: J[n]["pos"][2])     # back first (the model faces +Z)
    if not hips:
        raise RuntimeError("the plan has no leg on the template's side")
    _place(_path("Hip", _deepest("Hip", "Toes")), [V(n) for n in chain_from(hips[0])])
    if tpl == "dragon.ma":
        front = by_role("scapula", "Wing", side)
    elif tpl == "horse.ma":
        front = hips[1:2]
    else:
        front = [n for n in by_role("scapula", sd=side) if not n.startswith("Wing")]
    if not front:
        raise RuntimeError(f"the plan has no limb for {tpl}'s front limb")
    end = _deepest("Wrist", "Fingers") if tpl == "horse.ma" else "Wrist"
    _place(_path("Scapula", end), [V(n) for n in chain_from(front[0])])
    # a dragon with arms as well as wings: the arms are a copy of the template's limb, without its wing fingers
    arms = [n for n in by_role("scapula", sd=side) if not n.startswith("Wing")] if tpl == "dragon.ma" else []
    if arms:
        dup = cmds.duplicate("Scapula", renameChildren=True)
        line = [dup[0]]   # the copy's Scapula -> Shoulder -> Elbow -> Wrist; its wing fingers go first
        while len(line) < 4:
            ch = cmds.listRelatives(line[-1], children=True, type="joint", fullPath=True) or []
            if not ch:
                break
            line.append(max(ch, key=lambda c: len(cmds.listRelatives(c, allDescendents=True, type="joint") or [])))
        for f in cmds.listRelatives(line[-1], children=True, type="joint", fullPath=True) or []:
            cmds.delete(f)
        new = {}
        for d, base in zip(reversed(line), reversed(("Scapula", "Shoulder", "Elbow", "Wrist")[:len(line)])):
            new[base] = cmds.rename(d, "Arm" + base)   # children first, so the parents' paths stay valid
        _place([new[x] for x in ("Scapula", "Shoulder", "Elbow", "Wrist") if x in new], [V(n) for n in chain_from(arms[0])])
    _one_side()
    bad = [j for j in cmds.listRelatives("FitSkeleton", allDescendents=True, type="joint") or [] if "_" in j]
    if bad:
        raise RuntimeError(f"joint names with underscores after the fit: {bad[:5]}")
    print(f"FitSkeleton: AdvancedSkeleton's {tpl} fitted to the model" + (" (+ arms as a copy of its limb)" if arms else ""))
    return tpl


def fit_plan(p, mesh=None):
    """Make AdvancedSkeleton's FitSkeleton from a plan (amald skeleton's output): the FitSkeleton node comes from its biped
    template (it carries AdvancedSkeleton's settings), the joints from the plan."""
    mesh = mesh or _MESH
    if p.get("front", 1) < 0:
        raise RuntimeError("the model faces -Z: prepare() should have turned it - re-run prepare() then plan()")
    if cmds.objExists("FitSkeleton"):
        cmds.delete("FitSkeleton")
    cmds.file(f"{AS}/AdvancedSkeletonFiles/fitSkeletons/biped.ma", i=True, ignoreVersion=True,
              mergeNamespacesOnClash=True, namespace=":")
    old = cmds.listRelatives("FitSkeleton", children=True, type="joint", fullPath=True) or []
    if old:
        cmds.delete(old)
    h = p["height"]
    cx = p["centre_x"]
    # a symmetrical model: AdvancedSkeleton fits the right side and mirrors it. A lopsided one (a three-quarter pose, one
    # wing forward) gets both sides fitted to their own limbs and no mirroring: the mirrored left wing landed on the
    # wrong part of the membrane and every clip tore there (2026-11-02)
    mirror = p.get("mirrored", _MIRRORED)
    joints = p["joints"] if not mirror else [j for j in p["joints"] if not (j["side"] == "L" and j["mirror"])]
    role = {j["name"]: j["role"] for j in joints}
    made, spline_i = {}, {}
    necks = [j for j in joints if j["role"] == "neck"]
    core = ("root", "spine", "chest", "neck", "head", "head_end")
    for j in joints:
        name = j["name"][:-2] if j["name"].endswith(("_R", "_L")) else j["name"]
        # AdvancedSkeleton adds its own _R/_L/_M; an underscore anywhere else stops its build with a dialog that
        # waits for a click (a full-Maya build sat on it until the 15-minute timeout)
        name = name.replace("_", "")
        while cmds.objExists(name):
            name += "x"
        x, y, z = j["pos"]
        x -= cx
        if j["role"] in core:
            x = 0.0                                   # the body's centre line
        elif j["side"] == "C" and abs(x) < h * 0.05:
            # a centre chain (a tail) a little off the middle is voxel noise from thinning the shape, not a curl: off
            # the line, AdvancedSkeleton builds it as a one-sided _L chain whose weights pull the left hip and leg -
            # the dragon tore only on the left (Knee_L, Hip_L, Toes_L, Tail1_L) with its tail 2.6% of its height off
            x = 0.0
        elif j["side"] == "R":
            x = min(x, -h * 0.01)                     # right side starts at -X (AdvancedSkeleton's rule)
        cmds.select(clear=True)
        jn = cmds.joint(n=name, p=(x, y, z), rad=max(h * 0.01, 0.1))
        jn = cmds.parent(jn, made.get(j["parent"], "FitSkeleton"))[0]
        made[j["name"]] = jn
        typ, otp = LABELS.get(j["role"], (None, None))
        if j["role"] == "neck" and len(necks) > 1:
            k = necks.index(j)
            typ, otp = 18, ("0Neck" if k == 0 else str(k))
        elif j["role"] == "head" and len(necks) > 1:
            typ, otp = 18, str(len(necks))
        elif j["role"] == "head_end" and len(necks) > 1:
            typ, otp = 18, f"{len(necks)}N"
        elif j["role"] == "tail":
            k = spline_i[j["parent"]] + 1 if role.get(j["parent"]) == "tail" else 0
            spline_i[j["name"]] = k
            typ, otp = 18, ("0Tail" if k == 0 else str(k))
        if typ is not None:
            cmds.setAttr(jn + ".type", typ)
            if otp:
                cmds.setAttr(jn + ".otherType", otp, type="string")
        # left of the centre without a right-side twin (a tail curling left, a part on one side only):
        # AdvancedSkeleton must not mirror it
        # unmirrored model: every joint is marked so, the right side's too - left on, AdvancedSkeleton copied the right
        # wing onto the left beside the real one and the two fought over it (WingShoulder_L + WingShoulderx_L, 2026-11-02)
        if not mirror or (x > h * 0.005 and (j["side"] == "C" or not j["mirror"])):
            cmds.addAttr(jn, ln="noMirror", at="bool", dv=1)
    print(f"FitSkeleton: {len(made)} joints from the plan ({len(p['joints'])} with the mirrored side)")
    return made


def _plan_facing(m, name):
    """The skeleton plan, the model turned round first when the plan reads it as facing -Z (planned once more then)."""
    p = plan(m, f"scenes/{name}_plan_mesh.obj")
    if p.get("front", 1) < 0:      # the skeleton says the head is toward -Z: turn round and plan again
        for x in _all(m):
            cmds.rotate(0, 180, 0, x, r=True, ws=True, pivot=(0, 0, 0))
            cmds.makeIdentity(x, apply=True, r=True)
        p = plan(m, f"scenes/{name}_plan_mesh.obj")
    return p


def _digits_per_hand(p):
    """The fewest separate fingers on either hand of a plan (its Finger<n>A joints on each arm's wrist)."""
    per = {}
    for j in p.get("joints", []):
        n = j["name"]
        if j["role"] == "finger" and n.startswith("Finger") and n[:-2].endswith("A") and n[-2:] in ("_R", "_L"):
            per.setdefault(n[-2:], set()).add(n)
    return min((len(v) for v in per.values()), default=0)


def save(path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    cmds.file(rename=os.path.abspath(path))
    cmds.file(save=True, type="mayaAscii")
    return os.path.abspath(path)


# the proxy the weights are made on: dense enough to follow the shape, light enough for the bind and the bake to take
# about a minute
PROXY_FACES = 20000


def build_mel(fit_scene, out_scene, fbx, mel_path, mesh=None, place=False, here=False):
    """Write a .mel for gui_run(): open the fitted scene, build the AdvancedSkeleton rig (it needs Maya's interface),
    bind the mesh to the deformation joints with geodesic voxel weights (max 4 influences), export the skinned rig as
    FBX for game engines, save, quit. Maya's messages come back from gui_run(). `here`: for the Maya it is sourced in
    (an open Maya driven through MCP or the live link) - the build runs at once and that Maya is never quit."""
    f = lambda p: os.path.abspath(p).replace("\\", "/")
    mesh = mesh or _MESH or "body"
    # AdvancedSkeleton's own AutoPlace (its Fit > AutoPlace button), with the model as its Skin geometry: it fits a
    # biped template by itself and scales any other template to the model; it leaves its guides, which go after it
    place_mel = f'''
textField -e -tx "{mesh}" asBodySkinTextField;
string $tpl = `getAttr FitSkeleton.fitSkeletonTemplate`;
if (!`gmatch $tpl "biped*"`) createNode -n asFitAutoScale transform;
// AutoPlace stopping on an error of its own is the same as not reading the body (a squat goblin: "No valid objects
// supplied to 'xform'" inside AdvancedSkeleton.mel, 2026-11-12): it is said as that, and the FitSkeleton is then fitted
// from AMAL's own skeleton plan
if (catch(`asFitAutoPlace`)) error ("AdvancedSkeleton's AutoPlace could not read this model as its " + $tpl + " template");
// a biped it cannot read is said, not built wrong; other templates are only scaled, and leave no guides to read
if (`gmatch $tpl "biped*"` && !`objExists AutoPlacing`) error ("AdvancedSkeleton's AutoPlace could not read this model as its " + $tpl + " template");
if (`objExists AutoPlacing`) asFitDeleteGuides;
print ("AMAL_AS_STEP AdvancedSkeleton's AutoPlace placed its " + $tpl + " FitSkeleton\\n");
''' if place else ""
    mel = f'''
global proc amalAsDeltaMushBake(string $mesh)
{{
string $root[] = `listRelatives -c -type joint DeformationSystem`;
if (size($root) == 0) error "no root joint under DeformationSystem";
// an unskinned copy at the bind pose receives the baked weights
string $dup[] = `duplicate -rr -n amalBaked $mesh`;
string $sh[] = `listRelatives -s -f $dup[0]`;
for ($s in $sh) if (`getAttr ($s + ".intermediateObject")`) delete $s;
string $p[] = `listRelatives -p $dup[0]`;
if (size($p)) parent -w $dup[0];
deltaMush -si 20 -ss 0.5 -pinBorderVertices 1 $mesh;
// prune weights under 2% (stray far-bone influences: the dragon's knee smeared from a few such vertices) and smooth 3x
bakeDeformer -ss $root[0] -sm $mesh -ds $root[0] -dm $dup[0] -mi 4 -pw 0.02 -sw 3;
string $hist[] = `listHistory $dup[0]`;
string $bs[] = `ls -type skinCluster $hist`;
if (size($bs) == 0) error "bakeDeformer made no skin";
delete $mesh;
rename $dup[0] $mesh;
print "AMAL_AS_STEP delta mush baked into the skin weights\\n";
}}
global proc amalAsWork()
{{
file -f -o "{f(fit_scene)}";
currentUnit -l cm;
// AdvancedSkeleton stops on a dialog (waiting for a click no one gives) for joint names with "_": refuse them here
string $fj[] = `listRelatives -ad -type joint FitSkeleton`;
for ($n in $fj) if (`gmatch $n "*_*"`) error ("FitSkeleton joint name with an underscore: " + $n + " (AdvancedSkeleton would stop on a dialog)");
source "{AS}/AdvancedSkeleton.mel";
// the build reads its options from the AdvancedSkeleton window's controls ("Object 'asBodyOffsetParentMatrixCheckBox'
// not found" without it), so open the window first, the way a rigger does
AdvancedSkeleton;
print "AMAL_AS_STEP window\\n";
{place_mel}
asBuildAdvancedSkeleton;
print "AMAL_AS_STEP built\\n";
string $xf[] = {{"{mesh}"}};
string $dj[] = `listRelatives -ad -type joint DeformationSystem`;
// the weights are made on a light proxy of the model and copied onto it - the riggers' standard for dense meshes: the
// geodesic bind and the Delta Mush bake on 150,000 triangles ran past ten minutes and used up the PC's memory
// (2026-11-06), and a proxy's weights are smoother, with no noise from the mesh's small detail
string $bindOn = $xf[0];
int $nf[] = `polyEvaluate -f $xf[0]`;
if (`objExists amalProxy`) {{
    // Blender's light copy, brought in by prepare() and lying exactly on the model
    $bindOn = "amalProxy";
    setAttr amalProxy.visibility 1;
    int $pf[] = `polyEvaluate -f amalProxy`;
    print ("AMAL_AS_STEP weights made on Blender's " + $pf[0] + "-face light copy of the " + $nf[0] + "-face model\\n");
}} else if ($nf[0] > {PROXY_FACES} * 3/2) {{
    string $px[] = `duplicate -rr -n amalProxy $xf[0]`;
    // generated meshes are not manifold (TRELLIS's are not: "Cannot reduce polygonal object with nonmanifold geometry",
    // 2026-11-06): Maya's own Mesh > Cleanup first - zero-area faces, zero-length edges, non-manifold geometry, lamina
    // faces, invalid components (polyCleanupArgList version 4, Maya 2027's scripts/others/polyCleanupArgList.mel)
    select -r $px[0];
    catch(`polyCleanupArgList 4 {{"0","0","0","0","0","0","0","0","1","1e-05","1","1e-05","0","1e-05","0","2","1","1"}}`);
    select -cl;
    // what Cleanup leaves (it did, 2026-11-06): non-manifold edges and vertices are split apart - a proxy only gives
    // weights, an opened seam on it costs nothing
    for ($pass = 0; $pass < 3; $pass++) {{
        string $nme[] = `polyInfo -nme $px[0]`;
        if (size($nme)) catch(`polySplitEdge -op 1 $nme`);
        string $nmv[] = `polyInfo -nmv $px[0]`;
        if (size($nmv)) catch(`polySplitVertex $nmv`);
        if (!size($nme) && !size($nmv)) break;
    }}
    // Maya's current reducer refuses non-manifold meshes; its first one (version 0) is tried after it
    int $reduced = !catch(`polyReduce -ver 1 -trm 2 -tct {PROXY_FACES} -kb 1 -ch 0 $px[0]`);
    if (!$reduced) $reduced = !catch(`polyReduce -ver 0 -trm 2 -tct {PROXY_FACES} -ch 0 $px[0]`);
    if (!$reduced) {{
        delete $px[0];
        print "AMAL_AS_STEP proxy could not be made - the model itself is bound\\n";
    }} else {{
        int $pf[] = `polyEvaluate -f $px[0]`;
        print ("AMAL_AS_STEP weights made on a " + $pf[0] + "-face proxy of the " + $nf[0] + "-face model\\n");
        $bindOn = $px[0];
    }}
}}
select -r $dj; select -add $bindOn;
string $sc[] = `skinCluster -tsb -mi 4 -nw 1 -bm 3 -dr 4 -n amalSkin`;
// falloff = stiffness, 0..1: 0 (rigid) made hard seams at every joint and the gate saw them tear; 0.5 blends joints.
// voxel resolution 512 (AdvancedSkeleton's 256 joins parts that lie close - a wing's finger against its shoulder
// shared weights and tore, 2026-11-01)
geomBind -bm 3 -fo 0.5 -mi 4 -gvp 512 1 $sc[0];
print "AMAL_AS_STEP skinned\\n";
// the riggers' standard smoothing for game rigs: a Delta Mush over the bind, baked back into plain skin weights
// (bakeDeformer, max 4 influences) - joints bend smoothly without a Delta Mush the game engine cannot run
if (catch(`amalAsDeltaMushBake $bindOn`)) print "AMAL_AS_STEP delta mush bake failed - the geodesic bind's weights are kept\\n";
// each patch of skin follows one limb, its seams spread over a few rows of edges - on the light copy when there is one
python("import sys; sys.path.insert(0, r'{f(HERE)}'); import advanced_skeleton; advanced_skeleton.limit_weights('" + $bindOn + "')");
if ($bindOn != $xf[0]) {{
    // the model takes the proxy's weights: closest point on the surface, the same joints
    select -r $dj; select -add $xf[0];
    string $hs[] = `skinCluster -tsb -mi 4 -nw 1 -n amalSkinModel`;
    string $ph[] = `listHistory $bindOn`;
    string $ps[] = `ls -type skinCluster $ph`;
    copySkinWeights -ss $ps[0] -ds $hs[0] -noMirror -surfaceAssociation closestPoint -influenceAssociation oneToOne -influenceAssociation closestJoint -normalize;
    delete $bindOn;
    print "AMAL_AS_STEP the proxy's weights copied onto the model\\n";
    python("import sys; sys.path.insert(0, r'{f(HERE)}'); import advanced_skeleton; advanced_skeleton.limit_weights('{mesh}', limbs=False)");
}}
loadPlugin -qt fbxmaya;
select -r DeformationSystem $xf[0];
FBXResetExport; FBXExportSkins -v true; FBXExportShapes -v true; FBXExportUpAxis y; FBXExportSmoothingGroups -v true;
FBXExport -f "{f(fbx)}" -s;
print "AMAL_AS_STEP exported\\n";
file -rename "{f(out_scene)}"; file -save -type "mayaAscii";
print "AMAL_AS_BUILT\\n";
}}
global proc amalAsBuild()
{{
// whatever fails, Maya's error is in the log and Maya still quits (a session left open would hang the job)
if (catch(`amalAsWork`)) print "AMAL_AS_FAILED (see the Error lines above)\\n";
{"" if here else "quit -force;"}
}}
{"amalAsBuild;" if here else 'evalDeferred -lowestPriority "amalAsBuild";'}
'''
    with open(mel_path, "w", encoding="utf-8") as fh:
        fh.write(mel)
    return f(mel_path)


def gui_run(mel_file, timeout=900):
    """Run a MEL file in full Maya (its interface exists there; AdvancedSkeleton's build needs it) and return Maya's
    own messages. The same as the session's gui_run(), here too so `advanced_skeleton.gui_run` is not a dead end."""
    import subprocess, sys, tempfile, time
    exe = os.path.join(os.path.dirname(sys.executable), "maya.exe" if os.name == "nt" else "maya")
    log = os.path.join(tempfile.gettempdir(), "amal_maya_gui_%d.log" % int(time.time()))
    # Maya is watched while it works: one that has opened and not started the script - a window at its start waiting
    # for a click no one gives (sign-in, licence, crash recovery, a first-run prompt) - is ended after `start_wait`
    # seconds with that said, not after the whole time (a rig waited 15 minutes on a Maya whose log stayed empty,
    # 2026-11-11)
    start_wait = int(os.environ.get("AMAL_MAYA_START_WAIT", "240"))
    # the script says it has started by writing a file (Maya's own log may reach the disk late)
    mark = log + ".started"
    wrap = os.path.splitext(os.path.abspath(mel_file))[0] + "_start.mel"
    fwd = lambda path: os.path.abspath(path).replace("\\", "/")
    with open(wrap, "w", encoding="utf-8") as fh:
        fh.write('{ int $f = `fopen "%s" "w"`; fprint $f "started"; fclose $f; }\nsource "%s";\n' % (fwd(mark), fwd(mel_file)))
    p = subprocess.Popen([exe, "-script", wrap], env=dict(os.environ, MAYA_CMD_FILE_OUTPUT=log))
    read = lambda: open(log, encoding="utf-8", errors="replace").read() if os.path.isfile(log) else ""
    def end():
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True)
        else:
            p.kill()
        try: p.wait(20)
        except Exception: pass
    began = time.time()
    while p.poll() is None:
        time.sleep(2)
        waited = time.time() - began
        if waited > start_wait and not os.path.isfile(mark):
            end()
            raise RuntimeError("Maya opened but did not start the build script in %d s - a window at its start is waiting for a "
                "click (sign-in, licence, crash recovery, a first-run prompt): open Maya once on this machine and close what "
                "it asks.\n%s" % (start_wait, read()[-2000:] or "(Maya wrote nothing)"))
        if waited > timeout:
            end()
            raise RuntimeError("Maya did not finish the build in %d s. What it said last:\n%s" % (timeout, read()[-3000:] or "(Maya wrote nothing)"))
    text = read() or "(Maya wrote no log)"
    return "exit %s\n%s" % (p.returncode, text[-6000:])


def run_here(mel_file):
    """Source a MEL file in this Maya (an open one, with its interface) and return what Maya printed meanwhile."""
    import maya.mel as mel
    import tempfile, time
    log = os.path.join(tempfile.gettempdir(), "amal_maya_here_%d.log" % int(time.time() * 1000))
    cmds.cmdFileOutput(o=log)
    try:
        mel.eval('source "%s";' % os.path.abspath(mel_file).replace("\\", "/"))
    finally:
        cmds.cmdFileOutput(ca=True)
    return open(log, encoding="utf-8", errors="replace").read() if os.path.isfile(log) else ""


def build(fit_scene, out_scene, fbx, mesh=None, timeout=900, place=False, here=False):
    """One call for the whole build: write the MEL, run it in full Maya, check it. Raises with Maya's own messages when
    the rig, skin or export did not happen, so the cause is in front of whoever reads the error. `here`: in this Maya
    (open, with its interface) instead of a new one started for the build."""
    mel_path = os.path.splitext(os.path.abspath(out_scene))[0] + "_build.mel"
    made = build_mel(fit_scene, out_scene, fbx, mel_path, mesh, place, here)
    text = run_here(made) if here else gui_run(made, timeout)
    # Maya's own start-up complaints (USD menu, Bifrost's missing folder) come before the build and are not its cause
    noise = ("mayaUsdMenu", "Bifrost")
    steps = [l for l in text.splitlines() if ("AMAL_AS_" in l or "Error" in l) and not any(n in l for n in noise)]
    print("\n".join(steps[-40:]))
    if "AMAL_AS_BUILT" not in text or not os.path.isfile(fbx):
        raise RuntimeError("the AdvancedSkeleton build did not finish - the cause is in Maya's Error lines:\n" + "\n".join(steps[-20:]))
    return os.path.abspath(fbx)


def rig(src, name, here=False):
    """The whole rig in the current folder (the job's workspace: scenes/, renders/): prepare, check, place the
    skeleton, build, bind, export. Raises with the cause; Maya's own lines are in its log."""
    m = prepare(src, name="body")
    model_check(m)
    body = os.environ.get("AMAL_RIG_BODY", "").strip().lower()
    tpl = TEMPLATES.get(body)
    p, place = {"joints": [], "chains": [], "warnings": []}, False
    hands = None
    if body == "biped":
        # AdvancedSkeleton's AutoPlace finds a biped by scanning across four separate fingers (its fourFingerHit:
        # "Unable to detect ... form" otherwise, or an xform error inside its finger search). A generated game
        # character rarely has them - mitten hands, gauntlets - and every such run was a full Maya pass that could
        # only fail (the knight and the goblin, 2026-11-12/13). The plan counts the digits on each hand first.
        try:
            p = _plan_facing(m, name)
            hands = _digits_per_hand(p)
        except Exception as e:
            print(f"AMAL_AS_STEP no skeleton plan to count the fingers ({str(e).splitlines()[-1][:200]})")
    if body == "biped" and (hands is None or hands >= 4):
        # AdvancedSkeleton fits a biped by itself: its template, then its AutoPlace in the build
        import_template(tpl)
        place = True
        print(f"AMAL_AS_STEP biped: AdvancedSkeleton's {tpl} + its AutoPlace")
    else:
        if body == "biped":
            print(f"AMAL_AS_STEP biped with {hands} separate finger(s) a hand: AdvancedSkeleton's AutoPlace needs four, "
                  f"so its {tpl} is fitted from AMAL's skeleton plan")
        try:
            p = p if p["joints"] else _plan_facing(m, name)
        except Exception as e:
            if not tpl:
                raise
            # no plan: AdvancedSkeleton's own template, scaled to the model by its AutoPlace, is built as it is
            print(f"AMAL_AS_STEP no skeleton plan ({str(e).splitlines()[-1][:200]}); AdvancedSkeleton's {tpl}, scaled by its AutoPlace")
            import_template(tpl)
            place = True
        if not place:
            try:
                tpl = fit_template(p, m)
            except Exception as e:   # no template fits, or fitting failed: AMAL's own FitSkeleton from the plan
                print(f"AMAL_AS_STEP template fit not used ({type(e).__name__}: {e}); building the FitSkeleton from the plan")
                tpl = None
                fit_plan(p, m)
    save(f"scenes/{name}_fit.ma")
    try:
        fbx = build(f"scenes/{name}_fit.ma", f"scenes/{name}_as.ma", f"renders/{name}_as.fbx", m, place=place, here=here)
    except RuntimeError as e:
        # AdvancedSkeleton's AutoPlace reads average human proportions; a body it cannot read (a squat goblin in a
        # T-pose, 2026-11-12) is still a biped: its FitSkeleton is placed from AMAL's own reading of the model's
        # limbs instead - the same template, fitted to the plan - and built the same way
        if not (place and body == "biped" and "AutoPlace could not read" in str(e)):
            raise
        print("AMAL_AS_STEP AutoPlace could not read this body - the biped FitSkeleton is fitted from AMAL's own skeleton plan")
        cmds.file(new=True, force=True)
        m = prepare(src, name="body")
        p = plan(m, f"scenes/{name}_plan_mesh.obj")
        if p.get("front", 1) < 0:
            # the plan reads the front from the limbs: where it says the model faces away, the model is turned round
            for one in _all(m):
                cmds.rotate(0, 180, 0, one, r=True, ws=True, pivot=(0, 0, 0))
                cmds.makeIdentity(one, apply=True, r=True)
            print("AMAL_AS_STEP the skeleton plan reads the model as facing away - turned round")
            p = plan(m, f"scenes/{name}_plan_mesh.obj")
        place = False
        try:
            tpl = fit_template(p, m)
        except Exception as e2:
            print(f"AMAL_AS_STEP template fit not used ({type(e2).__name__}: {e2}); building the FitSkeleton from the plan")
            tpl = None
            fit_plan(p, m)
        save(f"scenes/{name}_fit.ma")
        fbx = build(f"scenes/{name}_fit.ma", f"scenes/{name}_as.ma", f"renders/{name}_as.fbx", m, place=False, here=here)
    info = {"fbx": fbx, "joints": len(p["joints"]),
            "chains": [c["kind"] + " " + c["side"] for c in p["chains"]],
            "warnings": p.get("warnings", []), "template": tpl, "placed_by": "AdvancedSkeleton AutoPlace" if place else "AMAL plan"}
    print("AMAL_INFO " + json.dumps(info))
    return info


def rig_here(src, name, ws, body="", amald="", advanced_skeleton="", proxy=""):
    """The same rig in the Maya that is open now (driven through MCP or the live link), where every step can be looked
    at. His open scene is never thrown away: one with unsaved changes stops the rig with that said. The rig is made in a
    new scene and saved under the job's folder; the folder Maya was working in is put back after. The settings the
    `rig` tool hands a mayapy run as its environment come as arguments here (an open Maya was started without them):
    body (biped / quadruped / winged), amald (the driver's program, for skeleton plans), advanced_skeleton (its
    folder), proxy (the light copy the weights are made on)."""
    global AS
    for k, v in (("AMAL_RIG_BODY", body), ("AMAL_AMALD", amald), ("AMAL_ADVANCED_SKELETON", advanced_skeleton), ("AMAL_AS_PROXY", proxy)):
        if v:
            os.environ[k] = v
    if advanced_skeleton:
        AS = advanced_skeleton.replace("\\", "/")
    if cmds.file(q=True, modified=True):
        raise RuntimeError("the scene open in Maya has unsaved changes - save or close it, then rig again (it is not thrown away)")
    before = os.getcwd()
    os.makedirs(os.path.join(ws, "scenes"), exist_ok=True)
    os.makedirs(os.path.join(ws, "renders"), exist_ok=True)
    os.chdir(ws)
    try:
        cmds.file(new=True, force=True)
        return rig(src, name, here=True)
    finally:
        os.chdir(before)


if __name__ == "__main__":
    # mayapy advanced_skeleton.py <model> <name> [workspace]
    import maya.standalone
    maya.standalone.initialize(name="python")
    src, name = sys.argv[1], sys.argv[2]
    ws = sys.argv[3] if len(sys.argv) > 3 else os.getcwd()
    os.chdir(ws)
    log = os.path.join(ws, "scenes", f"{name}_maya.log")
    os.makedirs(os.path.dirname(log), exist_ok=True)
    cmds.cmdFileOutput(o=log)
    try:
        rig(src, name)
    except Exception as e:  # Maya's own lines are the evidence: print them with the error
        cmds.cmdFileOutput(c=True) if hasattr(cmds, "cmdFileOutput") else None
        said = open(log, encoding="utf-8", errors="replace").read()[-3000:] if os.path.isfile(log) else ""
        print(f"AMAL_AS_ERROR {type(e).__name__}: {e}\n--- Maya says ---\n{said}")
        sys.exit(1)
    finally:
        maya.standalone.uninitialize()
