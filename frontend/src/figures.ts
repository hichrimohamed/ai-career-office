import * as THREE from 'three';
import { DRACOLoader } from 'three/addons/loaders/DRACOLoader.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';

export type WorkerState = 'idle' | 'thinking' | 'typing';

/** What a worker looks like: added to the worker's group, posed at its chair, animated per state. */
export interface Figure {
  readonly root: THREE.Object3D;
  /** Where the name tag hangs (it's placed a little above this point). */
  readonly headAnchor: THREE.Object3D;
  update(time: number, state: WorkerState): void;
}

/** The original block worker: capsule body, sphere head, capsule arms. */
export class BlockFigure implements Figure {
  readonly root = new THREE.Group();
  readonly headAnchor: THREE.Mesh;
  private readonly body: THREE.Mesh;
  private readonly arms: THREE.Mesh[] = [];

  constructor(color: number) {
    const shirt = new THREE.MeshStandardMaterial({ color });
    const skin = new THREE.MeshStandardMaterial({ color: 0xf1c27d });

    this.body = new THREE.Mesh(new THREE.CapsuleGeometry(0.25, 0.5, 4, 12), shirt);
    this.body.position.y = 0.85;
    this.headAnchor = new THREE.Mesh(new THREE.SphereGeometry(0.2, 16, 16), skin);
    this.headAnchor.position.y = 1.45;

    for (const side of [-1, 1]) {
      const arm = new THREE.Mesh(new THREE.CapsuleGeometry(0.07, 0.35, 4, 8), shirt);
      arm.position.set(side * 0.3, 0.95, -0.2);
      arm.rotation.x = -Math.PI / 2.5;
      this.arms.push(arm);
    }
    for (const mesh of [this.body, this.headAnchor, ...this.arms]) {
      mesh.castShadow = true;
      this.root.add(mesh);
    }
  }

  update(time: number, state: WorkerState): void {
    const t = time / 1000;
    this.headAnchor.rotation.set(0, 0, 0);
    this.body.position.y = 0.85 + Math.sin(t * 1.5) * 0.01;
    this.arms.forEach((arm, i) => {
      arm.position.y = state === 'typing' ? 0.95 + Math.sin(t * 20 + i * Math.PI) * 0.03 : 0.95;
    });
    if (state === 'thinking') {
      this.headAnchor.rotation.z = Math.sin(t * 2) * 0.15;
      this.headAnchor.rotation.x = -0.2;
    }
  }
}

// --- Rigged GLB figures (humanoid rigs with Mixamo-style bone names) ---

const SEAT_HIPS = new THREE.Vector3(0, 0.62, 0.05); // hips position on the chair, in worker space
const FORWARD = new THREE.Vector3(0, 0, -1); // workers face their monitor along -z
const RIGHT = new THREE.Vector3(1, 0, 0);
const UP = new THREE.Vector3(0, 1, 0);

/** Seated typing pose: for each bone, the worker-space direction toward its child bone. */
const SEATED_POSE: [bone: string, child: string, direction: THREE.Vector3][] = [
  ['LeftUpLeg', 'LeftLeg', new THREE.Vector3(0, -0.08, -1)],
  ['RightUpLeg', 'RightLeg', new THREE.Vector3(0, -0.08, -1)],
  ['LeftLeg', 'LeftFoot', new THREE.Vector3(0, -1, -0.05)],
  ['RightLeg', 'RightFoot', new THREE.Vector3(0, -1, -0.05)],
  ['LeftFoot', 'LeftToeBase', new THREE.Vector3(0, -0.3, -1)],
  ['RightFoot', 'RightToeBase', new THREE.Vector3(0, -0.3, -1)],
  // Elbows near the body, forearms level over the keyboard, hands angled slightly inward.
  ['LeftArm', 'LeftForeArm', new THREE.Vector3(0.12, -0.95, -0.3)],
  ['RightArm', 'RightForeArm', new THREE.Vector3(-0.12, -0.95, -0.3)],
  ['LeftForeArm', 'LeftHand', new THREE.Vector3(-0.22, 0.04, -1)],
  ['RightForeArm', 'RightHand', new THREE.Vector3(0.22, 0.04, -1)],
];

/** Bones animated each frame, reset to the seated pose first (parents before children). */
const ANIMATED_BONES = ['Spine01', 'Head', 'LeftHand', 'RightHand', 'LeftForeArm', 'RightForeArm'];

// Character GLBs are Draco-compressed (assets/characters/toolkit.py); the decoder is served from public/draco.
const loader = new GLTFLoader().setDRACOLoader(new DRACOLoader().setDecoderPath('/draco/'));

function worldDirection(from: THREE.Object3D, to: THREE.Object3D): THREE.Vector3 {
  const a = from.getWorldPosition(new THREE.Vector3());
  return to.getWorldPosition(new THREE.Vector3()).sub(a).normalize();
}

/** Rotate `bone` so that the direction toward `child` matches `target` (world space). Works for any bone axes. */
function aimBone(bone: THREE.Object3D, child: THREE.Object3D, target: THREE.Vector3): void {
  const delta = new THREE.Quaternion().setFromUnitVectors(worldDirection(bone, child), target.clone().normalize());
  const world = bone.getWorldQuaternion(new THREE.Quaternion()).premultiply(delta);
  const parentWorld = bone.parent!.getWorldQuaternion(new THREE.Quaternion());
  bone.quaternion.copy(parentWorld.invert().multiply(world));
  bone.updateMatrixWorld(true);
}

/** Rotate `bone` by `angle` around a world-space axis, on top of its current local rotation. */
function rotateBoneWorld(bone: THREE.Object3D, axis: THREE.Vector3, angle: number): void {
  const parentWorld = bone.parent!.getWorldQuaternion(new THREE.Quaternion());
  const turn = new THREE.Quaternion().setFromAxisAngle(axis, angle);
  const local = parentWorld.clone().invert().multiply(turn).multiply(parentWorld);
  bone.quaternion.premultiply(local);
  bone.updateMatrixWorld(true);
}

/** A rigged character loaded from a GLB, seated at the desk with its hands on the keyboard. */
export class RiggedFigure implements Figure {
  readonly root = new THREE.Group();
  readonly headAnchor: THREE.Object3D;
  private readonly bones = new Map<string, THREE.Object3D>();
  private readonly basePose = new Map<string, THREE.Quaternion>();
  private readonly worldAxes: { forward: THREE.Vector3; right: THREE.Vector3; up: THREE.Vector3 };

  private constructor(model: THREE.Object3D, parent: THREE.Object3D) {
    model.traverse((node) => {
      if ((node as THREE.Bone).isBone) this.bones.set(node.name, node);
      if ((node as THREE.Mesh).isMesh) {
        node.castShadow = true;
        node.frustumCulled = false; // bounds go stale once bones move
      }
    });
    this.root.add(model);
    parent.add(this.root);

    const parentQuat = parent.getWorldQuaternion(new THREE.Quaternion());
    this.worldAxes = {
      forward: FORWARD.clone().applyQuaternion(parentQuat),
      right: RIGHT.clone().applyQuaternion(parentQuat),
      up: UP.clone().applyQuaternion(parentQuat),
    };

    // Face the monitor: turn the model so its face (Head -> headfront) points forward.
    const head = this.bone('Head');
    const front = this.bones.get('headfront');
    if (front) {
      this.root.updateMatrixWorld(true);
      const facing = worldDirection(head, front).setY(0).normalize();
      const turn = new THREE.Quaternion().setFromUnitVectors(facing, this.worldAxes.forward.clone().setY(0).normalize());
      model.quaternion.premultiply(turn);
    }
    this.root.updateMatrixWorld(true);

    const toWorld = (v: THREE.Vector3) => v.clone().applyQuaternion(parentQuat);
    for (const [bone, child, direction] of SEATED_POSE) {
      if (this.bones.has(bone) && this.bones.has(child)) aimBone(this.bone(bone), this.bone(child), toWorld(direction));
    }

    // Drop the posed body onto the chair.
    const hips = this.bone('Hips').getWorldPosition(new THREE.Vector3());
    const seat = parent.localToWorld(SEAT_HIPS.clone());
    this.root.position.add(parent.worldToLocal(seat.clone()).sub(parent.worldToLocal(hips.clone())));
    this.root.updateMatrixWorld(true);

    for (const name of ANIMATED_BONES) {
      if (this.bones.has(name)) this.basePose.set(name, this.bone(name).quaternion.clone());
    }
    this.headAnchor = head;
  }

  /** Load a GLB and seat it in `parent` (the worker group). Rejects if the file or rig is unusable. */
  static async load(url: string, parent: THREE.Object3D): Promise<RiggedFigure> {
    const gltf = await loader.loadAsync(url);
    const names = new Set<string>();
    gltf.scene.traverse((node) => names.add(node.name));
    for (const required of ['Hips', 'Head', 'LeftArm', 'RightArm', 'LeftUpLeg', 'RightUpLeg']) {
      if (!names.has(required)) throw new Error(`${url}: rig has no "${required}" bone`);
    }
    parent.updateMatrixWorld(true);
    return new RiggedFigure(gltf.scene, parent);
  }

  private bone(name: string): THREE.Object3D {
    const bone = this.bones.get(name);
    if (!bone) throw new Error(`Missing bone ${name}`);
    return bone;
  }

  update(time: number, state: WorkerState): void {
    const t = time / 1000;
    const { forward, right, up } = this.worldAxes;
    for (const [name, quaternion] of this.basePose) this.bone(name).quaternion.copy(quaternion);

    const animate = (name: string, axis: THREE.Vector3, angle: number) => {
      if (this.basePose.has(name)) rotateBoneWorld(this.bone(name), axis, angle);
    };

    animate('Spine01', right, Math.sin(t * 1.6) * 0.015); // breathing
    if (state === 'typing') {
      animate('Head', right, 0.12); // eyes on the screen
      animate('LeftHand', right, Math.sin(t * 18) * 0.18);
      animate('RightHand', right, Math.sin(t * 18 + Math.PI) * 0.18);
      animate('LeftForeArm', up, Math.sin(t * 3) * 0.04);
      animate('RightForeArm', up, Math.sin(t * 3 + 1) * 0.04);
    } else if (state === 'thinking') {
      animate('Head', forward, Math.sin(t * 1.8) * 0.12); // slow head tilt
      animate('Head', right, -0.12); // looking up a little
    } else {
      animate('Head', up, Math.sin(t * 0.5) * 0.25); // glancing around
    }
  }
}
