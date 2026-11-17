"""maya_mesh - one of Maya's mesh tools on a model, in mayapy (no window). The flow editor's Maya nodes run this.

    mayapy maya_mesh.py <op> <model.glb|.fbx|.obj|.ma> <out.fbx> [key=value ...]

The tools and their settings are listed in maya_mesh.json (the flow editor builds its nodes from that list). Each prints
`AMAL_INFO {...}` (faces and vertices before and after, what ran) and writes the FBX; a tool that cannot run ends with
`AMAL_SPEC_ERROR <why>` and exit code 1, so a failed step never hands on a model it did not make.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def fail(why):
    print("AMAL_SPEC_ERROR " + why)
    sys.exit(1)


def load(path):
    """The model as one mesh transform, history off."""
    before = set(cmds.ls(type="mesh", long=True))
    ext = os.path.splitext(path)[1].lower()
    if ext in (".glb", ".gltf"):
        sys.path.insert(0, HERE)
        import gltf_in   # Maya has no glTF importer: AMAL's own reader
        gltf_in.load(path, tex_dir=os.path.join(os.getcwd(), "scenes"))
    else:
        if ext == ".fbx" and not cmds.pluginInfo("fbxmaya", q=True, loaded=True):
            cmds.loadPlugin("fbxmaya")
        if ext == ".obj" and not cmds.pluginInfo("objExport", q=True, loaded=True):
            cmds.loadPlugin("objExport")
        cmds.file(path, i=True, ignoreVersion=True, mergeNamespacesOnClash=True, namespace=":")
    shapes = [s for s in cmds.ls(type="mesh", long=True) if s not in before and not cmds.getAttr(s + ".intermediateObject")]
    if not shapes:
        fail(f"no mesh came in from {path}")
    xforms = list({cmds.listRelatives(s, parent=True, fullPath=True)[0] for s in shapes})
    mesh = cmds.polyUnite(xforms, ch=False, mergeUVSets=True, n="model")[0] if len(xforms) > 1 else xforms[0]
    try:
        cmds.parent(mesh, world=True)
    except Exception:
        pass
    cmds.makeIdentity(mesh, apply=True, t=True, r=True, s=True)
    cmds.delete(mesh, ch=True)
    return cmds.rename(mesh, "model")


def constraint_off():
    """The selection constraint back off (resetPolySelectConstraint is a UI script mayapy does not have)."""
    try:
        cmds.polySelectConstraint(m=0, sz=0, a=0, dis=True)
    except Exception:
        cmds.polySelectConstraint(m=0)


def counts(mesh):
    return {"faces": cmds.polyEvaluate(mesh, f=True), "vertices": cmds.polyEvaluate(mesh, v=True), "triangles": cmds.polyEvaluate(mesh, t=True)}


def cleanup(mesh, merge=0.01):
    """Maya's Mesh > Cleanup (polyCleanupArgList, version 4) on the whole mesh, then what it leaves split apart.
    The merge comes first: merged after the split, the split vertices joined again and the mesh stayed non-manifold
    (1028 places left on the chicken's light copy, and Reduce refused it, 2026-11-07)."""
    if merge > 0:
        cmds.polyMergeVertex(mesh, d=merge, am=True, ch=False)
    cmds.select(mesh, r=True)
    try:
        mel.eval('polyCleanupArgList 4 { "0","0","0","0","0","0","0","0","1","1e-05","1","1e-05","0","1e-05","0","2","1","1" }')
    except Exception:
        pass
    for _ in range(4):
        nme = cmds.polyInfo(mesh, nme=True) or []
        if nme:
            cmds.polySplitEdge(nme, op=1, ch=False)
        nmv = cmds.polyInfo(mesh, nmv=True) or []
        if nmv:
            cmds.polySplitVertex(nmv, ch=False)
        if not nme and not nmv:
            break
    # what splitting leaves (edges shared by three faces or more that come back as one): the faces on it go and the
    # hole is capped - a few faces, so Reduce and Retopologize take the mesh (Maya refuses any non-manifold place)
    for _ in range(3):
        nme = cmds.polyInfo(mesh, nme=True) or []
        if not nme:
            break
        faces = cmds.polyListComponentConversion(nme, fe=True, tf=True) or []
        if faces:
            cmds.delete(faces)
            cmds.polyCloseBorder(mesh, ch=False)
    cmds.delete(mesh, ch=True)
    return {"non_manifold_left": len(cmds.polyInfo(mesh, nme=True) or []) + len(cmds.polyInfo(mesh, nmv=True) or [])}


def reduce_to(mesh, want, keep_borders=True):
    """polyReduce to about `want` triangles. Maya refuses a whole mesh with any non-manifold place left; then each
    piece is reduced by its share and a piece Maya still refuses is kept as it is. Returns the mesh and how it went."""
    def one(m, t):
        try:
            cmds.polyReduce(m, ver=1, trm=2, tct=max(4, int(t)), kb=keep_borders, ch=False)
        except Exception:
            cmds.polyReduce(m, ver=0, trm=2, tct=max(4, int(t)), ch=False)
    total = cmds.polyEvaluate(mesh, t=True)
    if total <= want:
        return mesh, {"reduced": "already small enough"}
    try:
        one(mesh, want)
        return mesh, {"reduced": "whole"}
    except Exception:
        pass
    try:
        parts = cmds.polySeparate(mesh, ch=False) or []
    except Exception:
        parts = []
    parts = [p for p in parts if cmds.listRelatives(p, shapes=True)]
    if len(parts) < 2:
        fail("reduce: Maya refuses this model even after Cleanup (non-manifold), and it is one piece")
    refused = 0
    for p in parts:
        t = cmds.polyEvaluate(p, t=True)
        try:
            one(p, t * want / total)
        except Exception:
            refused += 1
    m = cmds.polyUnite(parts, ch=False, mergeUVSets=True, n="model")[0]
    try:
        cmds.parent(m, world=True)
    except Exception:
        pass
    m = cmds.rename(m, "model")
    return m, {"reduced": f"piece by piece ({len(parts)} pieces, {refused} kept as they were)"}


def run(op, mesh, a):
    num = lambda k, d: float(a.get(k, d))
    did = {}
    if op == "cleanup":
        did = cleanup(mesh, num("merge", 0.01))
    elif op == "floaters":
        try:
            parts = cmds.polySeparate(mesh, ch=False) or []
        except Exception:
            parts = []          # one piece: nothing floats
        parts = [p for p in parts if cmds.objectType(p) == "transform" or cmds.listRelatives(p, shapes=True)]
        if len(parts) > 1:
            areas = {p: cmds.polyEvaluate(p, a=True) for p in parts}
            big = max(areas.values()) or 1.0
            keep = [p for p, ar in areas.items() if ar >= num("keep", 0.02) * big]
            gone = [p for p in parts if p not in keep]
            if gone:
                cmds.delete(gone)
            mesh = cmds.polyUnite(keep, ch=False, mergeUVSets=True, n="model")[0] if len(keep) > 1 else keep[0]
            try:
                cmds.parent(mesh, world=True)
            except Exception:
                pass
            mesh = cmds.rename(mesh, "model")
            did = {"pieces": len(parts), "removed": len(gone)}
        else:
            did = {"pieces": 1, "removed": 0}
    elif op == "nsided_to_quads":
        # Bonus Tools' bt_polyNSidedToQuad: the faces with more than four sides, triangulated, then quadrangulated
        cmds.select(mesh + ".f[*]", r=True)
        cmds.polySelectConstraint(m=2, t=8, sz=3)
        big = cmds.ls(sl=True, fl=True) or []
        constraint_off()
        if big:
            cmds.polyTriangulate(big, ch=False)
            cmds.polyQuad(mesh, a=num("angle", 30), kgb=True, ktb=True, khe=True, ws=True, ch=False)
        did = {"n_sided_faces": len(big)}
    elif op == "quads":
        cmds.polyQuad(mesh, a=num("angle", 30), kgb=True, ktb=True, khe=True, ws=True, ch=False)
    elif op == "triangulate":
        cmds.polyTriangulate(mesh, ch=False)
    elif op == "reduce":
        cleanup(mesh, 0.0)
        mesh, did = reduce_to(mesh, int(num("triangles", 20000)))
    elif op == "retopo":
        cleanup(mesh, 0.01)
        want = int(num("faces", 8000))
        used = "Retopologize"
        try:
            cmds.polyRetopo(mesh, targetFaceCount=want)
        except Exception as e:
            used = f"Reduce + Quadrangulate (Retopologize: {str(e).strip()[:120]})"
            mesh, _ = reduce_to(mesh, want * 2)
            cmds.polyQuad(mesh, a=40, kgb=True, ktb=True, khe=True, ws=True, ch=False)
        cmds.delete(mesh, ch=True)
        did = {"used": used}
    elif op == "smooth":
        cmds.polySmooth(mesh, dv=int(num("divisions", 1)), kb=True, ch=False)
    elif op == "mirror":
        keep_plus = str(a.get("keep", "+x")).strip() != "-x"
        cmds.polyMirrorFace(mesh, ws=True, cutMesh=True, axis=0, axisDirection=0 if keep_plus else 1, mirrorAxis=2,
                            mirrorPosition=0, mergeMode=1, mergeThreshold=num("merge", 0.01))
        cmds.delete(mesh, ch=True)
    elif op == "merge":
        cmds.polyMergeVertex(mesh, d=num("distance", 0.01), am=True, ch=False)
    elif op == "fill_holes":
        cmds.polyCloseBorder(mesh, ch=False)
    elif op == "soften":
        cmds.polySoftEdge(mesh, a=num("angle", 60), ch=False)
    elif op == "uvs":
        steps = ["projection"]
        cmds.polyAutoProjection(mesh + ".f[*]", ch=False)
        try:
            if not cmds.pluginInfo("Unfold3D", q=True, loaded=True):
                cmds.loadPlugin("Unfold3D")
            res = int(num("resolution", 2048))
            cmds.u3dUnfold(mesh, ite=1, p=0, bi=1, tf=1, ms=res, rs=0)
            steps.append("unfold")
            cmds.u3dLayout(mesh, res=256, scl=1, spc=0.0039, mar=0.0039, box=(0, 1, 0, 1))
            steps.append("layout")
        except Exception as e:
            cmds.polyLayoutUV(mesh + ".f[*]", l=2, sc=1, ps=0.2, ch=False)
            steps.append(f"Maya layout (Unfold3D: {str(e).strip()[:100]})")
        cmds.delete(mesh, ch=True)
        did = {"steps": steps}
    elif op == "floor":
        h = num("height", 0)
        bb = cmds.exactWorldBoundingBox(mesh)
        if h > 0 and bb[4] - bb[1] > 0:
            s = h / (bb[4] - bb[1])
            cmds.scale(s, s, s, mesh, pivot=(0, 0, 0), r=True)
            cmds.makeIdentity(mesh, apply=True, s=True)
            bb = cmds.exactWorldBoundingBox(mesh)
        cmds.move(-(bb[0] + bb[3]) / 2, -bb[1], -(bb[2] + bb[5]) / 2, mesh, r=True, ws=True)
        cmds.makeIdentity(mesh, apply=True, t=True, r=True, s=True)
        cmds.xform(mesh, piv=(0, 0, 0), ws=True)
        bb = cmds.exactWorldBoundingBox(mesh)
        did = {"height_cm": round(bb[4] - bb[1], 2)}
    elif op == "conform_normals":
        cmds.polyNormal(mesh, nm=2, unm=0, ch=False)
    elif op == "reverse_normals":
        cmds.polyNormal(mesh, nm=0, unm=0, ch=False)
    elif op == "harden":
        cmds.polyNormalPerVertex(mesh, ufn=True)
        cmds.polySoftEdge(mesh, a=num("angle", 30), ch=False)
    elif op == "remesh":
        cleanup(mesh, 0.0)
        cmds.polyRemesh(mesh, maxEdgeLength=num("size", 1.0), collapseThreshold=20, smoothStrength=0, tessellateBorders=True)
        cmds.delete(mesh, ch=True)
    elif op == "relax":
        cmds.polyAverageVertex(mesh, i=int(num("rounds", 3)), ch=False)
    elif op == "bevel":
        cmds.select(mesh + ".e[*]", r=True)
        cmds.polySelectConstraint(m=2, t=0x8000, a=1, ab=(num("angle", 40), 180))
        hard = cmds.ls(sl=True, fl=True) or []
        constraint_off()
        if hard:
            cmds.polyBevel3(hard, fraction=0.5, offsetAsFraction=False, offset=num("width", 0.2), segments=int(num("segments", 1)),
                            autoFit=True, chamfer=True, ch=False)
        did = {"edges": len(hard)}
    elif op == "center_pivot":
        cmds.xform(mesh, cp=True)
        cmds.makeIdentity(mesh, apply=True, t=True, r=True, s=True)
    else:
        fail(f"no mesh tool called {op} (see maya_mesh.json)")
    return mesh, did


def export(mesh, out):
    if not cmds.pluginInfo("fbxmaya", q=True, loaded=True):
        cmds.loadPlugin("fbxmaya")
    os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
    cmds.select(mesh, r=True)
    mel.eval("FBXResetExport")
    mel.eval("FBXExportSmoothingGroups -v true")
    mel.eval('FBXExport -f "%s" -s' % out.replace("\\", "/"))
    if not os.path.isfile(out):
        fail(f"Maya wrote no {out}")


if __name__ == "__main__":
    if len(sys.argv) < 4:
        fail("usage: maya_mesh.py <op> <model> <out.fbx> [key=value ...]")
    op, src, out = sys.argv[1], sys.argv[2], sys.argv[3]
    a = dict(x.split("=", 1) for x in sys.argv[4:] if "=" in x)
    if not os.path.isfile(src):
        fail(f"no model at {src}")
    import maya.standalone
    maya.standalone.initialize(name="python")
    import maya.cmds as cmds
    import maya.mel as mel
    cmds.currentUnit(linear="cm")
    try:
        mesh = load(src)
        before = counts(mesh)
        mesh, did = run(op, mesh, a)
        after = counts(mesh)
        export(mesh, out)
        print("AMAL_INFO " + json.dumps({"op": op, "out": out, "before": before, "after": after, **did}))
    except SystemExit:
        raise
    except Exception as e:
        fail(f"{op}: {type(e).__name__}: {str(e).strip()[:400]}")
    finally:
        try:
            maya.standalone.uninitialize()
        except Exception:
            pass
