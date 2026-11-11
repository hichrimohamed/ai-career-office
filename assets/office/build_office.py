"""The AI Career Office as a 3D scene: room, four workstations with chairs and props, lounge corner.

Coordinates in this script are the web scene's (three.js: Y up, the back wall at z = -7, desks at
frontend/src/office.ts DESK_POSITIONS), converted to Blender's Z-up on the way in, so everything lines
up with the workers and the wall boards the web app draws itself.

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

DESKS = {  # agent id: desk centre (three.js x, z), same order as the web app
    "content": (-3.0, -2.0),
    "optimizer": (3.0, -2.0),
    "scout": (-3.0, 2.5),
    "coach": (3.0, 2.5),
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
             emission_texture: bpy.types.Image | None = None) -> bpy.types.Material:
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


def build_office() -> None:
    oak = wood_image("oak_floor", (0.72, 0.53, 0.36), planks=8)
    desk_oak = wood_image("desk_oak", (0.78, 0.6, 0.42), planks=4)
    floor = material("Floor", roughness=0.55, texture=oak)
    wall = material("Wall", "#ebe5da", 0.92)
    baseboard = material("Baseboard", "#5e4a3c", 0.6)
    frame_white = material("WindowFrame", "#f2f1ee", 0.45)
    glass = material("Daylight", "#cfe2f5", 0.15, emission="#d6e8ff", strength=1.6)
    desk_top = material("DeskTop", roughness=0.45, texture=desk_oak)
    steel = material("Steel", "#2e3237", 0.38, metallic=0.85)
    chrome = material("Chrome", "#c9ccd1", 0.22, metallic=1.0)
    plastic_dark = material("PlasticDark", "#1b1d21", 0.4)
    plastic_mid = material("PlasticMid", "#33363c", 0.5)
    keycaps = material("Keycaps", "#d9dade", 0.55)
    fabric = material("ChairFabric", "#2c333d", 0.95)
    sofa_fabric = material("SofaFabric", "#3d5a6a", 0.95)
    cushion = material("Cushion", "#c9a46a", 0.95)
    rug = material("Rug", "#4b5563", 0.98)
    rug_border = material("RugBorder", "#c9bfae", 0.98)
    shelf_wood = material("ShelfWood", "#7b5b40", 0.6)
    ceramic = material("Ceramic", "#e9e4dc", 0.35)
    terracotta = material("Terracotta", "#b5653d", 0.8)
    leaf = material("Leaf", "#3f7a3a", 0.7)
    leaf_light = material("LeafLight", "#5c9a4b", 0.7)
    soil = material("Soil", "#3a2a1e", 0.95)
    lamp_shade = material("LampShade", "#1e2023", 0.5)
    bulb = material("Bulb", "#fff3d6", 0.3, emission="#ffe2b0", strength=6.0)
    cord = material("Cord", "#111113", 0.6)
    paper = material("Paper", "#f4f1ea", 0.9)
    cork = material("Cork", "#b8915e", 0.95)

    # Room: floor, two walls with baseboards (front and right stay open so the camera can look in).
    box((0, -0.05, 0), (16, 0.1, 14), floor, uv_scale=0.5)
    box((0, 2, -7), (16, 4, 0.2), wall)
    box((-8, 2, 0), (0.2, 4, 14), wall)
    box((0, 0.06, -6.88), (16, 0.12, 0.04), baseboard)
    box((-7.88, 0.06, 0), (0.04, 0.12, 14), baseboard)

    # Daylight windows between the wall boards.
    for x in (-2.5, 2.5):
        window((x, 1.85, -6.89), 1.3, 1.7, "back", glass, frame_white)
    window((-7.89, 1.85, 5.5), 1.5, 1.7, "left", glass, frame_white)

    # Rug under the workstations.
    box((0, 0.004, 0.25), (11, 0.008, 8.6), rug_border)
    box((0, 0.009, 0.25), (10.6, 0.008, 8.2), rug)

    screens = {
        "content": screen_image("screen_content", (0.15, 0.39, 0.92)),
        "optimizer": screen_image("screen_optimizer", (0.09, 0.64, 0.29)),
        "scout": screen_image("screen_scout", (0.85, 0.47, 0.02)),
        "coach": screen_image("screen_coach", (0.58, 0.2, 0.92)),
    }
    for agent, (dx, dz) in DESKS.items():
        workstation(agent, dx, dz, desk_top, steel, chrome, plastic_dark, plastic_mid, keycaps, fabric,
                    material(f"Screen_{agent}", "#111111", 0.2, emission_texture=screens[agent], strength=1.4))
        pendant(dx, dz, lamp_shade, bulb, cord)
    desk_props(paper, cork, ceramic, chrome, plastic_dark, steel, shelf_wood)

    # Low bookshelf under the Jobs board.
    bookshelf((0, 0, -6.68), shelf_wood, paper)

    # Coffee counter on the left wall.
    box((-7.55, 0.45, -0.25), (0.6, 0.9, 1.7), shelf_wood, bevel=0.03)
    box((-7.55, 0.915, -0.25), (0.64, 0.03, 1.74), material("Counter", "#d9d4cb", 0.3))
    box((-7.6, 1.1, -0.65), (0.32, 0.34, 0.28), plastic_dark, bevel=0.08)  # coffee machine
    box((-7.5, 1.0, -0.65), (0.14, 0.03, 0.18), chrome)
    for i, z in enumerate((-0.05, 0.1, 0.25)):
        cylinder((-7.45, 0.98, z), 0.04, 0.1, ceramic, radius_top=0.045)

    # Lounge corner: sofa and coffee table.
    lounge(sofa_fabric, cushion, desk_top, steel)

    # Plants in the corners and by the window.
    for i, (x, z, scale) in enumerate(((-7.3, -6.3, 1.2), (7.3, -6.4, 1.0), (-7.3, 6.4, 1.1), (7.3, 6.3, 0.9),
                                       (-1.25, -6.55, 0.6), (1.25, -6.55, 0.6))):
        plant(x, z, scale, terracotta if i % 2 else ceramic, soil, leaf if i % 3 else leaf_light, seed=i)


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
    rod((dx, 4.2, dz), (dx, 2.62, dz), 0.006, cord)
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


def lounge(fabric, cushion, wood, steel) -> None:
    cx, cz = 5.3, 6.1
    box((cx, 0.22, cz), (2.2, 0.26, 0.85), fabric, bevel=0.15)  # base
    box((cx, 0.42, cz + 0.05), (2.0, 0.14, 0.75), fabric, bevel=0.35)  # seat cushion
    box((cx, 0.65, cz + 0.36), (2.2, 0.6, 0.18), fabric, bevel=0.3)  # back
    for side in (-1, 1):
        box((cx + side * 1.05, 0.48, cz), (0.18, 0.4, 0.85), fabric, bevel=0.3)  # arms
    for i, side in enumerate((-0.55, 0.55)):
        box((cx + side, 0.66, cz + 0.2), (0.42, 0.36, 0.12), cushion if i == 0 else fabric, bevel=0.45,
            rotation=Quaternion((1, 0, 0), math.radians(-14)))
    for i in range(4):
        box((cx + (-0.95 if i < 2 else 0.95), 0.045, cz + (-0.33 if i % 2 else 0.33)), (0.05, 0.09, 0.05), steel)
    # Coffee table with a plant-free top: a magazine and a cup.
    tx, tz = 5.3, 4.9
    box((tx, 0.4, tz), (1.1, 0.04, 0.6), wood, bevel=0.1, uv_scale=1.2)
    for sx in (-0.5, 0.5):
        for sz in (-0.25, 0.25):
            rod((tx + sx, 0.38, tz + sz), (tx + sx, 0.0, tz + sz), 0.015, steel)
    box((tx - 0.2, 0.425, tz), (0.22, 0.008, 0.3), material("Magazine", "#c84b31", 0.5), rotation=yaw(0.3))


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
    camera.location = T(9, 9, 11)
    camera.rotation_euler = (T(0, 0.5, 0) - camera.location).to_track_quat("-Z", "Y").to_euler()
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
