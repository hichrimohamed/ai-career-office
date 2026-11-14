"""The AI Career Office as a 3D floor: four department offices off a central corridor, one per agent.

    North row:  Content Studio (Nora)  |  Profile Lab (Leo)
                ------------ corridor (Career Profile board at the west end) ------------
    South row:  Scouting Desk (Maya)   |  Coaching Room (Kai)

Each office has a glass front on the corridor with a door, a sign and a floor label in the department's
colour, an accent wall, a rug, the agent's workstation and themed props. The walls facing the default
camera (south and east) are cut down to knee height so you can look in, like a dollhouse.

Coordinates in this script are the web scene's (three.js: Y up), converted to Blender's Z-up on the way
in, so everything lines up with the workers and the wall boards the web app draws itself
(frontend/src/office.ts DESK_POSITIONS and the board positions in frontend/src/main.ts).

    Blender --factory-startup -b -P assets/office/build_office.py -- --out frontend/public/models/office.glb [--preview <png>]
"""

from __future__ import annotations

import argparse
import math
import random
import sys

import bmesh
import bpy
from mathutils import Matrix, Quaternion, Vector, noise

# Floor plan (three.js x, z). The building spans x -HALF_W..HALF_W and z -OUTER_Z..OUTER_Z.
HALF_W = 6.5          # each office is HALF_W wide; the partition between east and west offices is at x = 0
CORRIDOR = 1.8        # the corridor runs along x for |z| < CORRIDOR
OUTER_Z = 6.8         # offices are OUTER_Z - CORRIDOR = 5 m deep
WALL_H = 3.0
KNEE_H = 0.95         # height of the cut-down walls facing the camera
WALL_T = 0.12

DESKS = {  # agent id: desk centre (three.js x, z), same order as the web app. Workers face -z.
    "content": (-4.2, -5.2),
    "optimizer": (4.2, -5.2),
    "scout": (-4.2, 3.4),
    "coach": (4.2, 3.4),
}
DEPARTMENTS = {  # agent id: (sign, agent name, accent colour = the worker colour in frontend/src/main.ts)
    "content": ("CONTENT STUDIO", "Nora", "#2563eb"),
    "optimizer": ("PROFILE LAB", "Leo", "#16a34a"),
    "scout": ("SCOUTING DESK", "Maya", "#d97706"),
    "coach": ("COACHING ROOM", "Kai", "#9333ea"),
}
DESK_TOP = 0.75
SEAT_TOP = 0.52
WORKER_OFFSET = 0.75  # workers sit this far in front of their desk centre (+z)


def T(x: float, y: float, z: float) -> Vector:
    """three.js position (Y up) -> Blender (Z up)."""
    return Vector((x, -z, y))


def S(sx: float, sy: float, sz: float) -> Vector:
    """three.js size -> Blender size."""
    return Vector((sx, sz, sy))


def yaw(radians: float) -> Quaternion:
    """Rotation about the web scene's vertical axis."""
    return Quaternion((0, 0, 1), radians)


# --- Materials and generated textures -------------------------------------------------------------

_materials: dict[str, bpy.types.Material] = {}


def _linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def rgb(hex_color: str) -> tuple[float, float, float, float]:
    h = hex_color.lstrip("#")
    return (*[_linear(int(h[i : i + 2], 16) / 255) for i in (0, 2, 4)], 1.0)


def material(name: str, color: str = "#ffffff", roughness: float = 0.7, metallic: float = 0.0,
             emission: str | None = None, strength: float = 1.0, texture: bpy.types.Image | None = None,
             emission_texture: bpy.types.Image | None = None, alpha: float = 1.0) -> bpy.types.Material:
    if name in _materials:
        return _materials[name]
    mat = bpy.data.materials.new(name)
    if hasattr(mat, "use_nodes") and not mat.use_nodes:
        mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = rgb(color)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    if texture:
        tex = nodes.new("ShaderNodeTexImage")
        tex.image = texture
        links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    if emission or emission_texture:
        bsdf.inputs["Emission Strength"].default_value = strength
        if emission_texture:
            tex = nodes.new("ShaderNodeTexImage")
            tex.image = emission_texture
            links.new(tex.outputs["Color"], bsdf.inputs["Emission Color"])
            links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
        else:
            bsdf.inputs["Emission Color"].default_value = rgb(emission)
    if alpha < 1.0:  # exported as a glTF alphaMode BLEND material
        bsdf.inputs["Alpha"].default_value = alpha
        for attr, value in (("surface_render_method", "BLENDED"), ("blend_method", "BLEND")):
            try:
                setattr(mat, attr, value)
                break
            except (AttributeError, TypeError):
                continue
    mat.diffuse_color = rgb(color)
    _materials[name] = mat
    return mat


def image(name: str, width: int, height: int, pixel) -> bpy.types.Image:
    """Make an image from pixel(x, y) -> (r, g, b) in 0..1 sRGB, packed so the GLB embeds it."""
    img = bpy.data.images.new(name, width, height, alpha=False)
    pixels = [0.0] * (width * height * 4)
    for y in range(height):
        for x in range(width):
            r, g, b = pixel(x, y)
            i = (y * width + x) * 4
            pixels[i : i + 4] = (r, g, b, 1.0)
    img.pixels[:] = pixels
    img.file_format = "PNG"
    img.pack()
    return img


def wood_image(name: str, base: tuple[float, float, float], planks: int, size: int = 256) -> bpy.types.Image:
    """Oak planks running along x: per-plank tone, fine grain, dark seams."""
    rng = random.Random(name)
    tones = [rng.uniform(0.86, 1.1) for _ in range(planks)]
    plank_h = size / planks

    def pixel(x: int, y: int):
        plank = int(y / plank_h)
        seam = (y % plank_h) < 1.2 or ((x + plank * 97) % size) < 1.2
        grain = noise.noise(Vector((x * 0.012 + plank * 7.1, y * 0.35, plank)))
        rings = 0.5 + 0.5 * math.sin(x * 0.05 + grain * 6 + plank * 3)
        shade = tones[plank] * (0.9 + 0.08 * grain + 0.06 * rings) * (0.55 if seam else 1.0)
        return tuple(min(1.0, c * shade) for c in base)

    return image(name, size, size, pixel)


def screen_image(name: str, accent: tuple[float, float, float]) -> bpy.types.Image:
    """A dark app window: sidebar, title bar in the agent's colour, lines of text, one card."""
    rng = random.Random(name)
    width, height = 192, 112
    lines = [(rng.randint(56, 70), rng.randint(90, 175)) for _ in range(12)]

    def pixel(x: int, y: int):
        yy = height - 1 - y
        if yy < 10:
            return accent
        if x < 40:
            return (0.09, 0.1, 0.12) if (yy // 12) % 2 or x < 6 else (0.13, 0.14, 0.17)
        if 120 < x < 182 and 18 < yy < 58:
            return tuple(0.25 + 0.5 * c for c in accent) if yy < 24 else (0.17, 0.18, 0.22)
        row = (yy - 16) // 8
        if 0 <= row < len(lines) and (yy - 16) % 8 < 3:
            start, end = lines[row]
            if start < x < min(end, 116 if 18 < yy < 58 else end):
                return (0.55, 0.58, 0.64)
        return (0.06, 0.065, 0.08)

    return image(name, width, height, pixel)


# --- Geometry --------------------------------------------------------------------------------------

objects: list[bpy.types.Object] = []


def emit(bm: bmesh.types.BMesh, mat: bpy.types.Material, uv_scale: float | None = None, smooth: bool = False):
    if uv_scale is not None:
        planar_uvs(bm, uv_scale)
    mesh = bpy.data.meshes.new(mat.name)
    bm.to_mesh(mesh)
    bm.free()
    mesh.materials.append(mat)
    mesh.polygons.foreach_set("use_smooth", [smooth] * len(mesh.polygons))
    obj = bpy.data.objects.new(mat.name, mesh)
    bpy.context.collection.objects.link(obj)
    objects.append(obj)
    return obj


def planar_uvs(bm: bmesh.types.BMesh, scale: float) -> None:
    """Box-style UVs: each face projected along its dominant normal axis."""
    layer = bm.loops.layers.uv.verify()
    for face in bm.faces:
        n = face.normal
        axis = max(range(3), key=lambda i: abs(n[i]))
        u_axis, v_axis = [(1, 2), (0, 2), (0, 1)][axis]
        for loop in face.loops:
            loop[layer].uv = (loop.vert.co[u_axis] * scale, loop.vert.co[v_axis] * scale)


def box(center3, size3, mat, rotation: Quaternion | None = None, bevel: float = 0.0, uv_scale=None):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    if bevel:
        bmesh.ops.bevel(bm, geom=bm.verts[:] + bm.edges[:], offset=bevel, offset_type="PERCENT", segments=3,
                        affect="EDGES")
    bmesh.ops.transform(bm, matrix=Matrix.LocRotScale(T(*center3), rotation or Quaternion(), S(*size3)), verts=bm.verts)
    bm.normal_update()
    return emit(bm, mat, uv_scale, smooth=bool(bevel))


def cylinder(center3, radius: float, height: float, mat, radius_top: float | None = None, segments: int = 24,
             rotation: Quaternion | None = None, caps: bool = True):
    """Vertical (web Y) cylinder or cone, centred at center3."""
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=caps, cap_tris=False, segments=segments, radius1=radius,
                          radius2=radius if radius_top is None else radius_top, depth=height,
                          matrix=Matrix.LocRotScale(T(*center3), rotation or Quaternion(), Vector((1, 1, 1))))
    return emit(bm, mat, smooth=True)


def rod(a3, b3, radius: float, mat, segments: int = 10):
    a, b = T(*a3), T(*b3)
    axis = b - a
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=segments, radius1=radius, radius2=radius,
                          depth=axis.length,
                          matrix=Matrix.LocRotScale((a + b) / 2, Vector((0, 0, 1)).rotation_difference(axis), Vector((1, 1, 1))))
    return emit(bm, mat, smooth=True)


def sphere(center3, radii3, mat, rotation: Quaternion | None = None, segments: int = 16, rings: int = 10):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=segments, v_segments=rings, radius=1.0,
                              matrix=Matrix.LocRotScale(T(*center3), rotation or Quaternion(), S(*radii3)))
    return emit(bm, mat, smooth=True)


def torus(center3, major: float, minor: float, mat, rotation: Quaternion | None = None, segments: int = 24):
    bm = bmesh.new()
    rings = []
    for i in range(segments):
        a = 2 * math.pi * i / segments
        ring = []
        for j in range(8):
            b = 2 * math.pi * j / 8
            ring.append(bm.verts.new(((major + minor * math.cos(b)) * math.cos(a), (major + minor * math.cos(b)) * math.sin(a),
                                      minor * math.sin(b))))
        rings.append(ring)
    for i in range(segments):
        r1, r2 = rings[i], rings[(i + 1) % segments]
        for j in range(8):
            bm.faces.new((r1[j], r1[(j + 1) % 8], r2[(j + 1) % 8], r2[j]))
    bmesh.ops.transform(bm, matrix=Matrix.LocRotScale(T(*center3), rotation or Quaternion(), Vector((1, 1, 1))), verts=bm.verts)
    bm.normal_update()
    return emit(bm, mat, smooth=True)


# --- The office -------------------------------------------------------------------------------------


M: dict[str, bpy.types.Material] = {}  # shared materials, filled by build_office()


def mix_hex(a: str, b: str, t: float) -> str:
    """Blend two sRGB hex colours: t = 0 gives a, t = 1 gives b."""
    ca = [int(a.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4)]
    cb = [int(b.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4)]
    return "#" + "".join(f"{round(x * (1 - t) + y * t):02x}" for x, y in zip(ca, cb))


def local(cx: float, cz: float, angle: float):
    """Position helper for furniture turned by `angle` about the vertical axis (same sense as yaw())."""
    c, s = math.cos(angle), math.sin(angle)
    return lambda dx, y, dz: (cx + dx * c + dz * s, y, cz - dx * s + dz * c)


def facing(dx: float, dz: float) -> float:
    """The yaw that turns an object's local -z (its front) toward the direction (dx, dz)."""
    return math.atan2(-dx, -dz)


def text(body: str, center3, size: float, mat, rotation: Quaternion | None = None, extrude: float = 0.004):
    """3D lettering, converted to a mesh so it merges and exports like everything else.
    With no rotation it lies flat on the floor, reading along +x for a camera on the +z side."""
    curve = bpy.data.curves.new(f"Text {body}", "FONT")
    curve.body = body
    curve.size = size
    curve.align_x = "CENTER"
    curve.align_y = "CENTER"
    curve.extrude = extrude
    curve.materials.append(mat)
    obj = bpy.data.objects.new(f"Text {body}", curve)
    bpy.context.collection.objects.link(obj)
    obj.location = T(*center3)
    obj.rotation_mode = "QUATERNION"
    obj.rotation_quaternion = rotation or Quaternion()
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.convert(target="MESH")
    obj = bpy.context.view_layer.objects.active
    objects.append(obj)
    return obj


UPRIGHT = Quaternion((1, 0, 0), math.pi / 2)  # text standing up, readable from +z
FACE = {  # rotations for upright signs readable from each direction
    "+z": UPRIGHT,
    "-z": Quaternion((0, 0, 1), math.pi) @ UPRIGHT,
    "+x": Quaternion((0, 0, 1), math.pi / 2) @ UPRIGHT,
}


def build_office() -> None:
    oak = wood_image("oak_floor", (0.72, 0.53, 0.36), planks=8)
    desk_oak = wood_image("desk_oak", (0.78, 0.6, 0.42), planks=4)
    M.update(
        floor=material("Floor", roughness=0.55, texture=oak),
        concrete=material("Concrete", "#b9b6b0", 0.35),
        slab=material("Slab", "#55585e", 0.8),
        wall=material("Wall", "#ebe5da", 0.92),
        cap=material("WallCap", "#3a3d43", 0.5),
        frame=material("GlassFrame", "#26282c", 0.35, metallic=0.6),
        window_frame=material("WindowFrame", "#f2f1ee", 0.45),
        daylight=material("Daylight", "#cfe2f5", 0.15, emission="#d6e8ff", strength=1.6),
        glass=material("Glass", "#dcebf0", 0.05, alpha=0.16),
        desk_top=material("DeskTop", roughness=0.45, texture=desk_oak),
        steel=material("Steel", "#2e3237", 0.38, metallic=0.85),
        chrome=material("Chrome", "#c9ccd1", 0.22, metallic=1.0),
        dark=material("PlasticDark", "#1b1d21", 0.4),
        mid=material("PlasticMid", "#33363c", 0.5),
        keycaps=material("Keycaps", "#d9dade", 0.55),
        fabric=material("ChairFabric", "#2c333d", 0.95),
        shelf_wood=material("ShelfWood", "#7b5b40", 0.6),
        ceramic=material("Ceramic", "#e9e4dc", 0.35),
        terracotta=material("Terracotta", "#b5653d", 0.8),
        leaf=material("Leaf", "#3f7a3a", 0.7),
        leaf_light=material("LeafLight", "#5c9a4b", 0.7),
        soil=material("Soil", "#3a2a1e", 0.95),
        paper=material("Paper", "#f4f1ea", 0.9),
        cork=material("Cork", "#b8915e", 0.95),
        title=material("FloorTitle", "#f4f1ea", 0.5),
    )

    shell()
    screens = {agent: screen_image(f"screen_{agent}", tuple(int(accent[i : i + 2], 16) / 255 for i in (1, 3, 5)))
               for agent, (_, _, accent) in DEPARTMENTS.items()}
    lamp_shade = material("LampShade", "#1e2023", 0.5)
    bulb = material("Bulb", "#fff3d6", 0.3, emission="#ffe2b0", strength=6.0)
    cord = material("Cord", "#111113", 0.6)
    for agent, (dx, dz) in DESKS.items():
        department(agent)
        workstation(agent, dx, dz, M["desk_top"], M["steel"], M["chrome"], M["dark"], M["mid"], M["keycaps"],
                    M["fabric"], material(f"Screen_{agent}", "#111111", 0.2, emission_texture=screens[agent],
                                          strength=1.4))
        pendant(dx, dz, lamp_shade, bulb, cord)
    desk_props(M["paper"], M["cork"], M["ceramic"], M["chrome"], M["dark"], M["steel"], M["shelf_wood"])

    content_studio()
    profile_lab()
    scouting_desk()
    coaching_room()
    corridor()


def shell() -> None:
    """Plinth, floors and the walls shared by the four offices."""
    w, d = 2 * HALF_W, 2 * OUTER_Z
    box((0, -0.2, 0), (w + 0.8, 0.3, d + 0.8), M["slab"])
    box((0, -0.05, 0), (w, 0.1, 2 * CORRIDOR), M["concrete"])
    for sx in (-1, 1):
        for sz in (-1, 1):
            box((sx * HALF_W / 2, -0.05, sz * (CORRIDOR + OUTER_Z) / 2), (HALF_W, 0.1, OUTER_Z - CORRIDOR),
                M["floor"], uv_scale=0.5)

    wall, room_d = M["wall"], OUTER_Z - CORRIDOR
    # Full-height walls at the back (north) and the far side (west), and the partition between offices.
    box((0, WALL_H / 2, -OUTER_Z), (w + WALL_T, WALL_H, WALL_T), wall)
    box((-HALF_W, WALL_H / 2, 0), (WALL_T, WALL_H, d + WALL_T), wall)
    north_z = -(CORRIDOR + OUTER_Z) / 2
    box((0, WALL_H / 2, north_z), (WALL_T, WALL_H, room_d), wall)
    box((0, WALL_H + 0.01, north_z), (WALL_T + 0.02, 0.02, room_d), M["cap"])
    # Between the two south offices the partition is glass, so the camera sees into both.
    z0, z1 = CORRIDOR, OUTER_Z - WALL_T / 2
    box((0, WALL_H / 2, (z0 + z1) / 2), (0.02, WALL_H, z1 - z0), M["glass"])
    box((0, WALL_H - 0.03, (z0 + z1) / 2), (0.07, 0.06, z1 - z0), M["frame"])
    box((0, 0.025, (z0 + z1) / 2), (0.07, 0.05, z1 - z0), M["frame"])
    for i in range(5):
        box((0, WALL_H / 2, z0 + i * (z1 - z0) / 4), (0.07, WALL_H, 0.05), M["frame"])
    box((0, WALL_H + 0.01, -OUTER_Z), (w + WALL_T + 0.02, 0.02, WALL_T + 0.02), M["cap"])
    box((-HALF_W, WALL_H + 0.01, 0), (WALL_T + 0.02, 0.02, d + WALL_T + 0.02), M["cap"])

    # Walls facing the camera (south, and east beside the offices) are cut to knee height.
    box((0, KNEE_H / 2, OUTER_Z), (w + WALL_T, KNEE_H, WALL_T), wall)
    box((0, KNEE_H + 0.015, OUTER_Z), (w + WALL_T + 0.04, 0.03, WALL_T + 0.04), M["cap"])
    for sz in (-1, 1):
        cz = sz * (CORRIDOR + OUTER_Z) / 2
        box((HALF_W, KNEE_H / 2, cz), (WALL_T, KNEE_H, room_d), wall)
        box((HALF_W, KNEE_H + 0.015, cz), (WALL_T + 0.04, 0.03, room_d + 0.04), M["cap"])

    # Glass fronts on the corridor, with a door near the partition.
    for agent in DESKS:
        sx = -1 if agent in ("content", "scout") else 1
        sz = -1 if agent in ("content", "optimizer") else 1
        glass_front(agent, sx, sz * CORRIDOR)


def glass_front(agent: str, sx: int, z: float) -> None:
    """Glass wall from the partition (x = 0) to the outer wall at x = sx * HALF_W, door 0.4..1.4 m from the partition."""
    sign_name, person, accent = DEPARTMENTS[agent]
    glow = material(f"Glow_{agent}", accent, 0.4, emission=accent, strength=2.2)
    band = material(f"Accent_{agent}", accent, 0.5)
    door0, door1, door_h = 0.4, 1.4, 2.3
    xs = lambda u: sx * u  # distance from the partition -> world x
    for u0, u1 in ((0.06, door0), (door1, HALF_W - 0.06)):
        box((xs((u0 + u1) / 2), WALL_H / 2, z), (u1 - u0, WALL_H, 0.02), M["glass"])
        # Frosted band in the department colour at eye level, like the reference HQ.
        if u1 - u0 > 1:
            box((xs((u0 + u1) / 2 + 0.2), 1.3, z), (u1 - u0 - 0.6, 0.1, 0.03), band)
    box((xs((door0 + door1) / 2), (door_h + WALL_H) / 2, z), (door1 - door0, WALL_H - door_h, 0.02), M["glass"])
    box((xs(HALF_W / 2), WALL_H - 0.03, z), (HALF_W, 0.06, 0.07), M["frame"])
    box((xs((door0 + door1) / 2), door_h, z), (door1 - door0, 0.05, 0.07), M["frame"])
    for u0, u1 in ((0.06, door0), (door1, HALF_W - 0.06)):
        box((xs((u0 + u1) / 2), 0.025, z), (u1 - u0, 0.05, 0.07), M["frame"])
    posts = [door0, door1] + [door1 + i * (HALF_W - door1) / 4 for i in range(1, 4)]
    for u in posts:
        box((xs(u), WALL_H / 2, z), (0.05, WALL_H, 0.07), M["frame"])

    # Sign over the door, on the corridor side, and the department name on the corridor floor.
    out = 1 if z < 0 else -1  # which way the corridor is: +z for the north offices
    sign_z = z + out * 0.06
    sign_x = xs(1.9)
    box((sign_x, 2.66, sign_z), (2.6, 0.36, 0.04), M["dark"])
    text(f"{sign_name}  ·  {person}", (sign_x, 2.66, sign_z + out * 0.025), 0.15, glow,
         FACE["+z" if out > 0 else "-z"], extrude=0.003)
    text(sign_name, (xs(HALF_W / 2), 0.004, z + out * 0.5), 0.34, glow, extrude=0.002)


def department(agent: str) -> None:
    """The parts every office has: an accent wall behind its board, a rug and a plant by the door."""
    _, _, accent = DEPARTMENTS[agent]
    paint = material(f"Paint_{agent}", mix_hex(accent, "#ebe5da", 0.62), 0.9)
    rug = material(f"Rug_{agent}", mix_hex(accent, "#d8d2c6", 0.72), 0.98)
    rug_border = material(f"RugBorder_{agent}", mix_hex(accent, "#3a3d43", 0.35), 0.98)
    face = WALL_T / 2 + 0.005
    room_d = OUTER_Z - CORRIDOR
    if agent == "content":  # back wall of the west half
        box((-HALF_W / 2, WALL_H / 2, -OUTER_Z + face), (HALF_W - WALL_T, WALL_H, 0.01), paint)
    elif agent == "optimizer":
        box((HALF_W / 2, WALL_H / 2, -OUTER_Z + face), (HALF_W - WALL_T, WALL_H, 0.01), paint)
    elif agent == "scout":  # west wall
        box((-HALF_W + face, WALL_H / 2, (CORRIDOR + OUTER_Z) / 2), (0.01, WALL_H, room_d - WALL_T), paint)

    dx, dz = DESKS[agent]
    box((dx, 0.004, dz + 0.3), (3.0, 0.008, 2.6), rug_border)
    box((dx, 0.009, dz + 0.3), (2.8, 0.008, 2.4), rug)


# --- The four departments -------------------------------------------------------------------------


def content_studio() -> None:
    """Nora, north-west: a writer's desk under the window, a bookshelf, and a recording corner."""
    window((-4.6, 1.75, -OUTER_Z + 0.08), 1.8, 1.7, "back", M["daylight"], M["window_frame"])
    window((-HALF_W + 0.08, 1.75, -3.2), 1.8, 1.7, "left", M["daylight"], M["window_frame"])
    bookshelf((-4.6, 0, -6.5), M["shelf_wood"], M["paper"])

    # Recording corner: a stool lit by a ring light, a camera on a tripod pointing at it.
    stool((-1.0, -4.3))
    ring = material("RingLight", "#fff8ec", 0.3, emission="#fff4e0", strength=4.0)
    rx, rz = -2.6, -3.2
    tripod(rx, rz, 1.45)
    q = yaw(facing(-1.0 - rx, -4.3 - rz)) @ Quaternion((1, 0, 0), math.pi / 2)
    torus((rx, 1.6, rz), 0.3, 0.035, ring, rotation=q, segments=32)
    cx, cz = -1.9, -2.7
    tripod(cx, cz, 1.25)
    p = local(cx, cz, facing(-1.0 - cx, -4.3 - cz))
    box(p(0, 1.33, 0), (0.22, 0.15, 0.14), M["dark"], rotation=yaw(facing(-1.0 - cx, -4.3 - cz)), bevel=0.15)
    rod(p(0, 1.34, -0.07), p(0, 1.34, -0.2), 0.045, M["mid"])
    plant(-5.9, -2.35, 1.1, M["ceramic"], M["soil"], M["leaf"], seed=1)


def profile_lab() -> None:
    """Leo, north-east: a headshot corner (backdrop, stool, softbox) for the profile photo."""
    window((4.6, 1.75, -OUTER_Z + 0.08), 1.8, 1.7, "back", M["daylight"], M["window_frame"])

    backdrop = material("Backdrop", "#8f99a6", 0.95)
    bx, z0, z1, top = 0.32, -4.75, -2.55, 2.4
    for z in (z0, z1):
        rod((bx, 0, z), (bx, top, z), 0.02, M["steel"])
        cylinder((bx, 0.01, z), 0.14, 0.02, M["steel"])
    rod((bx, top, z0 - 0.05), (bx, top, z1 + 0.05), 0.045, backdrop)
    box((bx + 0.03, (top + 0.3) / 2, (z0 + z1) / 2), (0.01, top - 0.3, z1 - z0 - 0.1), backdrop)
    box((bx + 0.95, 0.012, (z0 + z1) / 2), (0.7, 0.01, z1 - z0 - 0.1), backdrop)
    stool((1.15, -3.65))

    # Softbox on a stand, aimed at the stool.
    sx, sz = 2.7, -2.55
    tripod(sx, sz, 1.55)
    turn = facing(1.15 - sx, -3.65 - sz)
    p = local(sx, sz, turn)
    box(p(0, 1.7, 0), (0.62, 0.62, 0.3), M["dark"], rotation=yaw(turn), bevel=0.05)
    box(p(0, 1.7, -0.155), (0.56, 0.56, 0.01), material("Softbox", "#ffffff", 0.4, emission="#fff6e8", strength=3.0),
        rotation=yaw(turn))
    plant(5.9, -2.35, 1.0, M["terracotta"], M["soil"], M["leaf_light"], seed=2)


def scouting_desk() -> None:
    """Maya, south-west: a telescope at the window, a globe, filing cabinets of leads."""
    _, _, accent = DEPARTMENTS["scout"]
    brass = material("Brass", "#b08d4a", 0.35, metallic=0.9)

    # Telescope on a tripod, looking out over the low wall.
    tx, tz = -2.4, 5.9
    tripod(tx, tz, 1.05)
    tube = material("Telescope", mix_hex(accent, "#1b1d21", 0.25), 0.35)
    rod((tx, 1.08, tz - 0.35), (tx + 0.12, 1.42, tz + 0.45), 0.065, tube)
    rod((tx, 1.08, tz - 0.35), (tx - 0.02, 1.02, tz - 0.48), 0.025, M["dark"])

    # Globe on a stand.
    gx, gz = -1.0, 5.8
    cylinder((gx, 0.02, gz), 0.2, 0.04, M["shelf_wood"])
    rod((gx, 0.04, gz), (gx, 0.8, gz), 0.025, brass)
    sphere((gx, 1.05, gz), (0.26, 0.26, 0.26), material("Globe", "#3b78b8", 0.4), segments=24, rings=14)
    torus((gx, 1.05, gz), 0.3, 0.012, brass, rotation=Quaternion((1, 0, 0), math.pi / 2), segments=32)
    for i in range(6):  # continents
        a = i * 1.1
        sphere((gx + 0.24 * math.cos(a), 1.05 + 0.12 * math.sin(i * 2.3), gz + 0.24 * math.sin(a)),
               (0.08, 0.06, 0.08), material("Land", "#5c9a4b", 0.6))

    # Filing cabinets against the partition, drawers facing into the room (-x).
    grey = material("Cabinet", "#8b929b", 0.45, metallic=0.3)
    for z in (3.0, 3.62):
        box((-0.36, 0.65, z), (0.58, 1.3, 0.6), grey, bevel=0.02)
        for k in range(4):
            y = 0.18 + k * 0.31
            box((-0.655, y, z), (0.01, 0.27, 0.54), grey)
            box((-0.67, y + 0.07, z), (0.02, 0.025, 0.14), M["chrome"])
            box((-0.665, y + 0.07, z + 0.12), (0.01, 0.05, 0.06), M["paper"])
    plant(-5.9, 6.35, 1.0, M["terracotta"], M["soil"], M["leaf"], seed=3)


def coaching_room() -> None:
    """Kai, south-east: two armchairs facing each other for mock interviews, a side table, a water cooler."""
    _, _, accent = DEPARTMENTS["coach"]
    upholstery = material("Armchair", mix_hex(accent, "#3a3d43", 0.45), 0.95)
    armchair(1.55, 5.75, -math.pi / 2, upholstery)  # facing +x
    armchair(3.65, 5.75, math.pi / 2, upholstery)  # facing -x
    cylinder((2.6, 0.55, 6.15), 0.28, 0.03, M["desk_top"], segments=32)
    rod((2.6, 0.54, 6.15), (2.6, 0.02, 6.15), 0.025, M["steel"])
    cylinder((2.6, 0.015, 6.15), 0.18, 0.03, M["steel"])
    for dx in (-0.08, 0.1):
        cylinder((2.6 + dx, 0.62, 6.1), 0.035, 0.11, material("Water", "#bfe3f5", 0.05), segments=16)
    box((2.45, 0.572, 6.25), (0.16, 0.01, 0.22), M["paper"], rotation=yaw(0.3))

    # Rolling stand for the Coaching board (the web app draws the board face), in front of Kai's desk.
    bx, bz, half = DESKS["coach"][0], 2.2, 1.65
    for side in (-1, 1):
        x = bx + side * half
        box((x, 1.42, bz), (0.05, 2.84, 0.05), M["steel"])
        box((x, 0.04, bz), (0.06, 0.04, 0.6), M["steel"])
        for end in (-1, 1):
            sphere((x, 0.03, bz + end * 0.27), (0.03, 0.03, 0.03), M["dark"])
    box((bx, 0.5, bz), (2 * half, 0.04, 0.04), M["steel"])

    # Water cooler by the east wall.
    wx, wz = 6.05, 5.0
    box((wx, 0.5, wz), (0.36, 1.0, 0.36), M["ceramic"], bevel=0.05)
    cylinder((wx, 1.22, wz), 0.15, 0.44, material("Water", "#bfe3f5", 0.05), segments=24)
    box((wx - 0.19, 0.85, wz), (0.03, 0.05, 0.08), M["mid"])
    plant(5.9, 6.35, 1.15, M["ceramic"], M["soil"], M["leaf_light"], seed=4)


def corridor() -> None:
    """The title on the floor, a welcome mat and plants at the open east end."""
    text("AI CAREER OFFICE", (0.6, 0.004, 0), 0.42, M["title"], extrude=0.002)
    box((HALF_W - 0.45, 0.006, 0), (0.7, 0.012, 1.8), material("Mat", "#3a3d43", 0.98))
    for sz in (-1, 1):
        plant(HALF_W - 0.35, sz * (CORRIDOR - 0.3), 0.9, M["terracotta"], M["soil"], M["leaf"], seed=5 + sz)


# --- Furniture ---------------------------------------------------------------------------------------


def tripod(x: float, z: float, top: float) -> None:
    for i in range(3):
        a = 2 * math.pi * i / 3 + 0.4
        rod((x, top - 0.25, z), (x + math.cos(a) * 0.32, 0.0, z + math.sin(a) * 0.32), 0.012, M["steel"])
    rod((x, top - 0.3, z), (x, top, z), 0.016, M["steel"])


def stool(xz) -> None:
    x, z = xz
    cylinder((x, 0.62, z), 0.2, 0.05, M["fabric"], segments=24)
    cylinder((x, 0.35, z), 0.025, 0.5, M["chrome"])
    cylinder((x, 0.02, z), 0.22, 0.03, M["chrome"], segments=24)
    torus((x, 0.3, z), 0.17, 0.01, M["chrome"])


def armchair(cx: float, cz: float, angle: float, fabric) -> None:
    """Lounge armchair; a sitter faces local -z, turned by `angle`."""
    p, q = local(cx, cz, angle), yaw(angle)
    box(p(0, 0.24, 0), (0.82, 0.26, 0.78), fabric, rotation=q, bevel=0.15)
    box(p(0, 0.42, -0.02), (0.62, 0.12, 0.66), fabric, rotation=q, bevel=0.35)
    box(p(0, 0.68, 0.32), (0.82, 0.58, 0.16), fabric, rotation=q, bevel=0.3)
    for side in (-1, 1):
        box(p(side * 0.36, 0.52, 0), (0.12, 0.34, 0.78), fabric, rotation=q, bevel=0.3)
        for end in (-1, 1):
            box(p(side * 0.33, 0.05, end * 0.3), (0.05, 0.1, 0.05), M["steel"], rotation=q)


def window(center3, width: float, height: float, wall: str, glass, frame) -> None:
    """A window on the back wall (spans x) or the left wall (spans z); dn is toward the room."""
    cx, cy, cz = center3

    def place(du, dv, dn):
        return (cx + du, cy + dv, cz + dn) if wall == "back" else (cx + dn, cy + dv, cz + du)

    def size(w, h, d):
        return (w, h, d) if wall == "back" else (d, h, w)

    t = 0.06
    box(place(0, 0, 0), size(width, height, 0.02), glass)
    box(place(0, height / 2, 0.02), size(width + t, t, 0.06), frame)
    box(place(0, -height / 2, 0.02), size(width + t, t, 0.06), frame)
    box(place(-width / 2, 0, 0.02), size(t, height, 0.06), frame)
    box(place(width / 2, 0, 0.02), size(t, height, 0.06), frame)
    box(place(0, 0, 0.02), size(0.035, height, 0.05), frame)  # mullion
    box(place(0, height * 0.1, 0.02), size(width, 0.035, 0.05), frame)  # transom
    box(place(0, -height / 2 - 0.05, 0.08), size(width + 0.16, 0.04, 0.16), frame)  # sill


def workstation(agent, dx, dz, desk_top, steel, chrome, plastic_dark, plastic_mid, keycaps, fabric, screen) -> None:
    # Desk: oak top on a two-leg steel frame.
    box((dx, DESK_TOP - 0.02, dz), (2.0, 0.04, 1.0), desk_top, bevel=0.04, uv_scale=1.2)
    for side in (-1, 1):
        x = dx + side * 0.9
        box((x, (DESK_TOP - 0.04) / 2, dz), (0.05, DESK_TOP - 0.04, 0.06), steel)
        box((x, 0.02, dz), (0.07, 0.04, 0.8), steel)
        box((x, DESK_TOP - 0.06, dz), (0.07, 0.03, 0.85), steel)
    box((dx, 0.45, dz - 0.38), (1.75, 0.45, 0.02), steel)  # modesty panel

    # Monitor on a stand, facing the chair.
    mz = dz - 0.3
    box((dx, DESK_TOP + 0.005, mz), (0.24, 0.012, 0.18), plastic_dark, bevel=0.3)
    box((dx, DESK_TOP + 0.16, mz + 0.01), (0.05, 0.3, 0.025), plastic_mid)
    box((dx, DESK_TOP + 0.34, mz + 0.03), (0.64, 0.38, 0.028), plastic_dark, bevel=0.06)
    box((dx, DESK_TOP + 0.345, mz + 0.046), (0.6, 0.34, 0.004), screen)

    # Keyboard and mouse.
    box((dx, DESK_TOP + 0.012, dz + 0.27), (0.44, 0.022, 0.14), plastic_mid, bevel=0.15)
    box((dx, DESK_TOP + 0.025, dz + 0.27), (0.41, 0.008, 0.115), keycaps)
    sphere((dx + 0.32, DESK_TOP + 0.014, dz + 0.28), (0.032, 0.018, 0.055), plastic_dark)

    # Office chair: five-star base on casters, gas lift, seat, backrest.
    cx, cz = dx, dz + WORKER_OFFSET
    for i in range(5):
        a = 2 * math.pi * i / 5 + 0.3
        foot = (cx + math.cos(a) * 0.3, 0.07, cz + math.sin(a) * 0.3)
        rod((cx, 0.1, cz), foot, 0.018, steel)
        sphere((foot[0], 0.035, foot[2]), (0.028, 0.028, 0.028), plastic_dark)
    cylinder((cx, 0.28, cz), 0.025, 0.36, chrome)
    cylinder((cx, 0.12, cz), 0.04, 0.06, plastic_dark)
    box((cx, SEAT_TOP - 0.04, cz + 0.02), (0.5, 0.08, 0.48), fabric, bevel=0.25)
    box((cx, SEAT_TOP - 0.1, cz + 0.02), (0.36, 0.04, 0.36), plastic_dark)
    rod((cx, SEAT_TOP - 0.06, cz + 0.25), (cx, 0.78, cz + 0.29), 0.018, steel)
    box((cx, 0.92, cz + 0.3), (0.46, 0.5, 0.06), fabric, rotation=Quaternion((1, 0, 0), math.radians(-8)), bevel=0.3)
    for side in (-1, 1):
        rod((cx + side * 0.24, SEAT_TOP - 0.06, cz + 0.08), (cx + side * 0.25, 0.68, cz + 0.08), 0.012, steel)
        box((cx + side * 0.25, 0.69, cz + 0.05), (0.06, 0.03, 0.26), plastic_dark, bevel=0.3)


def pendant(dx, dz, shade, bulb, cord) -> None:
    rod((dx, WALL_H, dz), (dx, 2.62, dz), 0.006, cord)
    cylinder((dx, 2.52, dz), 0.26, 0.2, shade, radius_top=0.07, segments=32)
    sphere((dx, 2.44, dz), (0.07, 0.05, 0.07), bulb)


def desk_props(paper, cork, ceramic, chrome, dark, steel, wood) -> None:
    top = DESK_TOP
    navy = material("PropNavy", "#1f3466", 0.6)
    red = material("PropRed", "#b3201f", 0.4)
    cream = material("PropCream", "#ece4d4", 0.8)
    yellow = material("StickyNote", "#f5e27a", 0.8)
    purple = material("PropPurple", "#6b2fb3", 0.4)
    ruler = material("Ruler", "#d9b77e", 0.6)
    lens = material("Lens", "#cfe4f2", 0.05, metallic=0.2)

    # Nora: "Show, don't claim" mug, index cards with hooks, a stack of books, red pen.
    x, z = DESKS["content"]
    cylinder((x + 0.55, top + 0.05, z + 0.05), 0.04, 0.1, ceramic, segments=20)
    torus((x + 0.6, top + 0.05, z + 0.05), 0.025, 0.007, ceramic, rotation=Quaternion((1, 0, 0), math.pi / 2))
    for i in range(6):
        box((x - 0.55, top + 0.003 + i * 0.003, z + 0.18), (0.13, 0.003, 0.08), paper if i < 5 else cream,
            rotation=yaw(math.radians(i * 3 - 6)))
    for i, (mat, h) in enumerate(((red, 0.035), (cream, 0.03), (navy, 0.04))):
        box((x + 0.78, top + 0.02 + i * 0.037, z - 0.3), (0.2, h, 0.28), mat, rotation=yaw(math.radians(i * 5)), bevel=0.05)
    rod((x + 0.25, top + 0.006, z + 0.28), (x + 0.38, top + 0.006, z + 0.24), 0.005, red)

    # Leo: magnifying glass, stopwatch, ruler, sticky notes.
    x, z = DESKS["optimizer"]
    torus((x - 0.5, top + 0.008, z + 0.22), 0.05, 0.008, dark)
    cylinder((x - 0.5, top + 0.005, z + 0.22), 0.045, 0.004, lens)
    rod((x - 0.45, top + 0.008, z + 0.26), (x - 0.33, top + 0.012, z + 0.33), 0.009, dark)
    cylinder((x + 0.55, top + 0.012, z + 0.1), 0.035, 0.024, chrome, segments=24)
    cylinder((x + 0.55, top + 0.025, z + 0.1), 0.03, 0.003, paper, segments=24)
    cylinder((x + 0.55, top + 0.012, z + 0.06), 0.006, 0.02, chrome, rotation=Quaternion((1, 0, 0), math.pi / 2))
    box((x - 0.15, top + 0.003, z + 0.33), (0.3, 0.004, 0.035), ruler)
    for i in range(3):
        box((x + 0.72 + i * 0.012, top + 0.003 + i * 0.002, z - 0.18 - i * 0.01), (0.075, 0.002, 0.075), yellow,
            rotation=yaw(math.radians(i * 9)))

    # Maya: binoculars, phone, a small pinned map of Europe.
    x, z = DESKS["scout"]
    for side in (-1, 1):
        cylinder((x + 0.55 + side * 0.035, top + 0.03, z + 0.05), 0.028, 0.11, dark,
                 rotation=Quaternion((1, 0, 0), math.pi / 2), segments=16)
    box((x + 0.55, top + 0.03, z + 0.05), (0.04, 0.025, 0.04), dark)
    box((x - 0.5, top + 0.005, z + 0.25), (0.075, 0.008, 0.155), dark, bevel=0.3)
    box((x + 0.8, top + 0.16, z - 0.38), (0.36, 0.28, 0.02), cork, rotation=Quaternion((1, 0, 0), math.radians(-12)))
    for px, py in ((-0.08, 0.04), (0.02, 0.0), (0.09, 0.06), (-0.02, -0.06)):
        sphere((x + 0.8 + px, top + 0.16 + py, z - 0.365), (0.008, 0.008, 0.008), red)

    # Kai: clipboard with a score sheet, timer, water bottle, mini whiteboard.
    x, z = DESKS["coach"]
    box((x - 0.5, top + 0.005, z + 0.2), (0.23, 0.008, 0.31), wood, bevel=0.1)
    box((x - 0.5, top + 0.011, z + 0.21), (0.2, 0.002, 0.26), paper)
    box((x - 0.5, top + 0.016, z + 0.07), (0.08, 0.012, 0.03), chrome, bevel=0.2)
    cylinder((x + 0.55, top + 0.025, z + 0.05), 0.035, 0.05, material("TimerRed", "#d94a3a", 0.4), segments=20)
    cylinder((x + 0.8, top + 0.12, z - 0.2), 0.035, 0.24, purple, segments=20)
    cylinder((x + 0.8, top + 0.25, z - 0.2), 0.025, 0.03, steel, segments=16)
    box((x - 0.8, top + 0.17, z - 0.38), (0.34, 0.24, 0.02), material("Whiteboard", "#f7f7f5", 0.2),
        rotation=Quaternion((1, 0, 0), math.radians(-12)))


def bookshelf(center3, wood, paper) -> None:
    cx, _, cz = center3
    width, height, depth = 2.4, 0.9, 0.35
    box((cx, height / 2, cz), (width, 0.03, depth), wood)
    for y in (0.02, 0.45, height - 0.015):
        box((cx, y, cz), (width, 0.03, depth), wood)
    for x in (-width / 2, -width / 6, width / 6, width / 2):
        box((cx + x, height / 2, cz), (0.03, height, depth), wood)
    rng = random.Random(4)
    colors = ["#1f3466", "#b3201f", "#2f6b3a", "#d9a441", "#e9e4dc", "#5a3d8a", "#2c2c30"]
    books = [material(f"Book{i}", c, 0.7) for i, c in enumerate(colors)]
    for shelf_y in (0.035, 0.465):
        x = cx - width / 2 + 0.05
        while x < cx + width / 2 - 0.08:
            if abs(x - (cx - width / 6)) < 0.03 or abs(x - (cx + width / 6)) < 0.03:
                x += 0.04
                continue
            w, h = rng.uniform(0.025, 0.05), rng.uniform(0.24, 0.34)
            box((x + w / 2, shelf_y + h / 2, cz + 0.02), (w, h, rng.uniform(0.2, 0.26)), rng.choice(books))
            x += w + 0.004
            if rng.random() < 0.12:
                x += 0.12


def plant(x, z, scale, pot, soil, leaf_mat, seed) -> None:
    rng = random.Random(seed)
    h = 0.42 * scale
    cylinder((x, h / 2, z), 0.2 * scale, h, pot, radius_top=0.24 * scale, segments=28)
    cylinder((x, h - 0.02, z), 0.22 * scale, 0.02, soil, segments=28)
    for i in range(16):
        a = 2 * math.pi * i / 16 + rng.uniform(-0.2, 0.2)
        length = rng.uniform(0.35, 0.6) * scale
        lift = rng.uniform(0.55, 1.1)
        center = (x + math.cos(a) * length * 0.45, h + length * 0.45 * lift, z + math.sin(a) * length * 0.45)
        tilt = Quaternion((0, 0, 1), -a) @ Quaternion((1, 0, 0), 0) @ Quaternion((0, 1, 0), math.radians(90 - 50 * lift))
        sphere(center, (length * 0.5, 0.012, length * 0.12), leaf_mat, rotation=tilt, segments=12, rings=6)


# --- Output -------------------------------------------------------------------------------------------


def merge_by_material() -> list[bpy.types.Object]:
    """One mesh per material keeps the web scene's draw calls low."""
    groups: dict[str, list[bpy.types.Object]] = {}
    for obj in objects:
        groups.setdefault(obj.data.materials[0].name, []).append(obj)
    merged = []
    for name, group in groups.items():
        bpy.ops.object.select_all(action="DESELECT")
        for obj in group:
            obj.select_set(True)
        bpy.context.view_layer.objects.active = group[0]
        if len(group) > 1:
            bpy.ops.object.join()
        result = bpy.context.view_layer.objects.active
        result.name = name
        merged.append(result)
    return merged


def render_preview(path: str) -> None:
    scene = bpy.context.scene
    for engine in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        try:
            scene.render.engine = engine
            break
        except TypeError:
            continue
    scene.render.resolution_x, scene.render.resolution_y = 1400, 900
    world = bpy.data.worlds.new("Preview")
    if hasattr(world, "use_nodes"):
        world.use_nodes = True
        bg = world.node_tree.nodes.get("Background")
        if bg:
            bg.inputs["Color"].default_value = (0.75, 0.78, 0.82, 1)
            bg.inputs["Strength"].default_value = 0.6
    scene.world = world
    sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
    sun.data.energy = 3.0
    sun.rotation_euler = (math.radians(50), 0, math.radians(30))
    bpy.context.collection.objects.link(sun)
    camera = bpy.data.objects.new("Camera", bpy.data.cameras.new("Camera"))
    camera.data.lens = 28
    bpy.context.collection.objects.link(camera)
    camera.location = T(10, 13, 14)  # the web app's default view (frontend/src/main.ts)
    camera.rotation_euler = (T(0, 0, 0.5) - camera.location).to_track_quat("-Z", "Y").to_euler()
    scene.camera = camera
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)


def main() -> None:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--preview")
    args = parser.parse_args(argv)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    build_office()
    merged = merge_by_material()
    bpy.ops.object.select_all(action="DESELECT")
    for obj in merged:
        obj.select_set(True)
    bpy.ops.export_scene.gltf(filepath=args.out, export_format="GLB", use_selection=True,
                              export_draco_mesh_compression_enable=True, export_draco_mesh_compression_level=6)
    print(f"[office] exported {args.out}: {len(merged)} meshes, "
          f"{sum(len(o.data.vertices) for o in merged)} vertices")
    if args.preview:
        render_preview(args.preview)


main()
