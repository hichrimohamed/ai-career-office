"""Toolkit for building the office workers as realistic-looking characters in Blender.

Bodies are metaballs (they blend into one smooth surface, like skin over muscle), heads are
sculpted from a sphere with facial landmarks, clothes are separate shells over the body,
and everything is skinned to one shared humanoid skeleton with smooth, joint-blended weights.

The skeleton matches frontend/src/figures.ts (Mixamo-style names, A-pose), so the office's
seating and animation code works for every character.

Run a character script with:
    Blender --factory-startup -b -P assets/characters/<name>.py -- --out <file.glb> [--preview <stem>]
"""

from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass
from typing import Callable, NamedTuple

import bmesh
import bpy
from mathutils import Matrix, Quaternion, Vector, geometry, noise
from mathutils.bvhtree import BVHTree

V = Vector

# Metaball calibration (measured): a ball's surface sits at 0.571 x its radius; balls chained at
# 0.8 x radius spacing swell by about 11%.
BALL_SURFACE = 0.571
CHAIN_SURFACE = BALL_SURFACE * 1.11
MB_RESOLUTION = 0.011


# --- Materials -------------------------------------------------------------------------------


class Paint(NamedTuple):
    """A material description, turned into a Blender material when first used."""

    hex_color: str
    roughness: float = 0.8
    metallic: float = 0.0
    sheen: float = 0.0


def paint(hex_color: str, roughness: float = 0.8, metallic: float = 0.0, sheen: float = 0.0) -> Paint:
    return Paint(hex_color, roughness, metallic, sheen)


_materials: dict[Paint, bpy.types.Material] = {}


def _linear(channel: float) -> float:
    return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4


def blender_material(p: Paint) -> bpy.types.Material:
    if p in _materials:
        return _materials[p]
    srgb = [int(p.hex_color.lstrip("#")[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    rgba = (*[_linear(c) for c in srgb], 1.0)
    mat = bpy.data.materials.new(p.hex_color)
    if hasattr(mat, "use_nodes") and not mat.use_nodes:
        mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = rgba
    bsdf.inputs["Roughness"].default_value = p.roughness
    bsdf.inputs["Metallic"].default_value = p.metallic
    if p.sheen and "Sheen Weight" in bsdf.inputs:
        bsdf.inputs["Sheen Weight"].default_value = p.sheen
    mat.diffuse_color = rgba
    mat.roughness = p.roughness
    _materials[p] = mat
    return mat


# --- Body proportions and skeleton -------------------------------------------------------------


@dataclass
class Body:
    """Proportions. Positions are for a 1.75 m reference and scaled by height; radii are absolute (m)."""

    height: float = 1.75
    feminine: bool = False
    shoulder: float = 0.18  # half distance between shoulder joints
    hip: float = 0.09  # half distance between hip joints
    chest: tuple[float, float] = (0.155, 0.1)  # half width, half depth
    waist: tuple[float, float] = (0.13, 0.088)
    pelvis: tuple[float, float] = (0.15, 0.098)
    bust: float = 0.0
    neck: float = 0.052
    upper_arm: float = 0.044
    forearm: float = 0.037
    wrist: float = 0.026
    hand: float = 1.0
    thigh: float = 0.08
    knee: float = 0.052
    calf: float = 0.054
    ankle: float = 0.032
    head: tuple[float, float, float] = (0.074, 0.098, 0.115)  # half width, depth, height

    @property
    def k(self) -> float:
        return self.height / 1.75


class Joints(dict):
    """Named joint positions (Vectors) for a Body in the A-pose."""


ARM_DROP = math.radians(45)


def joints(b: Body) -> Joints:
    k = b.k
    j = Joints()
    for name, z in (("pelvis", 0.95), ("spine02", 1.03), ("spine01", 1.15), ("spine", 1.27), ("neck", 1.42),
                    ("head", 1.505), ("crown", 1.725)):
        j[name] = V((0, 0, z * k))
    j["head_center"] = V((0, 0.004 * k, 1.62 * k))
    for side, s in ((1, "L"), (-1, "R")):
        shoulder = V((b.shoulder * side * k, 0, 1.40 * k))
        direction = V((math.cos(ARM_DROP) * side, 0, -math.sin(ARM_DROP)))
        j[f"{s}_clavicle"] = V((0.03 * side * k, 0, 1.40 * k))
        j[f"{s}_shoulder"] = shoulder
        j[f"{s}_elbow"] = shoulder + direction * 0.28 * k
        j[f"{s}_wrist"] = j[f"{s}_elbow"] + direction * 0.25 * k
        j[f"{s}_fingertip"] = j[f"{s}_wrist"] + direction * 0.17 * k * b.hand
        j[f"{s}_arm_dir"] = direction
        x = b.hip * side * k
        j[f"{s}_hip"] = V((x, 0, 0.90 * k))
        j[f"{s}_knee"] = V((x, -0.005 * k, 0.49 * k))
        j[f"{s}_ankle"] = V((x, 0.0, 0.085 * k))
        j[f"{s}_ball"] = V((x, -0.11 * k, 0.025 * k))
        j[f"{s}_toe"] = V((x, -0.18 * k, 0.025 * k))
    return j


def skeleton(j: Joints) -> list[tuple[str, Vector, Vector, str | None]]:
    k = j["crown"].z / 1.725
    bones = [
        ("Hips", j["pelvis"], j["spine02"], None),
        ("Spine02", j["spine02"], j["spine01"], "Hips"),
        ("Spine01", j["spine01"], j["spine"], "Spine02"),
        ("Spine", j["spine"], j["neck"], "Spine01"),
        ("neck", j["neck"], j["head"], "Spine"),
        ("Head", j["head"], j["crown"], "neck"),
        ("head_end", j["crown"], j["crown"] + V((0, 0, 0.08 * k)), "Head"),
        # Points out of the face: the office uses Head -> headfront to know which way the model faces.
        ("headfront", V((0, -0.1 * k, 1.615 * k)), V((0, -0.17 * k, 1.615 * k)), "Head"),
    ]
    for s, prefix in (("L", "Left"), ("R", "Right")):
        bones += [
            (f"{prefix}Shoulder", j[f"{s}_clavicle"], j[f"{s}_shoulder"], "Spine"),
            (f"{prefix}Arm", j[f"{s}_shoulder"], j[f"{s}_elbow"], f"{prefix}Shoulder"),
            (f"{prefix}ForeArm", j[f"{s}_elbow"], j[f"{s}_wrist"], f"{prefix}Arm"),
            (f"{prefix}Hand", j[f"{s}_wrist"], j[f"{s}_fingertip"], f"{prefix}ForeArm"),
            (f"{prefix}UpLeg", j[f"{s}_hip"], j[f"{s}_knee"], "Hips"),
            (f"{prefix}Leg", j[f"{s}_knee"], j[f"{s}_ankle"], f"{prefix}UpLeg"),
            (f"{prefix}Foot", j[f"{s}_ankle"], j[f"{s}_ball"], f"{prefix}Leg"),
            (f"{prefix}ToeBase", j[f"{s}_ball"], j[f"{s}_toe"], f"{prefix}Foot"),
        ]
    return bones


NON_DEFORM = {"head_end", "headfront"}


def _segment_distance(p: Vector, a: Vector, b: Vector) -> float:
    closest, t = geometry.intersect_point_line(p, a, b)
    if t < 0:
        closest = a
    elif t > 1:
        closest = b
    return (p - closest).length


def smooth_weights(bones) -> Callable[[Vector], dict[str, float]]:
    """Weights from the nearest bone, blended with its parent or child near the joint between them."""
    deform = [(name, head, tail, parent) for name, head, tail, parent in bones if name not in NON_DEFORM]

    def weigh(co: Vector) -> dict[str, float]:
        ranked = sorted((_segment_distance(co, head, tail), name, parent) for name, head, tail, parent in deform)
        d1, n1, p1 = ranked[0]
        for d2, n2, p2 in ranked[1:4]:
            if p2 == n1 or p1 == n2:
                w1, w2 = 1 / (d1**4 + 1e-14), 1 / (d2**4 + 1e-14)
                return {n1: w1 / (w1 + w2), n2: w2 / (w1 + w2)}
        return {n1: 1.0}

    return weigh


# --- Geometry helpers ---------------------------------------------------------------------------


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def smoothstep(edge0: float, edge1: float, x: float) -> float:
    t = min(1.0, max(0.0, (x - edge0) / (edge1 - edge0)))
    return t * t * (3 - 2 * t)


def azimuth(n: Vector) -> float:
    """Around-the-head position of a normalized point: 0 at the face, 0.5 at the ears, 1 at the back."""
    return abs(math.atan2(n.x, -n.y)) / math.pi


def hairline(n: Vector, front: float, side: float, back: float, temples: float = 0.0,
             ear_clearance: float = 0.0) -> float:
    """Signed distance above a hairline: > 0 where hair grows. Heights are normalized z at the face,
    the sides and the back; `temples` recedes it above the outer brows; `ear_clearance` lifts it over the ears."""
    a = azimuth(n)
    if a < 0.5:
        height = lerp(front, side, smoothstep(0.12, 0.5, a))
    else:
        height = lerp(side, back, smoothstep(0.5, 0.85, a))
    height += temples * math.exp(-(((a - 0.2) / 0.07) ** 2))
    height += ear_clearance * math.exp(-(((a - 0.5) / 0.09) ** 2) - ((n.z + 0.1) / 0.3) ** 2)
    return n.z - height


def frame_from(direction: Vector, up_hint: Vector = V((0, 0, 1))) -> tuple[Vector, Vector]:
    """Two unit vectors perpendicular to `direction` (and to each other)."""
    d = direction.normalized()
    u = d.cross(up_hint)
    if u.length < 1e-6:
        u = d.cross(V((0, 1, 0)))
    u.normalize()
    return u, d.cross(u).normalized()


def sweep(points: list[Vector], radii, segments: int = 8, closed: bool = False, flat: float = 1.0,
          up_hint: Vector = V((0, 0, 1)), caps: bool = True) -> bmesh.types.BMesh:
    """A tube through `points` (radius per point, or one radius). `flat` squashes the cross-section."""
    if not isinstance(radii, (list, tuple)):
        radii = [radii] * len(points)
    bm = bmesh.new()
    rings = []
    count = len(points)
    for i, p in enumerate(points):
        if closed:
            tangent = points[(i + 1) % count] - points[i - 1]
        else:
            tangent = points[min(i + 1, count - 1)] - points[max(i - 1, 0)]
        u, v = frame_from(tangent, up_hint)
        ring = []
        for s in range(segments):
            a = 2 * math.pi * s / segments
            ring.append(bm.verts.new(p + u * math.cos(a) * radii[i] + v * math.sin(a) * radii[i] * flat))
        rings.append(ring)
    pairs = list(zip(rings, rings[1:])) + ([(rings[-1], rings[0])] if closed else [])
    for r1, r2 in pairs:
        for s in range(segments):
            bm.faces.new((r1[s], r1[(s + 1) % segments], r2[(s + 1) % segments], r2[s]))
    if caps and not closed:
        bm.faces.new(list(reversed(rings[0])))
        bm.faces.new(rings[-1])
    bm.normal_update()
    return bm


def ring_around(center: Vector, axis: Vector, radius: float, count: int = 14) -> list[Vector]:
    """Points on a circle around `axis` (for cuffs, watch bands, hair ties)."""
    u, v = frame_from(axis)
    return [center + (u * math.cos(a) + v * math.sin(a)) * radius
            for a in (2 * math.pi * i / count for i in range(count))]


def ellipsoid(center, radii, rotation: Quaternion | None = None, segments: int = 24, rings: int = 16) -> bmesh.types.BMesh:
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=segments, v_segments=rings, radius=1.0,
                              matrix=Matrix.LocRotScale(V(center), rotation or Quaternion(), V(radii)))
    return bm


def rounded_box(center, size, rotation: Quaternion | None = None, bevel: float = 0.25) -> bmesh.types.BMesh:
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.bevel(bm, geom=bm.verts[:] + bm.edges[:], offset=bevel, offset_type="PERCENT", segments=3,
                    affect="EDGES")
    bmesh.ops.transform(bm, matrix=Matrix.LocRotScale(V(center), rotation or Quaternion(), V(size)), verts=bm.verts)
    return bm


def cut(bm: bmesh.types.BMesh, point, normal) -> bmesh.types.BMesh:
    """Keep only the part of the shape on the side `normal` points to."""
    geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
    bmesh.ops.bisect_plane(bm, geom=geom, plane_co=V(point), plane_no=V(normal).normalized(), clear_inner=True)
    return bm


def limb_cut(bm: bmesh.types.BMesh, end: Vector, direction: Vector, radius: float = 0.12) -> bmesh.types.BMesh:
    """End a sleeve or trouser leg at `end`, removing what lies beyond it along `direction`.
    Only geometry within `radius` of the limb is touched, so the cut can't slice the torso."""
    d = direction.normalized()

    def near(co: Vector) -> bool:
        offset = co - end
        return (offset - d * offset.dot(d)).length < radius and offset.dot(d) > -radius

    verts = {v for v in bm.verts if near(v.co)}
    edges = [e for e in bm.edges if all(v in verts for v in e.verts)]
    faces = [f for f in bm.faces if all(v in verts for v in f.verts)]
    bmesh.ops.bisect_plane(bm, geom=list(verts) + edges + faces, plane_co=end, plane_no=-d, clear_inner=True)
    beyond = [f for f in bm.faces if near(f.calc_center_median()) and (f.calc_center_median() - end).dot(d) > 0.002]
    bmesh.ops.delete(bm, geom=beyond, context="FACES")
    return bm


def smooth_border(bm: bmesh.types.BMesh, tree: BVHTree, iterations: int = 14,
                  only: Callable[[Vector], bool] | None = None) -> None:
    """Turn the stair-stepped border left by deleting faces into a smooth curve, kept on the
    original surface (`tree`). `only` limits it to border vertices where only(co) is True."""
    border = [v for v in bm.verts if v.is_boundary and (only is None or only(v.co))]
    for _ in range(iterations):
        targets = {}
        for vert in border:
            neighbours = [e.other_vert(vert) for e in vert.link_edges if e.is_boundary]
            if len(neighbours) == 2:
                targets[vert] = vert.co.lerp((neighbours[0].co + neighbours[1].co) / 2, 0.5)
        for vert, co in targets.items():
            nearest = tree.find_nearest(co)[0]
            vert.co = nearest if nearest is not None else co


def keep_faces(bm: bmesh.types.BMesh, keep: Callable[[Vector], bool]) -> bmesh.types.BMesh:
    doomed = [f for f in bm.faces if not keep(f.calc_center_median())]
    bmesh.ops.delete(bm, geom=doomed, context="FACES")
    loose = [v for v in bm.verts if not v.link_faces]
    bmesh.ops.delete(bm, geom=loose, context="VERTS")
    return bm


def rot(axis: str, degrees: float) -> Quaternion:
    return Quaternion(V({"x": (1, 0, 0), "y": (0, 1, 0), "z": (0, 0, 1)}[axis]), math.radians(degrees))


class Surface:
    """Ray-cast helper to place details (eyes, zips, badges) on a surface."""

    def __init__(self, bm: bmesh.types.BMesh):
        self.tree = BVHTree.FromBMesh(bm)

    def front(self, x: float, z: float, from_y: float = -1.0) -> tuple[Vector, Vector]:
        hit, normal, _, _ = self.tree.ray_cast(V((x, from_y, z)), V((0, 1 if from_y < 0 else -1, 0)))
        if hit is None:
            raise ValueError(f"No surface at x={x:.3f}, z={z:.3f}")
        return hit, normal

    def toward(self, origin: Vector, direction: Vector) -> tuple[Vector, Vector]:
        hit, normal, _, _ = self.tree.ray_cast(origin, direction.normalized())
        if hit is None:
            raise ValueError(f"No surface from {tuple(origin)}")
        return hit, normal


# --- Metaball blobs (organic, blended shapes) ----------------------------------------------------


class Blob:
    """A family of metaball elements that melt into one smooth surface."""

    _count = 0

    def __init__(self, name: str, resolution: float = MB_RESOLUTION):
        Blob._count += 1
        self.mb = bpy.data.metaballs.new(f"{name}Blob{Blob._count}")
        self.mb.resolution = resolution
        self.mb.render_resolution = resolution
        self.mb.threshold = 0.6
        self.obj = bpy.data.objects.new(self.mb.name, self.mb)
        bpy.context.collection.objects.link(self.obj)

    def ball(self, center, radius: float) -> "Blob":
        element = self.mb.elements.new(type="BALL")
        element.co = V(center)
        element.radius = radius / BALL_SURFACE
        return self

    def ellipsoid(self, center, half, rotation: Quaternion | None = None) -> "Blob":
        biggest = max(half)
        element = self.mb.elements.new(type="ELLIPSOID")
        element.co = V(center)
        element.radius = biggest / BALL_SURFACE
        element.size_x, element.size_y, element.size_z = (h / biggest for h in half)
        if rotation:
            element.rotation = rotation
        return self

    def limb(self, a, b, radius_a: float, radius_b: float, bulge: float = 0.0, bulge_at: float = 0.35) -> "Blob":
        """Tapered tube from a to b, optionally with a muscle bulge (fraction of the radius)."""
        a, b = V(a), V(b)
        smallest = min(radius_a, radius_b)
        count = max(2, math.ceil((b - a).length / (0.8 * smallest)) + 1)
        for i in range(count):
            t = i / (count - 1)
            r = lerp(radius_a, radius_b, t) * (1 + bulge * math.exp(-((t - bulge_at) / 0.25) ** 2))
            element = self.mb.elements.new(type="BALL")
            element.co = a.lerp(b, t)
            element.radius = r / CHAIN_SURFACE
        return self

    def to_bmesh(self) -> bmesh.types.BMesh:
        bpy.context.view_layer.update()
        bpy.ops.object.select_all(action="DESELECT")
        self.obj.select_set(True)
        bpy.context.view_layer.objects.active = self.obj
        bpy.ops.object.convert(target="MESH")
        mesh_obj = bpy.context.view_layer.objects.active
        bm = bmesh.new()
        bm.from_mesh(mesh_obj.data)
        mesh = mesh_obj.data
        bpy.data.objects.remove(mesh_obj)
        bpy.data.meshes.remove(mesh)
        return bm


# --- Heads --------------------------------------------------------------------------------------


@dataclass
class Face:
    skin: Paint
    lips: Paint
    iris: Paint
    brows: Paint
    jaw: float = 0.5  # 0 soft and tapered, 1 square
    chin: float = 1.0
    nose: float = 1.0
    brow_ridge: float = 1.0
    cheekbones: float = 1.0
    lip_fullness: float = 1.0
    brow_thickness: float = 0.003
    brow_angle: float = 0.0  # positive: inner ends lower (stern)
    eye_size: float = 1.0


class Head:
    """A sculpted head. `norm(co)` maps a point back to unit-sphere coordinates for region masks."""

    def __init__(self, center: Vector, half: tuple[float, float, float], face: Face):
        self.center, self.half, self.face = center, half, face
        hw, hd, hh = half
        bm = bmesh.new()
        bmesh.ops.create_uvsphere(bm, u_segments=96, v_segments=64, radius=1.0)
        for vert in bm.verts:
            x, y, z = vert.co
            X, Y, Z = x * hw, y * hd, z * hh
            below = max(0.0, -z)
            X *= 1 - 0.30 * below**1.5 * (1 - 0.5 * face.jaw)
            Y *= (1 - 0.45 * below**1.2) if y > 0 else (1 - 0.1 * below**2)
            if y > 0 and z > 0:
                Y *= 1 + 0.06 * z
            if y < -0.5:
                Y *= 0.965
            if y < 0:
                ax = abs(x)
                Y -= 0.026 * face.nose * math.exp(-((x / 0.1) ** 2 + ((z + 0.2) / 0.22) ** 2))
                Y -= 0.007 * face.nose * math.exp(-((x / 0.13) ** 2 + ((z + 0.36) / 0.08) ** 2))
                Y += 0.009 * math.exp(-(((ax - 0.4) / 0.16) ** 2 + (z / 0.11) ** 2))  # eye sockets
                Y -= 0.005 * face.brow_ridge * math.exp(-(((ax - 0.36) / 0.3) ** 2 + ((z - 0.18) / 0.06) ** 2))
                Y -= 0.006 * math.exp(-((x / 0.3) ** 2 + ((z + 0.58) / 0.2) ** 2))  # mouth
                Y -= 0.011 * face.chin * math.exp(-((x / 0.22) ** 2 + ((z + 0.86) / 0.12) ** 2))
                X += math.copysign(0.006 * face.cheekbones, x) * math.exp(-(((ax - 0.62) / 0.15) ** 2 + ((z + 0.1) / 0.14) ** 2))
            vert.co = V((X, Y, Z)) + center
        bm.normal_update()
        self.bm = bm
        self.surface = Surface(bm)

    def norm(self, co: Vector) -> Vector:
        d = co - self.center
        return V((d.x / self.half[0], d.y / self.half[1], d.z / self.half[2]))

    def at(self, xn: float, zn: float) -> tuple[Vector, Vector]:
        """Front surface point at normalized x, z."""
        return self.surface.front(self.center.x + xn * self.half[0], self.center.z + zn * self.half[2])

    def shell(self, field: Callable[[Vector], float], thickness: Callable[[Vector], float], soft: float = 0.08,
              roughness: float = 0.0, grain: tuple[float, float, float] = (60, 60, 60),
              solid: float = 0.003) -> bmesh.types.BMesh:
        """A layer over the head (hair, beard) where field(normalized) > 0. Its thickness tapers to
        nothing over `soft` at the edge, so the border melts into the skin instead of stair-stepping.
        `grain` stretches the surface noise (low frequency along strands, high across them)."""
        bm = self.bm.copy()
        keep_faces(bm, lambda c: field(self.norm(c)) > -0.015)
        smooth_border(bm, self.surface.tree)
        bm.normal_update()
        for vert in bm.verts:
            n = self.norm(vert.co)
            fade = smoothstep(-0.015, soft, field(n))
            push = thickness(n)
            if roughness:
                co = vert.co
                push += roughness * noise.noise(V((co.x * grain[0], co.y * grain[1], co.z * grain[2])))
            vert.co += vert.normal * (0.0006 + max(0.0, push) * fade)
        if solid:
            bmesh.ops.solidify(bm, geom=bm.faces[:], thickness=solid)
        return bm


def add_face_features(char: "Character", head: Head) -> None:
    """Eyes with lids and lashes, brows, lips and ears, placed on the sculpted head."""
    f = head.face
    hw, hd, hh = head.half
    eye_r = 0.0118 * f.eye_size
    white = paint("#f1ece6", 0.25)
    pupil = paint("#0b0b0c", 0.1)
    lash = paint("#1c1612", 0.6)
    for side in (1, -1):
        hit, _ = head.at(0.41 * side, 0.0)
        eye_center = hit + V((0, eye_r * 0.5, 0))
        char.add(ellipsoid(eye_center, (eye_r,) * 3, segments=20, rings=14), white, "Head")
        iris_center = eye_center + V((0, -eye_r * 0.93, 0))
        char.add(ellipsoid(iris_center, (eye_r * 0.5, eye_r * 0.12, eye_r * 0.5), segments=16, rings=10), f.iris, "Head")
        char.add(ellipsoid(iris_center + V((0, -eye_r * 0.06, 0)), (eye_r * 0.22, eye_r * 0.1, eye_r * 0.22),
                           segments=12, rings=8), pupil, "Head")
        # Upper lid covering the top of the eyeball, with a lash line along its edge.
        lid = ellipsoid(eye_center, (eye_r * 1.12,) * 3, segments=24, rings=16)
        cut(lid, eye_center + V((0, 0, eye_r * 0.44)), (0, 0.12, 1))
        cut(lid, eye_center + V((0, eye_r * 0.2, 0)), (0, -1, 0))
        char.add(lid, f.skin, "Head")
        lower = ellipsoid(eye_center, (eye_r * 1.06,) * 3, segments=24, rings=16)
        cut(lower, eye_center + V((0, 0, -eye_r * 0.62)), (0, 0.1, -1))
        cut(lower, eye_center + V((0, eye_r * 0.2, 0)), (0, -1, 0))
        char.add(lower, f.skin, "Head")
        lash_points = []
        for a in range(-70, 75, 14):
            t = math.radians(a)
            p = eye_center + V((math.sin(t) * eye_r * 1.08 * side, -math.cos(t) * eye_r * 1.06, eye_r * 0.55 - abs(math.sin(t)) * eye_r * 0.35))
            lash_points.append(p)
        char.add(sweep(lash_points, 0.0011, segments=5), lash, "Head")

        # Brow: follows the surface above the eye, inner end lowered for a stern look.
        brow = []
        for i in range(6):
            t = i / 5
            xn = (0.14 + 0.62 * t) * side
            zn = 0.2 + 0.05 * math.sin(math.pi * t * 0.9) - f.brow_angle * (1 - t) * 0.05
            point, normal = head.at(xn, zn)
            brow.append(point + normal * 0.0014)
        radii = [f.brow_thickness * (1.15 - 0.5 * i / 5) for i in range(6)]
        char.add(sweep(brow, radii, segments=6, flat=0.45, up_hint=V((0, -1, 0))), f.brows, "Head")

        # Ear.
        ear_center = head.center + V((side * (hw + 0.0015), 0.01, -0.012 * hh / 0.115))
        char.add(ellipsoid(ear_center, (0.0065, 0.013, 0.025), rot("x", -15), segments=16, rings=12), f.skin, "Head")

    mouth, _ = head.at(0.0, -0.6)
    char.add(ellipsoid(mouth + V((0, 0.0042, 0.0038)), (0.02, 0.0042 * f.lip_fullness, 0.0038 * f.lip_fullness),
                       segments=20, rings=12), f.lips, "Head")
    char.add(ellipsoid(mouth + V((0, 0.0038, -0.0042)), (0.018, 0.0048 * f.lip_fullness, 0.0046 * f.lip_fullness),
                       segments=20, rings=12), f.lips, "Head")


# --- Character assembly ---------------------------------------------------------------------------


class Character:
    def __init__(self, name: str, body: Body):
        self.name = name
        self.body = body
        self.j = joints(body)
        self.bones = skeleton(self.j)
        self.weigh = smooth_weights(self.bones)
        self.parts: list[bpy.types.Object] = []

    def add(self, bm: bmesh.types.BMesh, p: Paint, bone: str | None = None, smooth: bool = True,
            regions: list[tuple[Callable[[Vector], bool], Paint]] | None = None) -> bpy.types.Object:
        """Add a part. bone=None skins it smoothly to the skeleton; regions repaint faces by position."""
        mesh = bpy.data.meshes.new(f"{self.name}_{len(self.parts)}")
        bm.to_mesh(mesh)
        bm.free()
        obj = bpy.data.objects.new(mesh.name, mesh)
        bpy.context.collection.objects.link(obj)
        mesh.materials.append(blender_material(p))
        for index, (predicate, region_paint) in enumerate(regions or [], start=1):
            mesh.materials.append(blender_material(region_paint))
            for poly in mesh.polygons:
                if predicate(V(poly.center)):
                    poly.material_index = index
        mesh.polygons.foreach_set("use_smooth", [smooth] * len(mesh.polygons))

        groups: dict[str, bpy.types.VertexGroup] = {}

        def group(name: str) -> bpy.types.VertexGroup:
            if name not in groups:
                groups[name] = obj.vertex_groups.new(name=name)
            return groups[name]

        if bone:
            group(bone).add(range(len(mesh.vertices)), 1.0, "REPLACE")
        else:
            for vert in mesh.vertices:
                for name, weight in self.weigh(V(vert.co)).items():
                    group(name).add([vert.index], weight, "REPLACE")
        self.parts.append(obj)
        return obj

    # Shared building blocks -------------------------------------------------------------------

    def torso_blob(self, blob: Blob, extra: float = 0.0, top: float = 1.0, lower: bool = True) -> Blob:
        """Torso volumes; `extra` inflates them (clothes), `top` scales how far up the neck it goes."""
        b, j, k = self.body, self.j, self.body.k
        if lower:
            blob.ellipsoid(V((0, 0.0, 0.94 * k)), (b.pelvis[0] + extra, b.pelvis[1] + extra, 0.1 * k + extra))
        blob.ellipsoid(V((0, 0.004, 1.07 * k)), (b.waist[0] + extra, b.waist[1] + extra, 0.1 * k + extra))
        blob.ellipsoid(V((0, 0.004, 1.24 * k)), (b.chest[0] + extra, b.chest[1] + extra, 0.12 * k + extra))
        blob.ellipsoid(V((0, 0.012, 1.37 * k)), (b.shoulder * k * 0.92 + extra, b.chest[1] * 0.85 + extra, 0.07 * k + extra))
        for side, s in ((1, "L"), (-1, "R")):
            # Trapezius: slopes from the neck down to the shoulder, so the neck doesn't sit on a flat ledge.
            blob.ellipsoid(V((0.068 * side * k, 0.016, 1.435 * k)), (0.07 * k + extra, 0.042 + extra, 0.03 + extra),
                           rot("y", 20 * side))
            blob.ball(j[f"{s}_shoulder"] + V((-0.012 * side, 0.005, 0.005)), b.upper_arm * 1.25 + extra)
            if b.bust:
                blob.ball(V((0.048 * side * k, -b.chest[1] * 0.55, 1.27 * k)), b.bust + extra)
        return blob

    def arm_blob(self, blob: Blob, side: str, extra: float = 0.0, until: float = 1.0) -> Blob:
        """Upper arm and forearm; `until` (0..1 along the forearm) stops early for sleeves."""
        b, j = self.body, self.j
        shoulder, elbow, wrist = j[f"{side}_shoulder"], j[f"{side}_elbow"], j[f"{side}_wrist"]
        blob.limb(shoulder, elbow, b.upper_arm + extra, b.forearm * 1.05 + extra, bulge=0.12)
        end = elbow.lerp(wrist, until)
        blob.limb(elbow, end, b.forearm * 1.05 + extra, lerp(b.forearm, b.wrist, until) + extra, bulge=0.1, bulge_at=0.25)
        return blob

    def hand_blob(self, blob: Blob, side: str) -> Blob:
        b, j = self.body, self.j
        d = j[f"{side}_arm_dir"]
        wrist = j[f"{side}_wrist"]
        rotation = d.to_track_quat("Z", "Y")
        h = b.hand
        blob.ellipsoid(wrist + d * 0.045 * h, (0.036 * h, 0.016 * h, 0.044 * h), rotation)  # palm
        blob.ellipsoid(wrist + d * 0.11 * h, (0.033 * h, 0.011 * h, 0.042 * h), rotation)  # fingers together
        palm_front = V((0, -1, 0))
        blob.limb(wrist + d * 0.025 * h + palm_front * 0.012, wrist + d * 0.07 * h + palm_front * 0.034, 0.012 * h, 0.009 * h)
        return blob

    def leg_blob(self, blob: Blob, side: str, extra: float = 0.0, until: float = 1.0) -> Blob:
        b, j = self.body, self.j
        hip, knee, ankle = j[f"{side}_hip"], j[f"{side}_knee"], j[f"{side}_ankle"]
        blob.limb(hip + V((0, 0, 0.03)), knee, b.thigh + extra, b.knee + extra, bulge=0.06, bulge_at=0.2)
        blob.limb(knee, knee.lerp(ankle, until), b.knee + extra, lerp(b.knee, b.ankle, until) + extra, bulge=0.18, bulge_at=0.3)
        return blob

    def body_skin(self, skin: Paint) -> None:
        """The whole bare body as one smooth surface (clothes go over it)."""
        blob = self.torso_blob(Blob("Body"))
        j, b = self.j, self.body
        blob.limb(j["neck"] + V((0, 0.01, -0.03)), j["head"] + V((0, 0.012, 0.05)), b.neck, b.neck * 0.92)
        for s in ("L", "R"):
            self.arm_blob(blob, s)
            self.hand_blob(blob, s)
            self.leg_blob(blob, s)
        self.add(blob.to_bmesh(), skin)

    def sleeve_end(self, side: str, until: float, short: bool = False) -> tuple[Vector, Vector]:
        """Where a sleeve ends and the arm direction there. `short` measures along the upper arm."""
        j = self.j
        if short:
            a, b = j[f"{side}_shoulder"], j[f"{side}_elbow"]
        else:
            a, b = j[f"{side}_elbow"], j[f"{side}_wrist"]
        return a.lerp(b, until), (b - a).normalized()

    def top(self, p: Paint, extra: float, hem: float, sleeve: float = 1.0, short_sleeve: bool = False,
            neckline: float = 1.49, opening: Callable[[Vector], bool] | None = None,
            regions=None) -> Surface:
        """A shirt, sweater or jacket over the body. hem/neckline are heights at the 1.75 m reference;
        `sleeve` is how far down the forearm (or upper arm, if short_sleeve) the sleeves reach;
        `opening(center)` returns True for faces to remove (open fronts, V-necks)."""
        k = self.body.k
        blob = self.torso_blob(Blob("Top"), extra=extra)
        for s in ("L", "R"):
            if hem < 0.95:
                hip = self.j[f"{s}_hip"]
                blob.limb(hip + V((0, 0, 0.03)), hip - V((0, 0, 0.14)), self.body.thigh + extra, self.body.thigh + extra)
            if short_sleeve:
                end, _ = self.sleeve_end(s, sleeve, short=True)
                blob.limb(self.j[f"{s}_shoulder"], end, self.body.upper_arm + extra, self.body.upper_arm * 0.95 + extra)
            else:
                self.arm_blob(blob, s, extra=extra, until=sleeve)
        bm = cut(cut(blob.to_bmesh(), (0, 0, hem * k), (0, 0, 1)), (0, 0, neckline * k), (0, 0, -1))
        for s in ("L", "R"):
            end, direction = self.sleeve_end(s, sleeve, short_sleeve)
            limb_cut(bm, end, direction)
        if opening:
            original = BVHTree.FromBMesh(bm)
            keep_faces(bm, lambda c: not opening(c))
            # Smooth only the opening's edge, not the hem or sleeve ends.
            smooth_border(bm, original, only=lambda co: co.y < -0.01 and co.z > (hem + 0.02) * k)
        surface = Surface(bm)
        self.add(bm, p, regions=regions)
        return surface

    def trousers(self, p: Paint, top: float = 1.0, extra: float = 0.012, regions=None) -> None:
        k = self.body.k
        blob = Blob("Trousers")
        blob.ellipsoid(V((0, 0, 0.94 * k)), (self.body.pelvis[0] + extra, self.body.pelvis[1] + extra, 0.1 * k + extra))
        for s in ("L", "R"):
            self.leg_blob(blob, s, extra=extra)
        self.add(cut(cut(blob.to_bmesh(), (0, 0, 0.1), (0, 0, 1)), (0, 0, top * k), (0, 0, -1)), p, regions=regions)

    def cuff(self, side: str, at: float, p: Paint, extra: float, thickness: float = 0.01, short: bool = False) -> None:
        """A rolled cuff or sleeve band around the arm."""
        end, direction = self.sleeve_end(side, at, short)
        radius = (self.body.upper_arm * 0.95 if short else lerp(self.body.forearm, self.body.wrist, at)) + extra
        self.add(sweep(ring_around(end - direction * thickness, direction, radius), thickness, segments=8, closed=True), p)

    def watch(self, side: str, strap: Paint, face: Paint) -> None:
        end, direction = self.sleeve_end(side, 0.9)
        radius = lerp(self.body.forearm, self.body.wrist, 0.9) + 0.004
        self.add(sweep(ring_around(end, direction, radius, 16), 0.0045, segments=6, closed=True, flat=0.5), strap)
        outward = V((0, 0, 1)).cross(direction).cross(direction).normalized() * -1  # back of the wrist
        self.add(rounded_box(end + outward * (radius + 0.004), (0.026, 0.006, 0.03),
                             outward.to_track_quat("Y", "Z")), face)

    def shoes(self, upper: Paint, sole: Paint | None = None, sole_height: float = 0.022, height: float = 0.07) -> None:
        j, k = self.j, self.body.k
        blob = Blob("Shoes")
        for s in ("L", "R"):
            x = j[f"{s}_ankle"].x
            blob.ellipsoid(V((x, 0.028 * k, 0.045)), (0.04, 0.045, 0.042))
            blob.ellipsoid(V((x, -0.05 * k, 0.036)), (0.043, 0.095 * k, height * 0.48))
            blob.ellipsoid(V((x, -0.15 * k, 0.03)), (0.04, 0.05, 0.028))
        bm = cut(blob.to_bmesh(), (0, 0, 0.0), (0, 0, 1))
        regions = [(lambda c: c.z < sole_height, sole)] if sole else None
        self.add(bm, upper, regions=regions)


def _build_armature(char: Character) -> bpy.types.Object:
    armature = bpy.data.armatures.new("Armature")
    rig = bpy.data.objects.new("Armature", armature)
    bpy.context.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode="EDIT")
    for name, head, tail, parent in char.bones:
        bone = armature.edit_bones.new(name)
        bone.head, bone.tail = head, tail
        if parent:
            bone.parent = armature.edit_bones[parent]
    bpy.ops.object.mode_set(mode="OBJECT")
    return rig


def _render_previews(stem: str, height: float) -> None:
    scene = bpy.context.scene
    for engine in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        try:
            scene.render.engine = engine
            break
        except TypeError:
            continue
    scene.render.resolution_x, scene.render.resolution_y = 700, 1000
    world = bpy.data.worlds.new("Preview")
    world.color = (0.55, 0.56, 0.6)
    if hasattr(world, "use_nodes"):
        world.use_nodes = True
        background = world.node_tree.nodes.get("Background")
        if background:
            background.inputs["Color"].default_value = (0.42, 0.44, 0.48, 1)
            background.inputs["Strength"].default_value = 0.35
    scene.world = world
    for name, energy, location, rotation in (
        ("Key", 320, (2.5, -3.0, 3.2), (55, 0, 40)),
        ("Fill", 90, (-3.0, -2.0, 2.0), (65, 0, -55)),
        ("Rim", 220, (0.5, 3.0, 3.0), (-50, 0, 170)),
    ):
        light = bpy.data.lights.new(name, "AREA")
        light.energy = energy
        light.size = 2.0
        obj = bpy.data.objects.new(name, light)
        obj.location = location
        obj.rotation_euler = [math.radians(a) for a in rotation]
        bpy.context.collection.objects.link(obj)

    camera_data = bpy.data.cameras.new("Preview")
    camera = bpy.data.objects.new("Preview", camera_data)
    bpy.context.collection.objects.link(camera)
    scene.camera = camera
    shots = (
        ("front", 50, (0, -5.2 * height / 1.75, 0.95 * height / 1.75), 0, 90),
        ("three_quarter", 50, (3.4, -3.4, 1.0 * height / 1.75), 45, 88),
        ("face", 85, (0.9, -2.4, 1.64 * height / 1.75), 20, 90),
    )
    for name, lens, location, yaw, pitch in shots:
        camera_data.lens = lens
        camera.location = location
        camera.rotation_euler = (math.radians(pitch), 0, math.radians(yaw))
        if name == "face":
            camera_data.lens = 160
        scene.render.filepath = f"{stem}_{name}.png"
        bpy.ops.render.render(write_still=True)


def build(make: Callable[[], Character]) -> None:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--preview")
    args = parser.parse_args(argv)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    _materials.clear()
    char = make()
    rig = _build_armature(char)

    bpy.ops.object.select_all(action="DESELECT")
    for part in char.parts:
        part.select_set(True)
    bpy.context.view_layer.objects.active = char.parts[0]
    bpy.ops.object.join()
    body = bpy.context.view_layer.objects.active
    body.name = char.name
    body.parent = rig
    body.modifiers.new("Armature", "ARMATURE").object = rig

    bpy.ops.object.select_all(action="DESELECT")
    body.select_set(True)
    rig.select_set(True)
    bpy.ops.export_scene.gltf(filepath=args.out, export_format="GLB", use_selection=True,
                              export_draco_mesh_compression_enable=True, export_draco_mesh_compression_level=6)
    print(f"[characters] exported {args.out}: {len(body.data.vertices)} vertices, {len(rig.data.bones)} bones")
    if args.preview:
        _render_previews(args.preview, char.body.height)
