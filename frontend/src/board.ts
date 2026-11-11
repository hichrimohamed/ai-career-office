import * as THREE from 'three';

export interface BoardContent {
  title: string;
  subtitle: string;
  noteCount: number;
}

interface BoardStyle {
  background: string;
  frame: number;
  ink: string;
  noteColors: string[];
  pinned: boolean;
}

export const CORKBOARD: BoardStyle = {
  background: '#c8a46a',
  frame: 0x6b4a2f,
  ink: '#2b1d10',
  noteColors: ['#fff7ae', '#c7f0d8', '#cfe3ff', '#ffd6e0'],
  pinned: true,
};

export const WHITEBOARD: BoardStyle = {
  background: '#f7f8fa',
  frame: 0x9aa3ad,
  ink: '#1f2a37',
  noteColors: ['#fff1a8', '#ffd8a8', '#c3e6ff'],
  pinned: false,
};

/** A wall-mounted board with a canvas face: a title, a subtitle and one note per item. Clickable. */
export class WallBoard {
  readonly mesh: THREE.Mesh;
  private readonly canvas = document.createElement('canvas');
  private readonly texture: THREE.CanvasTexture;
  private readonly style: BoardStyle;

  constructor(style: BoardStyle, position: THREE.Vector3, rotationY = 0) {
    this.style = style;
    this.canvas.width = 512;
    this.canvas.height = 320;
    this.texture = new THREE.CanvasTexture(this.canvas);
    this.texture.colorSpace = THREE.SRGBColorSpace;

    const frame = new THREE.MeshStandardMaterial({ color: style.frame });
    const face = new THREE.MeshStandardMaterial({ map: this.texture });
    // BoxGeometry face order: +x, -x, +y, -y, +z (front), -z.
    this.mesh = new THREE.Mesh(new THREE.BoxGeometry(3.2, 2, 0.08), [frame, frame, frame, frame, face, frame]);
    this.mesh.position.copy(position);
    this.mesh.rotation.y = rotationY;
  }

  draw({ title, subtitle, noteCount }: BoardContent): void {
    const ctx = this.canvas.getContext('2d')!;
    const { width, height } = this.canvas;
    const { background, ink, noteColors, pinned } = this.style;
    ctx.fillStyle = background;
    ctx.fillRect(0, 0, width, height);

    // One sticky note per item, up to 12.
    for (let i = 0; i < Math.min(noteCount, 12); i++) {
      const x = 30 + (i % 6) * 78;
      const y = 120 + Math.floor(i / 6) * 90;
      ctx.fillStyle = noteColors[i % noteColors.length];
      ctx.fillRect(x, y, 62, 62);
      if (pinned) {
        ctx.fillStyle = '#c0392b';
        ctx.beginPath();
        ctx.arc(x + 31, y + 8, 5, 0, Math.PI * 2);
        ctx.fill();
      }
    }

    ctx.fillStyle = ink;
    ctx.font = 'bold 40px system-ui, sans-serif';
    ctx.fillText(title, 30, 58);
    ctx.font = '24px system-ui, sans-serif';
    ctx.fillText(subtitle, 30, 96, width - 60);
    this.texture.needsUpdate = true;
  }
}
