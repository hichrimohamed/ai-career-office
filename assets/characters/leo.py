"""Leo, Profile Optimizer: ex-recruiter in a green quarter-zip with rolled sleeves, trimmed beard,
swept-back hair, and the old recruiter badge he still wears on a lanyard."""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from toolkit import (  # noqa: E402
    Body, Character, Face, Head, V, add_face_features, build, ellipsoid, hairline, paint, rounded_box, sweep,
)

SKIN = paint("#d9a585", 0.55)
HAIR = paint("#1e1714", 0.72)
BEARD = paint("#2e221b", 0.75)
SWEATER = paint("#4a7a3c", 0.95, sheen=0.4)
TEE = paint("#ece9e2", 0.9)
METAL = paint("#c3c6cb", 0.3, metallic=1.0)
LANYARD = paint("#454a52", 0.8)
BADGE = paint("#f3f1ec", 0.5)
BADGE_PHOTO = paint("#7d90a6", 0.6)
TROUSERS = paint("#30323a", 0.85)
SHOES = paint("#2b211c", 0.45)
SOLE = paint("#16120f", 0.7)

SLEEVE_END = 0.42  # sleeves pushed up to here along the forearm


def hair_field(n) -> float:
    return hairline(n, front=0.6, side=0.0, back=-0.45, temples=0.09, ear_clearance=0.25)


def hair_thickness(n) -> float:
    """Short at the sides, volume on top, swept up at the front."""
    top = max(0.0, n.z) ** 1.5
    front = max(0.0, n.z - 0.35) * math.exp(-(((n.y + 0.55) / 0.35) ** 2))
    return 0.003 + 0.02 * top + 0.016 * front


def beard_field(n) -> float:
    """Jaw, chin and moustache below the cheekbones, with the lips left clear."""
    edge = -0.38 + 0.45 * max(0.0, abs(n.x) - 0.25) ** 1.3 - n.z  # cheek line: moustache corners up to sideburns
    lips = 0.25 * math.exp(-((n.x / 0.27) ** 2 + ((n.z + 0.62) / 0.09) ** 2)) if n.y < -0.5 else 0.0
    return min(edge - lips, 0.5 - n.y)


def make_leo() -> Character:
    body = Body(height=1.80, shoulder=0.185, chest=(0.158, 0.102), waist=(0.13, 0.088), pelvis=(0.148, 0.096),
                upper_arm=0.046, forearm=0.039, neck=0.058)
    leo = Character("Leo", body)
    j, k = leo.j, body.k
    leo.body_skin(SKIN)

    face = Face(skin=SKIN, lips=paint("#a8665a", 0.5), iris=paint("#4a2e1c", 0.2), brows=HAIR,
                jaw=0.85, nose=1.05, brow_ridge=1.2, brow_thickness=0.0037, brow_angle=1.0)
    head = Head(j["head_center"], body.head, face)
    leo.add(head.bm.copy(), SKIN, "Head")
    add_face_features(leo, head)
    # Hair strands run front to back: low noise frequency along y, high across.
    leo.add(head.shell(hair_field, hair_thickness, soft=0.1, roughness=0.002, grain=(420, 45, 420)), HAIR, "Head")
    leo.add(head.shell(beard_field, lambda n: 0.0042, soft=0.07, roughness=0.0012, grain=(260, 260, 120),
                       solid=0.002), BEARD, "Head")

    # Green quarter-zip, sleeves pushed up to mid-forearm.
    front = leo.top(SWEATER, extra=0.017, hem=0.92, sleeve=SLEEVE_END)
    for s in ("L", "R"):
        leo.cuff(s, SLEEVE_END, SWEATER, extra=0.017, thickness=0.011)

    neck = body.neck
    leo.add(sweep([V((0, 0.008, 1.44 * k)), V((0, 0.008, 1.51 * k))], [neck + 0.017, neck + 0.009],
                  segments=20, caps=False), SWEATER)  # standing collar
    tee_hit, _ = front.front(0, 1.43 * k)
    leo.add(ellipsoid(tee_hit + V((0, 0.012, 0.02)), (0.022, 0.01, 0.03)), TEE)

    zipper = [V((0, -(neck + 0.014), 1.505 * k))]
    for z in (1.42, 1.37, 1.31):
        point, normal = front.front(0, z * k)
        zipper.append(point + normal * 0.002)
    leo.add(sweep(zipper, 0.0025, segments=6), METAL)
    leo.add(rounded_box(zipper[-1] + V((0, -0.004, -0.008)), (0.008, 0.004, 0.016)), METAL)

    # Lanyard and the old recruiter badge.
    badge, badge_normal = front.front(0, 1.23 * k)
    for side in (1, -1):
        path = [V((0.045 * side, 0.05, 1.47 * k)), V((0.072 * side, -0.01, 1.455 * k))]
        for x, z in ((0.068, 1.41), (0.045, 1.35), (0.018, 1.30)):
            point, normal = front.front(x * side, z * k)
            path.append(point + normal * 0.004)
        path.append(badge + badge_normal * 0.006 + V((0, 0, 0.05)))
        leo.add(sweep(path, 0.0028, segments=6), LANYARD)
    leo.add(rounded_box(badge + V((0, -0.008, 0.045)), (0.012, 0.006, 0.016)), METAL)
    leo.add(rounded_box(badge + V((0, -0.008, 0.0)), (0.056, 0.004, 0.08), bevel=0.15), BADGE)
    leo.add(rounded_box(badge + V((0, -0.0105, 0.012)), (0.026, 0.002, 0.026), bevel=0.1), BADGE_PHOTO)

    leo.trousers(TROUSERS, top=1.02, extra=0.01)
    leo.shoes(SHOES, SOLE)
    return leo


build(make_leo)
