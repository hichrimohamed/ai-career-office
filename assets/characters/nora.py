"""Nora, Content Strategist: composed senior strategist with a sleek dark bob and a silver streak,
thin black rectangular glasses, a red pen behind her ear, navy blazer over a cream turtleneck."""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from toolkit import (  # noqa: E402
    Body, Character, Face, Head, V, add_face_features, azimuth, build, lerp, paint, ring_around, rounded_box,
    smoothstep, sweep,
)

SKIN = paint("#d6a684", 0.5)
HAIR = paint("#17161b", 0.55)
SILVER = paint("#cfcfd3", 0.5)
FRAMES = paint("#111114", 0.3)
PEN = paint("#b3201f", 0.35)
METAL = paint("#c9ccd1", 0.25, metallic=1.0)
TURTLENECK = paint("#e9e1d1", 0.95, sheen=0.4)
BLAZER = paint("#1f3466", 0.7)
BLAZER_DARK = paint("#18284f", 0.6)
BUTTON = paint("#0f1426", 0.4)
TROUSERS = paint("#2a2b31", 0.8)
LOAFERS = paint("#141416", 0.35)
STRAP = paint("#1c1c1f", 0.5)

BLAZER_SLEEVE = 0.9


def bob_field(n) -> float:
    """Forehead hairline at the front; at the sides and back the hair comes down to the jaw."""
    t = smoothstep(0.17, 0.31, azimuth(n))
    return n.z - lerp(0.62, -0.6, t)


def bob_thickness(n) -> float:
    """Sleek on top, hanging straight down so the lower part stands off the narrowing jaw."""
    return 0.007 + 0.034 * smoothstep(0.35, -0.55, n.z) * smoothstep(0.15, 0.32, azimuth(n))


def make_nora() -> Character:
    body = Body(height=1.72, feminine=True, shoulder=0.165, chest=(0.138, 0.096), waist=(0.11, 0.079),
                pelvis=(0.154, 0.1), bust=0.047, neck=0.048, upper_arm=0.038, forearm=0.032, wrist=0.023,
                hand=0.9, thigh=0.079, knee=0.048, calf=0.05, ankle=0.027, head=(0.07, 0.094, 0.11))
    nora = Character("Nora", body)
    j, k = nora.j, body.k
    nora.body_skin(SKIN)

    face = Face(skin=SKIN, lips=paint("#ad5f58", 0.45), iris=paint("#3b2618", 0.2), brows=HAIR,
                jaw=0.2, chin=0.8, nose=0.78, brow_ridge=0.4, cheekbones=1.3, lip_fullness=1.12,
                brow_thickness=0.0025, brow_angle=-0.4, eye_size=1.05)
    head = Head(j["head_center"], body.head, face)
    nora.add(head.bm.copy(), SKIN, "Head")
    add_face_features(nora, head)

    # Sleek bob with a silver streak on her right, framing the face.
    def streak(c):
        n = head.norm(c)
        return -0.5 < n.x < -0.18 and n.y < 0.2 and n.z > -0.1

    nora.add(head.shell(bob_field, bob_thickness, soft=0.04, roughness=0.0012, grain=(520, 520, 40), solid=0.004),
             HAIR, "Head", regions=[(streak, SILVER)])

    # Thin black rectangular glasses.
    hw = body.head[0]
    lens_w, lens_h = 0.022, 0.0135
    for side in (1, -1):
        eye, _ = head.at(0.41 * side, 0.0)
        center = eye + V((0, -0.013, 0.001))
        corners = []
        for cx, cz in ((1, 1), (-1, 1), (-1, -1), (1, -1)):
            for a in range(4):
                t = math.radians(a * 30 + {(1, 1): 0, (-1, 1): 90, (-1, -1): 180, (1, -1): 270}[(cx, cz)])
                corners.append(center + V(((lens_w - 0.004) * cx + 0.004 * math.cos(t), 0, (lens_h - 0.004) * cz + 0.004 * math.sin(t))))
        nora.add(sweep(corners, 0.0014, segments=5, closed=True), FRAMES, "Head")
        outer = center + V((lens_w * side, 0, 0.004))
        temple = [outer, V((side * (hw + 0.008), outer.y + 0.025, outer.z)),
                  V((side * (hw + 0.009), j["head_center"].y + 0.01, outer.z - 0.004)),
                  V((side * (hw + 0.006), j["head_center"].y + 0.035, outer.z - 0.02))]
        nora.add(sweep(temple, 0.0013, segments=5), FRAMES, "Head")
    left_eye, _ = head.at(0.41, 0.0)
    nora.add(sweep([V((0.009, left_eye.y - 0.016, left_eye.z + 0.006)), V((0, left_eye.y - 0.019, left_eye.z + 0.008)),
                    V((-0.009, left_eye.y - 0.016, left_eye.z + 0.006))], 0.0013, segments=5), FRAMES, "Head")

    # Red pen tucked behind her right ear.
    ear = j["head_center"] + V((-(hw + 0.012), 0.02, 0.025))
    tip, cap = ear + V((0.004, -0.07, 0.035)), ear + V((-0.004, 0.06, -0.02))
    nora.add(sweep([tip, cap], 0.0042, segments=8), PEN, "Head")
    nora.add(sweep([cap.lerp(tip, 0.1), cap.lerp(tip, 0.28)], 0.0012, segments=4), METAL, "Head")

    # Cream turtleneck under a navy blazer with an open V front.
    nora.top(TURTLENECK, extra=0.007, hem=0.9, sleeve=0.97)
    collar_top = 1.495 * k
    nora.add(sweep([V((0, 0.006, 1.42 * k)), V((0, 0.006, collar_top))], [body.neck + 0.02, body.neck + 0.011],
                   segments=22, caps=False), TURTLENECK)
    nora.add(sweep(ring_around(V((0, 0.006, collar_top - 0.006)), V((0, 0, 1)), body.neck + 0.012, 22), 0.007,
                   segments=8, closed=True), TURTLENECK)  # folded top edge

    button_z = 1.1 * k

    def v_opening(c) -> bool:
        if c.y > 0:
            return False
        if c.z > button_z:
            return abs(c.x) < (c.z - button_z) * 0.3
        return abs(c.x) < (button_z - c.z) * 0.18

    front = nora.top(BLAZER, extra=0.021, hem=0.82, sleeve=BLAZER_SLEEVE, opening=v_opening)
    for side in (1, -1):
        lapel = []
        for i in range(7):
            z = lerp(button_z + 0.01, 1.42 * k, i / 6)
            x = (z - button_z) * 0.3 + 0.012
            point, normal = front.front(x * side, z)
            lapel.append(point + normal * 0.003)
        nora.add(sweep(lapel, [lerp(0.008, 0.02, i / 6) for i in range(7)], segments=8, flat=0.18,
                       up_hint=V((0, -1, 0))), BLAZER_DARK)
        pocket, normal = front.front(0.085 * side, 0.94 * k)
        nora.add(rounded_box(pocket + normal * 0.004, (0.07, 0.006, 0.014), bevel=0.2), BLAZER_DARK)
    button, normal = front.front(0.012, button_z)
    nora.add(rounded_box(button + normal * 0.004, (0.012, 0.005, 0.012), bevel=0.45), BUTTON)
    for s in ("L", "R"):
        nora.cuff(s, BLAZER_SLEEVE, BLAZER, extra=0.021, thickness=0.006)
    nora.watch("L", STRAP, METAL)

    nora.trousers(TROUSERS, top=1.0, extra=0.012)
    nora.shoes(LOAFERS, height=0.055)
    return nora


build(make_nora)
