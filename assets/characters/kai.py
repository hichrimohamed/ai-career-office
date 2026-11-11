"""Kai, Career Coach: broad-shouldered former hiring manager, close-cropped hair graying at the temples,
light stubble, purple athletic zip jacket over a dark tee, whistle on a lanyard, smartwatch, track pants."""

import math
import os
import sys

from mathutils import geometry

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from toolkit import (  # noqa: E402
    Body, Character, Face, Head, V, add_face_features, build, hairline, paint, rounded_box, sweep,
)

SKIN = paint("#b27b58", 0.5)
HAIR = paint("#2a231f", 0.75)
GRAY_HAIR = paint("#6e6a66", 0.75)
STUBBLE = paint("#8c664f", 0.85)
TEE = paint("#24252b", 0.9)
JACKET = paint("#5f2aa6", 0.55)
STRIPE = paint("#f1f0f3", 0.6)
METAL = paint("#c9ccd1", 0.25, metallic=1.0)
CORD = paint("#151518", 0.6)
PANTS = paint("#1d1e23", 0.75)
SNEAKERS = paint("#59606a", 0.6)
SOLE = paint("#efefec", 0.8)
WATCH = paint("#101012", 0.3)


def crop_field(n) -> float:
    return hairline(n, front=0.6, side=0.08, back=-0.4, temples=0.13, ear_clearance=0.25)


def stubble_field(n) -> float:
    edge = -0.45 + 0.4 * max(0.0, abs(n.x) - 0.3) ** 1.3 - n.z
    lips = 0.25 * math.exp(-((n.x / 0.27) ** 2 + ((n.z + 0.62) / 0.09) ** 2)) if n.y < -0.5 else 0.0
    return min(edge - lips, 0.45 - n.y)


def make_kai() -> Character:
    body = Body(height=1.86, shoulder=0.2, chest=(0.172, 0.112), waist=(0.142, 0.096), pelvis=(0.152, 0.1),
                neck=0.064, upper_arm=0.053, forearm=0.044, wrist=0.029, hand=1.08, thigh=0.088, knee=0.056,
                calf=0.06, ankle=0.035, head=(0.077, 0.1, 0.118))
    kai = Character("Kai", body)
    j, k = kai.j, body.k
    kai.body_skin(SKIN)

    face = Face(skin=SKIN, lips=paint("#8f5a4c", 0.5), iris=paint("#3a2a20", 0.2), brows=HAIR,
                jaw=1.0, chin=1.15, nose=1.1, brow_ridge=1.3, cheekbones=0.9, brow_thickness=0.0036,
                brow_angle=0.35)
    head = Head(j["head_center"], body.head, face)
    kai.add(head.bm.copy(), SKIN, "Head")
    add_face_features(kai, head)

    def gray_temples(c) -> bool:
        n = head.norm(c)
        return abs(n.x) > 0.78 and n.z < 0.32

    kai.add(head.shell(crop_field, lambda n: 0.0026 + 0.003 * max(0.0, n.z), soft=0.08, roughness=0.0007,
                       grain=(300, 300, 300), solid=0.002), HAIR, "Head", regions=[(gray_temples, GRAY_HAIR)])
    kai.add(head.shell(stubble_field, lambda n: 0.0009, soft=0.12, solid=0), STUBBLE, "Head")

    # Dark tee under a purple athletic jacket, zip a little open at the top, white stripes down the sleeves.
    kai.top(TEE, extra=0.007, hem=0.9, sleeve=0.45, short_sleeve=True, neckline=1.46)
    zip_top = 1.33 * k

    def v_neck(c) -> bool:
        return c.y < 0 and c.z > zip_top and abs(c.x) < (c.z - zip_top) * 0.38

    def sleeve_stripe(c) -> bool:
        for s, side in (("L", 1), ("R", -1)):
            shoulder, wrist = j[f"{s}_shoulder"], j[f"{s}_wrist"]
            closest, t = geometry.intersect_point_line(c, shoulder, wrist)
            if 0.05 < t < 0.98:
                radial = (c - closest).normalized()
                up_out = V((math.sin(math.radians(45)) * side, 0, math.cos(math.radians(45))))
                if radial.dot(up_out) > 0.975:
                    return True
        return False

    front = kai.top(JACKET, extra=0.02, hem=0.9, sleeve=0.96, opening=v_neck, regions=[(sleeve_stripe, STRIPE)])
    for s in ("L", "R"):
        kai.cuff(s, 0.96, JACKET, extra=0.02, thickness=0.007)
    for side in (1, -1):  # collar edges of the open zip
        edge = []
        for i in range(5):
            z = zip_top + (1.4 * k - zip_top) * i / 4
            point, normal = front.front(((z - zip_top) * 0.38 + 0.006) * side, z)
            edge.append(point + normal * 0.003)
        kai.add(sweep(edge, 0.006, segments=6, flat=0.5), JACKET)
    zipper = []
    for z in (zip_top, 1.2 * k, 1.05 * k, 0.92 * k):
        point, normal = front.front(0, z)
        zipper.append(point + normal * 0.002)
    kai.add(sweep(zipper, 0.0028, segments=6), METAL)

    # Whistle on a cord.
    whistle, normal = front.front(0.0, 1.27 * k)
    for side in (1, -1):
        cord = [V((0.05 * side, 0.05, 1.49 * k)), V((0.075 * side, -0.02, 1.47 * k))]
        for x, z in ((0.06, 1.42), (0.03, 1.34)):
            point, n = front.front(x * side, z * k)
            cord.append(point + n * 0.004)
        cord.append(whistle + normal * 0.012 + V((0, 0, 0.02)))
        kai.add(sweep(cord, 0.0022, segments=5), CORD)
    kai.add(rounded_box(whistle + normal * 0.014, (0.036, 0.02, 0.018), bevel=0.45), METAL)
    kai.add(sweep([whistle + normal * 0.014 + V((0.018, 0, 0)), whistle + normal * 0.014 + V((0.03, 0, 0.004))],
                  0.006, segments=8), METAL)

    kai.watch("L", WATCH, WATCH)

    def pant_stripe(c) -> bool:
        for s, side in (("L", 1), ("R", -1)):
            hip, ankle = j[f"{s}_hip"], j[f"{s}_ankle"]
            closest, t = geometry.intersect_point_line(c, hip, ankle)
            if 0.0 < t < 1.0 and (c - closest).normalized().dot(V((side, 0, 0))) > 0.97:
                return True
        return False

    kai.trousers(PANTS, top=1.02, extra=0.014, regions=[(pant_stripe, STRIPE)])
    kai.shoes(SNEAKERS, SOLE, sole_height=0.027, height=0.078)
    return kai


build(make_kai)
