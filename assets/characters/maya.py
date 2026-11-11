"""Maya, Job & People Scout: energetic recruiter with curly hair in a high ponytail (a pencil through it),
amber utility overshirt open over a white tee, dark jeans, white sneakers and a crossbody bag."""

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from toolkit import (  # noqa: E402
    Blob, Body, Character, Face, Head, V, add_face_features, build, hairline, lerp, paint, ring_around,
    rounded_box, sweep,
)

SKIN = paint("#ad7652", 0.5)
HAIR = paint("#2c1b12", 0.8)
PENCIL = paint("#f0bf2c", 0.5)
ERASER = paint("#e49a9a", 0.8)
GRAPHITE = paint("#2a2a2a", 0.4)
TEE = paint("#f2f1ed", 0.9)
OVERSHIRT = paint("#cc7a1c", 0.85, sheen=0.3)
OVERSHIRT_DARK = paint("#a9620f", 0.8)
BUTTON = paint("#3b2a1a", 0.4)
JEANS = paint("#2b3956", 0.85)
SNEAKERS = paint("#f1f0ec", 0.6)
SOLE = paint("#cfcfca", 0.8)
LEATHER = paint("#8a5a35", 0.5)
LEATHER_DARK = paint("#6b4426", 0.5)
HAIR_TIE = paint("#1a1a1d", 0.5)

OVERSHIRT_SLEEVE = 0.86


def scalp_field(n) -> float:
    return hairline(n, front=0.6, side=0.05, back=-0.32, temples=0.05, ear_clearance=0.22)


def make_maya() -> Character:
    body = Body(height=1.65, feminine=True, shoulder=0.16, chest=(0.136, 0.096), waist=(0.108, 0.079),
                pelvis=(0.152, 0.1), bust=0.046, neck=0.047, upper_arm=0.037, forearm=0.031, wrist=0.022,
                hand=0.88, thigh=0.079, knee=0.047, calf=0.05, ankle=0.027, head=(0.069, 0.093, 0.108))
    maya = Character("Maya", body)
    j, k = maya.j, body.k
    maya.body_skin(SKIN)

    face = Face(skin=SKIN, lips=paint("#8c4d44", 0.45), iris=paint("#2e1d12", 0.2), brows=HAIR,
                jaw=0.2, chin=0.7, nose=0.75, brow_ridge=0.4, cheekbones=1.2, lip_fullness=1.25,
                brow_thickness=0.0028, brow_angle=-0.2, eye_size=1.08)
    head = Head(j["head_center"], body.head, face)
    maya.add(head.bm.copy(), SKIN, "Head")
    add_face_features(maya, head)

    # Curly hair pulled up: a bumpy scalp layer and a big curly ponytail on top.
    maya.add(head.shell(scalp_field, lambda n: 0.006 + 0.005 * max(0.0, n.z), soft=0.06, roughness=0.004,
                        grain=(170, 170, 170)), HAIR, "Head")
    rng = random.Random(7)
    puff = Blob("Ponytail", resolution=0.008)
    path = [(0.06, 1.755, 0.026), (0.09, 1.80, 0.034), (0.135, 1.805, 0.044), (0.17, 1.76, 0.042),
            (0.185, 1.70, 0.034), (0.18, 1.645, 0.024)]
    for (y1, z1, r1), (y2, z2, r2) in zip(path, path[1:]):
        for _ in range(9):
            t = rng.random()
            center = V((0, lerp(y1, y2, t) * k, lerp(z1, z2, t) * k))
            r = lerp(r1, r2, t)
            jitter = V((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-1, 1))) * r * 0.55
            puff.ball(center + jitter, rng.uniform(0.45, 0.62) * r)
    maya.add(puff.to_bmesh(), HAIR, "Head")
    base = V((0, 0.07 * k, 1.77 * k))
    maya.add(sweep(ring_around(base, V((0, 0.4, 1)), 0.022, 14), 0.004, segments=6, closed=True), HAIR_TIE, "Head")

    # Pencil stuck through the ponytail.
    a, b = V((-0.075, 0.13 * k, 1.80 * k)), V((0.07, 0.115 * k, 1.775 * k))
    maya.add(sweep([a, b], 0.0042, segments=6), PENCIL, "Head")
    maya.add(sweep([b, b + (b - a).normalized() * 0.012], [0.0042, 0.0042], segments=6), ERASER, "Head")
    maya.add(sweep([a, a - (b - a).normalized() * 0.014], [0.0042, 0.0006], segments=6), GRAPHITE, "Head")

    # White tee under an amber utility overshirt, worn open.
    maya.top(TEE, extra=0.007, hem=0.9, sleeve=0.4, short_sleeve=True, neckline=1.455)

    def open_front(c) -> bool:
        return c.y < 0 and c.z > 0.84 * k and abs(c.x) < 0.028 + max(0.0, c.z - 1.0 * k) * 0.16

    front = maya.top(OVERSHIRT, extra=0.019, hem=0.84, sleeve=OVERSHIRT_SLEEVE, opening=open_front)
    for side in (1, -1):
        pocket, normal = front.front(0.075 * side, 1.27 * k)
        maya.add(rounded_box(pocket + normal * 0.003, (0.05, 0.005, 0.055), bevel=0.15), OVERSHIRT)
        maya.add(rounded_box(pocket + normal * 0.006 + V((0, 0, 0.024)), (0.053, 0.004, 0.016), bevel=0.2), OVERSHIRT_DARK)
        maya.add(rounded_box(pocket + normal * 0.009 + V((0, 0, 0.02)), (0.008, 0.003, 0.008), bevel=0.45), BUTTON)
    for s in ("L", "R"):
        maya.cuff(s, OVERSHIRT_SLEEVE, OVERSHIRT_DARK, extra=0.019, thickness=0.008)

    # Crossbody bag: strap from her left shoulder across to a bag at her right hip.
    strap = [V((0.09, 0.07, 1.45 * k)), V((0.11, 0.0, 1.455 * k))]
    for x, z in ((0.09, 1.39), (0.035, 1.27), (-0.035, 1.15), (-0.1, 1.03)):
        point, normal = front.front(x, z * k)
        strap.append(point + normal * 0.012)
    bag_center = V((-0.165, -0.035, 0.96 * k))
    strap.append(bag_center + V((0.02, -0.01, 0.06)))
    maya.add(sweep(strap, 0.007, segments=6, flat=0.3, up_hint=V((0, -1, 0))), LEATHER_DARK)
    maya.add(rounded_box(bag_center, (0.05, 0.15, 0.115), bevel=0.3), LEATHER)
    maya.add(rounded_box(bag_center + V((-0.022, 0, 0.025)), (0.012, 0.152, 0.07), bevel=0.3), LEATHER_DARK)

    maya.trousers(JEANS, top=1.0, extra=0.011)
    maya.shoes(SNEAKERS, SOLE, sole_height=0.026, height=0.075)
    return maya


build(make_maya)
