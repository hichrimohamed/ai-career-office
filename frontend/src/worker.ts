import * as THREE from 'three';
import { BlockFigure, type Figure, RiggedFigure, type WorkerState } from './figures';

export type { WorkerState };

/** An office worker at a desk (the office provides the chair): a figure (block or rigged 3D model) and a name tag. */
export class Worker {
  readonly group = new THREE.Group();
  readonly agentId: string;
  /** Invisible box around the worker: the only thing clicks and hovers are tested against. */
  readonly hitbox: THREE.Mesh;
  state: WorkerState = 'idle';
  /** What the worker is doing right now, shown under the name tag while busy (e.g. "Searching the web…"). */
  activity: string | null = null;
  /** A reply finished while you weren't looking at this worker's chat. Cleared when you open it. */
  hasNews = false;
  /** A line said out loud (the Morning standup), shown in a speech bubble above the name tag. */
  speech: string | null = null;

  private figure: Figure;
  private readonly label: HTMLDivElement;
  private readonly activityLine: HTMLElement;
  private readonly speechBubble: HTMLElement;
  private shownActivity: string | null = null;
  private shownSpeech: string | null = null;

  constructor(agentId: string, name: string, role: string, color: number, deskPosition: THREE.Vector3, modelUrl?: string) {
    this.agentId = agentId;

    // Picking a 27k-vertex skinned mesh on every mouse move is slow, so test a simple box instead.
    this.hitbox = new THREE.Mesh(new THREE.BoxGeometry(0.8, 1.9, 1.1), new THREE.MeshBasicMaterial({ visible: false }));
    this.hitbox.position.set(0, 0.95, -0.15);
    this.hitbox.userData.agentId = agentId;
    this.group.add(this.hitbox);

    // Sit on the near side of the desk, facing the monitor.
    this.group.position.copy(deskPosition).add(new THREE.Vector3(0, 0, 0.75));

    this.figure = new BlockFigure(color);
    this.group.add(this.figure.root);
    if (modelUrl) void this.loadModel(modelUrl);

    this.label = document.createElement('div');
    this.label.className = 'worker-label';
    this.label.innerHTML = `<strong></strong><span></span><em hidden></em><p class="speech" hidden></p>`;
    this.label.querySelector('strong')!.textContent = name;
    this.label.querySelector('span')!.textContent = role;
    this.activityLine = this.label.querySelector('em')!;
    this.speechBubble = this.label.querySelector('.speech')!;
    document.body.appendChild(this.label);
  }

  /** Swap the block figure for a rigged model; keep the block one if loading fails. */
  private async loadModel(url: string): Promise<void> {
    try {
      const rigged = await RiggedFigure.load(url, this.group);
      this.group.remove(this.figure.root);
      this.figure = rigged;
      console.info(`[office] Loaded ${url} for ${this.agentId}.`);
    } catch (error) {
      console.warn(`[office] Could not load ${url}, keeping the block figure.`, error);
    }
  }

  update(time: number): void {
    this.figure.update(time, this.state);
  }

  /** Keep the HTML name tag above the worker's head. */
  updateLabel(camera: THREE.Camera, width: number, height: number): void {
    const point = this.figure.headAnchor.getWorldPosition(new THREE.Vector3()).add(new THREE.Vector3(0, 0.45, 0));
    point.project(camera);
    const visible = point.z < 1;
    this.label.style.display = visible ? 'block' : 'none';
    this.label.style.transform = `translate(-50%, -100%) translate(${((point.x + 1) / 2) * width}px, ${((1 - point.y) / 2) * height}px)`;
    this.label.classList.toggle('busy', this.state !== 'idle');
    this.label.classList.toggle('has-news', this.hasNews);

    if (this.speech !== this.shownSpeech) {
      this.shownSpeech = this.speech;
      this.speechBubble.hidden = this.speech === null;
      this.speechBubble.textContent = this.speech ?? '';
      this.label.classList.toggle('speaking', this.speech !== null);
    }

    const activity = this.state === 'idle' ? null : this.activity ?? (this.state === 'typing' ? 'Writing…' : 'Thinking…');
    if (activity !== this.shownActivity) {
      this.shownActivity = activity;
      this.activityLine.hidden = activity === null;
      this.activityLine.textContent = activity ?? '';
    }
  }
}
