"""gltf_in - read a glTF / GLB model straight into Maya (Maya has no glTF importer of its own), no other program.

    import gltf_in; xforms = gltf_in.load("model.glb", tex_dir="scenes")

Plain Python + Maya's API, so it runs in mayapy on the Mac and the PC alike. Brings in every triangle primitive of every
node in the default scene with its node transforms, positions and UVs (TEXCOORD_0), seams welded, each primitive's
base-colour texture as a lambert, in centimetres (glTF is metres, Y up - Maya's up too). Returns the new transforms.
Skins, morph targets and animation in the file are not read: the rig tool rigs the static mesh.
"""
import base64
import json
import os
import struct

import maya.api.OpenMaya as om
import maya.cmds as cmds

_FMT = {5120: "b", 5121: "B", 5122: "h", 5123: "H", 5125: "I", 5126: "f"}
_N = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def _read(path):
    data = open(path, "rb").read()
    if data[:4] == b"glTF":
        length = struct.unpack_from("<I", data, 8)[0]
        off, doc, bin_chunk = 12, None, None
        while off < length:
            n, kind = struct.unpack_from("<II", data, off)
            chunk = data[off + 8: off + 8 + n]
            if kind == 0x4E4F534A:
                doc = json.loads(chunk.decode("utf-8"))
            elif kind == 0x004E4942:
                bin_chunk = chunk
            off += 8 + n
        return doc, bin_chunk
    return json.loads(data.decode("utf-8")), None


def _buffers(doc, bin_chunk, base):
    out = []
    for b in doc.get("buffers", []):
        uri = b.get("uri")
        if uri is None:
            out.append(bin_chunk or b"")
        elif uri.startswith("data:"):
            out.append(base64.b64decode(uri.split(",", 1)[1]))
        else:
            out.append(open(os.path.join(base, uri), "rb").read())
    return out


def _view(doc, bufs, i):
    v = doc["bufferViews"][i]
    start = v.get("byteOffset", 0)
    return bufs[v["buffer"]][start: start + v["byteLength"]], v.get("byteStride")


def _accessor(doc, bufs, i):
    a = doc["accessors"][i]
    fmt, n, count = _FMT[a["componentType"]], _N[a["type"]], a["count"]
    if "bufferView" not in a:
        return [[0] * n for _ in range(count)]
    raw, stride = _view(doc, bufs, a["bufferView"])
    size = struct.calcsize("<" + fmt)
    stride = stride or size * n
    off = a.get("byteOffset", 0)
    rows = [list(struct.unpack_from("<" + fmt * n, raw, off + k * stride)) for k in range(count)]
    if a.get("normalized") and fmt != "f":
        top = float((1 << (8 * size - (1 if fmt.islower() else 0))) - 1)
        rows = [[x / top for x in r] for r in rows]
    return rows


def _mul(a, b):
    return [sum(a[r * 4 + k] * b[k * 4 + c] for k in range(4)) for r in range(4) for c in range(4)]


def _local(node):
    """The node's matrix, row-major, column vectors (p' = M p)."""
    if "matrix" in node:
        m = node["matrix"]                      # glTF stores column-major
        return [m[c * 4 + r] for r in range(4) for c in range(4)]
    tx, ty, tz = node.get("translation", (0, 0, 0))
    x, y, z, w = node.get("rotation", (0, 0, 0, 1))
    sx, sy, sz = node.get("scale", (1, 1, 1))
    r = [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w),
         2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w),
         2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]
    return [r[0] * sx, r[1] * sy, r[2] * sz, tx,
            r[3] * sx, r[4] * sy, r[5] * sz, ty,
            r[6] * sx, r[7] * sy, r[8] * sz, tz,
            0, 0, 0, 1]


def _apply(m, p, w=1.0):
    return [m[0] * p[0] + m[1] * p[1] + m[2] * p[2] + m[3] * w,
            m[4] * p[0] + m[5] * p[1] + m[6] * p[2] + m[7] * w,
            m[8] * p[0] + m[9] * p[1] + m[10] * p[2] + m[11] * w]


def _texture(doc, bufs, base, mat_i, tex_dir, cache):
    """A lambert with the material's base-colour image (written out next to the scene), or None."""
    if mat_i is None or mat_i in cache:
        return cache.get(mat_i)
    mat = doc.get("materials", [])[mat_i]
    pbr = mat.get("pbrMetallicRoughness", {})
    sh = cmds.shadingNode("lambert", asShader=True, n="gltfMat%d" % mat_i)
    col = pbr.get("baseColorFactor")
    if col:
        cmds.setAttr(sh + ".color", col[0], col[1], col[2], type="double3")
    t = pbr.get("baseColorTexture")
    if t is not None and tex_dir:
        img = doc["images"][doc["textures"][t["index"]]["source"]]
        if "bufferView" in img:
            raw = _view(doc, bufs, img["bufferView"])[0]
            ext = ".jpg" if "jpeg" in img.get("mimeType", "") else ".png"
            path = os.path.abspath(os.path.join(tex_dir, "gltf_tex%d%s" % (mat_i, ext)))
            os.makedirs(tex_dir, exist_ok=True)
            open(path, "wb").write(raw)
        elif img.get("uri", "").startswith("data:"):
            path = os.path.abspath(os.path.join(tex_dir, "gltf_tex%d.png" % mat_i))
            os.makedirs(tex_dir, exist_ok=True)
            open(path, "wb").write(base64.b64decode(img["uri"].split(",", 1)[1]))
        else:
            path = os.path.join(base, img.get("uri", ""))
        f = cmds.shadingNode("file", asTexture=True, n="gltfTex%d" % mat_i)
        cmds.setAttr(f + ".fileTextureName", path.replace("\\", "/"), type="string")
        cmds.connectAttr(f + ".outColor", sh + ".color", force=True)
    sg = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, n=sh + "SG")
    cmds.connectAttr(sh + ".outColor", sg + ".surfaceShader", force=True)
    cache[mat_i] = sg
    return sg


def load(path, tex_dir=None, scale=100.0):
    """Bring the model in; returns the transforms made (one per primitive)."""
    doc, bin_chunk = _read(path)
    base = os.path.dirname(os.path.abspath(path))
    bufs = _buffers(doc, bin_chunk, base)
    nodes = doc.get("nodes", [])
    scene = doc.get("scenes", [{}])[doc.get("scene", 0)] if doc.get("scenes") else {"nodes": list(range(len(nodes)))}
    made, mats = [], {}
    stack = [(i, [scale, 0, 0, 0, 0, scale, 0, 0, 0, 0, scale, 0, 0, 0, 0, 1]) for i in scene.get("nodes", [])]
    while stack:
        i, parent = stack.pop()
        node = nodes[i]
        world = _mul(parent, _local(node))
        stack += [(c, world) for c in node.get("children", [])]
        if "mesh" not in node:
            continue
        for prim in doc["meshes"][node["mesh"]]["primitives"]:
            if prim.get("mode", 4) != 4 or "POSITION" not in prim["attributes"]:
                continue
            att = prim["attributes"]
            pos = [_apply(world, p) for p in _accessor(doc, bufs, att["POSITION"])]
            idx = [r[0] for r in _accessor(doc, bufs, prim["indices"])] if "indices" in prim else list(range(len(pos)))
            tris = len(idx) // 3
            fn = om.MFnMesh()
            obj = fn.create([om.MPoint(*p) for p in pos], [3] * tris, idx[: tris * 3])
            if "TEXCOORD_0" in att:
                uv = _accessor(doc, bufs, att["TEXCOORD_0"])
                fn.setUVs([u for u, v in uv], [1.0 - v for u, v in uv])     # glTF V runs down
                fn.assignUVs([3] * tris, idx[: tris * 3])
            xf = om.MFnDagNode(obj).fullPathName() if obj.hasFn(om.MFn.kTransform) else om.MFnDagNode(obj).partialPathName()
            xf = cmds.ls(xf, long=True)[0]
            shape = (cmds.listRelatives(xf, shapes=True, fullPath=True) or [xf])[0]
            sg = _texture(doc, bufs, base, prim.get("material"), tex_dir, mats)
            cmds.sets(shape, edit=True, forceElement=sg or "initialShadingGroup")
            made.append(cmds.rename(xf, "gltfMesh%d" % len(made)))
    if not made:
        raise RuntimeError("no triangle mesh in " + path)
    for m in made:
        # glTF splits vertices along UV and normal seams: welded again, or the skin tears open along every seam
        # (Maya keeps the UVs per face corner); edges under 80 degrees smooth, sharper ones stay hard
        cmds.polyMergeVertex(m, d=scale * 1e-5, ch=False)
        cmds.polySoftEdge(m, a=80, ch=False)
    return made
