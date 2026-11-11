"""A skeleton's range of motion, checked in MuJoCo (Apache-2.0, pip install mujoco).

In: the plan `amald skeleton` writes ({"height", "joints": [{"name", "parent", "pos", "role", "side"}], ...}).
Each joint turns about three axes within its role's range. Two questions, two sets of capsules:
- at rest, do two bones lie in the same place or cross (a mirrored side that landed on the other, two tails, a limb
  laid inside the trunk)? Thin capsules (1% of the height): only the bones' own lines count, not how thick the body is.
- in motion, how far does each joint turn each way before its part goes through another, and how many mixed poses
  collide? Capsules as thick as that kind of part usually is for the model's height; what already touches at rest
  (the trunk's own parts) is the baseline and not counted.
Nothing here knows any one model: thickness and ranges come from the joint's role.
"""
import argparse, json, math, os, sys

import subprocess

try:
    import numpy as np
    import mujoco
except ImportError:
    # the first use on a machine fetches the engine (a few MB, no graphics card); a system Python that refuses
    # packages takes them for this user only
    for extra in ([], ["--user"], ["--user", "--break-system-packages"]):
        if subprocess.run([sys.executable, "-m", "pip", "install", "-q", *extra, "mujoco", "numpy"]).returncode == 0:
            break
    import numpy as np
    import mujoco

# thickness of a part as a share of the model's height, and the range (degrees, each way) its joint turns, by role
THICK = {"root": .085, "spine": .08, "chest": .09, "neck": .04, "head": .07, "tail": .03, "hip": .045, "knee": .038, "ankle": .03,
         "toes": .022, "scapula": .04, "shoulder": .035, "elbow": .03, "wrist": .022, "finger": .008, "part": .025}
RANGE = {"root": 0, "spine": 25, "chest": 25, "neck": 40, "head": 50, "tail": 50, "hip": 80, "knee": 110, "ankle": 45, "toes": 30,
         "scapula": 20, "shoulder": 100, "elbow": 120, "wrist": 60, "finger": 70, "part": 45}


def build(plan, thin=False):
    joints = plan["joints"]
    h = float(plan.get("height") or 1.0)
    kids = {}
    for j in joints:
        kids.setdefault(j.get("parent"), []).append(j)
    pos = {j["name"]: np.array(j["pos"], float) for j in joints}
    out, bones = [], []

    def body(j, parent_pos, depth):
        p = pos[j["name"]]
        role = j.get("role", "part").replace("_end", "")
        pad = "  " * depth
        out.append(f'{pad}<body name="{j["name"]}" pos="{" ".join(f"{v:.5f}" for v in p - parent_pos)}">')
        r = RANGE.get(role, 45)
        # a joint with no bone after it (the end of a chain) has nothing to turn
        if r and any(np.linalg.norm(pos[c["name"]] - p) >= 1e-6 for c in kids.get(j["name"], [])):
            for ax, v in (("x", "1 0 0"), ("y", "0 1 0"), ("z", "0 0 1")):
                out.append(f'{pad}  <joint name="{j["name"]}.{ax}" type="hinge" axis="{v}" range="{-r} {r}"/>')
        for c in kids.get(j["name"], []):
            a, b = np.zeros(3), pos[c["name"]] - p
            n = float(np.linalg.norm(b))
            if n < 1e-6:
                continue
            rad = (0.01 if thin else THICK.get(role, .025)) * h * 0.5
            # a bone's capsule starts a little way out from its joint, so parts that share a joint do not count as touching
            a2, b2 = b * min(0.2, rad / n), b * max(0.8, 1 - rad / n)
            gname = f'{j["name"]}>{c["name"]}'
            out.append(f'{pad}  <geom name="{gname}" type="capsule" size="{rad:.5f}" fromto="{" ".join(f"{v:.5f}" for v in (*a2, *b2))}"/>')
            bones.append(gname)
        for c in kids.get(j["name"], []):
            body(c, p, depth + 1)
        out.append(f"{pad}</body>")

    for root in kids.get(None, []):
        body(root, np.zeros(3), 2)
    # how many joints apart two joints are (bones a joint or two apart are neighbours: they meet or nearly do)
    par = {j["name"]: j.get("parent") for j in joints}
    def line(n):
        out_ = [n]
        while par.get(out_[-1]):
            out_.append(par[out_[-1]])
        return out_
    def apart(x, y):
        lx, ly = line(x), line(y)
        common = next((n for n in lx if n in ly), None)
        return 99 if common is None else lx.index(common) + ly.index(common)
    build.apart = apart
    xml = ('<mujoco><compiler angle="degree"/><option gravity="0 0 0"/><default><geom contype="1" conaffinity="1"/></default>\n'
           "  <worldbody>\n" + "\n".join(out) + "\n  </worldbody>\n</mujoco>")
    return xml, bones, h


def hits(m, d, deep):
    """Pairs of parts that pass through each other by more than `deep`."""
    mujoco.mj_forward(m, d)
    found = {}
    for i in range(d.ncon):
        c = d.contact[i]
        if c.dist < -deep:
            a, b = m.geom(c.geom1).name, m.geom(c.geom2).name
            # two bones that meet at a joint (one ends where the other starts, or both start there) are neighbours
            ja, jb = a.split(">"), b.split(">")
            if min(build.apart(x, y) for x in ja for y in jb) <= 1:
                continue
            key = tuple(sorted((a, b)))
            found[key] = min(found.get(key, 0.0), float(c.dist))
    return found


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("skeleton")
    ap.add_argument("--out", default="renders/rig_motion.json")
    ap.add_argument("--poses", type=int, default=300)
    ap.add_argument("--min-free", type=float, default=8.0)
    a = ap.parse_args()
    plan = json.load(open(a.skeleton))
    if not plan.get("joints"):
        sys.exit("the skeleton plan has no joints - make it with `amald skeleton <model> <plan.json>`")
    # at rest: the bones' own lines
    xml, bones, h = build(plan, thin=True)
    m = mujoco.MjModel.from_xml_string(xml)
    d = mujoco.MjData(m)
    crossed = hits(m, d, 0.0)
    # in motion: parts as thick as they usually are; what touches at rest is the baseline
    xml, bones, h = build(plan)
    m = mujoco.MjModel.from_xml_string(xml)
    d = mujoco.MjData(m)
    deep = 0.004 * h   # a touch is not a hit: parts must pass through each other by this much
    names = [m.joint(i).name for i in range(m.njnt)]
    rest = hits(m, d, deep)
    # each joint alone, each axis, each way: the first angle at which its part goes through another
    free = {}
    for i, n in enumerate(names):
        joint, axis = n.rsplit(".", 1)
        for sign in (1, -1):
            end = math.degrees(abs(m.jnt_range[i][1 if sign > 0 else 0]))
            reach, hit = end, None
            for step in range(1, 25):
                d.qpos[:] = 0
                d.qpos[m.jnt_qposadr[i]] = math.radians(sign * end * step / 24)
                new = {k: v for k, v in hits(m, d, deep).items() if k not in rest}
                if new:
                    pair = min(new, key=new.get)
                    reach, hit = end * (step - 1) / 24, f"{pair[0]} x {pair[1]}"
                    break
            free.setdefault(joint, {}).setdefault(axis, {})["+" if sign > 0 else "-"] = {"free": round(reach, 1), "hits": hit}
    # mixed poses within half of every range: how often an ordinary pose collides
    rng = np.random.default_rng(7)
    bad, worst = 0, {}
    for _ in range(a.poses):
        d.qpos[:] = rng.uniform(m.jnt_range[:, 0], m.jnt_range[:, 1]) * 0.5
        new = {k: v for k, v in hits(m, d, deep).items() if k not in rest}
        if new:
            bad += 1
            for k in new:
                worst[k] = worst.get(k, 0) + 1
    # a joint is stuck when, about one of its axes, it cannot turn `min_free` either way (turning one way into the
    # other leg or the trunk is how bodies are; having no way to turn is a part laid inside another)
    stuck = []
    for j, axes in sorted(free.items()):
        for ax, ways in axes.items():
            best = max(w["free"] for w in ways.values())
            if best < a.min_free and any(w["hits"] for w in ways.values()):
                w = max(ways.values(), key=lambda w: w["free"])
                stuck.append(f"{j} cannot turn {a.min_free:.0f} degrees either way about {ax} (at most {best:.0f}): {w['hits'] or next(x['hits'] for x in ways.values() if x['hits'])} pass through each other")
    problems = [f"at rest the bones {x} and {y} lie in the same place or cross" for (x, y), v in sorted(crossed.items(), key=lambda kv: kv[1])]
    problems += stuck
    report = {
        "result": "FAIL" if problems else "PASS",
        "problems": problems,
        "joints": len(set(n.rsplit(".", 1)[0] for n in names)), "bones": len(bones), "height": h,
        "at_rest": [{"a": x, "b": y} for (x, y) in crossed],
        "free_range_degrees": {j: f for j, f in sorted(free.items())},
        "mixed_poses": {"tried": a.poses, "colliding": bad, "share": round(bad / max(1, a.poses), 3),
                        "most": [f"{x} x {y} ({n})" for (x, y), n in sorted(worst.items(), key=lambda kv: -kv[1])[:6]]},
        "engine": f"mujoco {mujoco.__version__}",
    }
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    json.dump(report, open(a.out, "w"), indent=1)
    print(f"{report['result']}: {report['joints']} joints, {report['bones']} bones; at rest {len(crossed)} pair(s) of bones in the same place; "
          f"{len(stuck)} joint axis/axes stuck; {bad} of {a.poses} mixed poses collide -> {a.out}")
    for p in problems[:12]:
        print(" -", p)
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
