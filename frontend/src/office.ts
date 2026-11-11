import * as THREE from 'three';
import { DRACOLoader } from 'three/addons/loaders/DRACOLoader.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';

/** Desk centres. Must match DESKS in assets/office/build_office.py. Workers sit 0.75 m in front (+z). */
export const DESK_POSITIONS: THREE.Vector3[] = [
  new THREE.Vector3(-3, 0, -2),
  new THREE.Vector3(3, 0, -2),
  new THREE.Vector3(-3, 0, 2.5),
  new THREE.Vector3(3, 0, 2.5),
];

/** The office built in Blender (assets/office/build_office.py). */
const OFFICE_MODEL = '/models/office.glb';
const PENDANT_HEIGHT = 2.4;

const loader = new GLTFLoader().setDRACOLoader(new DRACOLoader().setDecoderPath('/draco/'));

/** Image-based lighting, a soft sky/ground fill, the sun with shadows, and warm light under each pendant. */
export function addLighting(scene: THREE.Scene, renderer: THREE.WebGLRenderer): void {
  const pmrem = new THREE.PMREMGenerator(renderer);
  scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
  scene.environmentIntensity = 0.45;

  scene.add(new THREE.HemisphereLight(0xfff6e8, 0x8d8577, 0.5));
  const sun = new THREE.DirectionalLight(0xfff1dc, 2.2);
  sun.position.set(6, 10, 6);
  sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  sun.shadow.camera.left = -10;
  sun.shadow.camera.right = 10;
  sun.shadow.camera.top = 10;
  sun.shadow.camera.bottom = -10;
  sun.shadow.bias = -0.0004;
  sun.shadow.normalBias = 0.02;
  scene.add(sun);

  for (const desk of DESK_POSITIONS) {
    const lamp = new THREE.PointLight(0xffd9a0, 3, 4.5, 2);
    lamp.position.set(desk.x, PENDANT_HEIGHT, desk.z);
    scene.add(lamp);
  }
}

function blockDesk(position: THREE.Vector3): THREE.Group {
  const desk = new THREE.Group();
  const wood = new THREE.MeshStandardMaterial({ color: 0x9c6b43 });
  const top = new THREE.Mesh(new THREE.BoxGeometry(2, 0.1, 1), wood);
  top.position.y = 0.75;
  desk.add(top);

  for (const [x, z] of [[-0.9, -0.4], [0.9, -0.4], [-0.9, 0.4], [0.9, 0.4]]) {
    const leg = new THREE.Mesh(new THREE.BoxGeometry(0.08, 0.75, 0.08), wood);
    leg.position.set(x, 0.375, z);
    desk.add(leg);
  }

  const monitor = new THREE.Mesh(
    new THREE.BoxGeometry(0.8, 0.5, 0.05),
    new THREE.MeshStandardMaterial({ color: 0x222831, emissive: 0x1d4ed8, emissiveIntensity: 0.25 }),
  );
  monitor.position.set(0, 1.1, -0.3);
  desk.add(monitor);

  const chair = new THREE.Mesh(new THREE.BoxGeometry(0.6, 0.08, 0.6), new THREE.MeshStandardMaterial({ color: 0x333842 }));
  chair.position.set(0, 0.5, 0.75);
  desk.add(chair);

  desk.position.copy(position);
  return desk;
}

/** Simple box office, shown until the Blender model loads (and kept if it can't). */
function blockOffice(): THREE.Group {
  const office = new THREE.Group();
  const floor = new THREE.Mesh(new THREE.PlaneGeometry(16, 14), new THREE.MeshStandardMaterial({ color: 0xd8d2c4 }));
  floor.rotation.x = -Math.PI / 2;
  office.add(floor);

  const wallMaterial = new THREE.MeshStandardMaterial({ color: 0xeee8dc });
  const backWall = new THREE.Mesh(new THREE.BoxGeometry(16, 4, 0.2), wallMaterial);
  backWall.position.set(0, 2, -7);
  const sideWall = new THREE.Mesh(new THREE.BoxGeometry(0.2, 4, 14), wallMaterial);
  sideWall.position.set(-8, 2, 0);
  office.add(backWall, sideWall);

  for (const position of DESK_POSITIONS) office.add(blockDesk(position));
  office.traverse((node) => {
    node.castShadow = node !== floor;
    node.receiveShadow = true;
  });
  return office;
}

const NO_SHADOW_CASTERS = new Set(['Floor', 'Rug', 'RugBorder', 'Daylight', 'Wall']);

export function buildOffice(scene: THREE.Scene): void {
  const fallback = blockOffice();
  scene.add(fallback);

  loader
    .loadAsync(OFFICE_MODEL)
    .then((gltf) => {
      gltf.scene.traverse((node) => {
        if (!(node as THREE.Mesh).isMesh) return;
        const materialName = ((node as THREE.Mesh).material as THREE.Material).name;
        node.castShadow = !NO_SHADOW_CASTERS.has(materialName);
        node.receiveShadow = true;
      });
      scene.remove(fallback);
      scene.add(gltf.scene);
    })
    .catch((error) => console.warn(`[office] Could not load ${OFFICE_MODEL}, keeping the block office.`, error));
}
