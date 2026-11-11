import * as THREE from 'three';
import type { OrbitControls } from 'three/addons/controls/OrbitControls.js';

const FLIGHT_MS = 900;
const HEAD_HEIGHT = 1.05;
/** Camera offset from a seated worker: beside the desk on the aisle side, a little in front and above. */
const OFFSET = { side: 2.0, up: 1.5, forward: -0.9 };
/** Smallest uncovered width (px) between the side panels worth re-centring the worker into. */
const MIN_FREE_WIDTH = 300;

interface View {
  position: THREE.Vector3;
  target: THREE.Vector3;
}

const easeInOutCubic = (x: number) => (x < 0.5 ? 4 * x * x * x : 1 - (-2 * x + 2) ** 3 / 2);

/** Flies the orbit camera to a worker and back to where it was before. Any drag or zoom cancels a flight. */
export class CameraDirector {
  private flight: { from: View; to: View; start: number; duration: number } | null = null;
  /** The view before the first fly-in, restored by `returnHome`. */
  private home: View | null = null;

  private readonly camera: THREE.PerspectiveCamera;
  private readonly controls: OrbitControls;
  /** Width (px) of the screen covered by panels on each side. */
  private readonly covered: () => { left: number; right: number };

  constructor(camera: THREE.PerspectiveCamera, controls: OrbitControls, covered: () => { left: number; right: number }) {
    this.camera = camera;
    this.controls = controls;
    this.covered = covered;
    controls.addEventListener('start', () => (this.flight = null));
  }

  /** Frame the worker seated at `seat`. The worker lands in the part of the screen the panels leave free. */
  focus(seat: THREE.Vector3, instant = false): void {
    this.home ??= this.currentView();
    const target = seat.clone().setY(HEAD_HEIGHT);
    // Stand on the aisle side (towards the room centre) so walls and neighbouring desks stay out of the way.
    const side = seat.x > 0 ? -OFFSET.side : OFFSET.side;
    const position = target.clone().add(new THREE.Vector3(side, OFFSET.up, OFFSET.forward));

    const shift = this.panelShift(position, target);
    this.flyTo({ position: position.add(shift), target: target.add(shift) }, instant);
  }

  returnHome(): void {
    if (this.home) this.flyTo(this.home);
    this.home = null;
  }

  update(time: number): void {
    if (!this.flight) return;
    const { from, to, start, duration } = this.flight;
    const progress = duration > 0 ? Math.min(Math.max((time - start) / duration, 0), 1) : 1;
    const eased = easeInOutCubic(progress);
    this.camera.position.lerpVectors(from.position, to.position, eased);
    this.controls.target.lerpVectors(from.target, to.target, eased);
    if (progress === 1) this.flight = null;
  }

  private flyTo(view: View, instant = false): void {
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    this.flight = {
      from: this.currentView(),
      to: view,
      start: performance.now(),
      duration: instant || reduceMotion ? 0 : FLIGHT_MS,
    };
    if (this.flight.duration === 0) this.update(this.flight.start);
  }

  private currentView(): View {
    return { position: this.camera.position.clone(), target: this.controls.target.clone() };
  }

  /** Sideways move (world space) that puts the target in the middle of the screen area between the panels. */
  private panelShift(position: THREE.Vector3, target: THREE.Vector3): THREE.Vector3 {
    const width = window.innerWidth;
    const covered = this.covered();
    if (width - covered.left - covered.right < MIN_FREE_WIDTH) return new THREE.Vector3();

    const ndcX = (covered.left + (width - covered.right)) / width - 1; // centre of the free area, in -1..1 screen units
    const distance = position.distanceTo(target);
    const halfWidth = distance * Math.tan(THREE.MathUtils.degToRad(this.camera.fov / 2)) * (width / window.innerHeight);
    const forward = target.clone().sub(position).normalize();
    const right = forward.cross(new THREE.Vector3(0, 1, 0)).normalize();
    return right.multiplyScalar(-ndcX * halfWidth);
  }
}
