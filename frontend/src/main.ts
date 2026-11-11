import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { fetchAgents } from './api';
import { CameraDirector } from './camera';
import { CORKBOARD, WallBoard, WHITEBOARD } from './board';
import { ChatPanel } from './chat';
import { CoachingPanel } from './coaching';
import { DraftsPanel } from './drafts';
import { JobsPanel } from './jobs';
import { LinkedInPanel } from './linkedin';
import { addLighting, buildOffice, DESK_POSITIONS } from './office';
import { ProfilePanel } from './profile';
import { StandupPanel } from './standup';
import { Worker } from './worker';
import './style.css';

const WORKER_COLORS = [0x2563eb, 0x16a34a, 0xd97706, 0x9333ea];
// Rigged character models (GLB in public/models). Workers without one use the block figure.
// Built in Blender from assets/characters/<name>.py.
const WORKER_MODELS: Record<string, string> = {
  content: '/models/nora.glb',
  optimizer: '/models/leo.glb',
  scout: '/models/maya.glb',
  coach: '/models/kai.glb',
};

const canvas = document.querySelector<HTMLCanvasElement>('#office')!;
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.05;

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x1b1d23);

const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 100);
camera.position.set(9, 9, 11);

const controls = new OrbitControls(camera, canvas);
controls.target.set(0, 0.5, 0);
controls.enableDamping = true;
controls.maxPolarAngle = Math.PI / 2.2;
controls.minDistance = 2; // close enough to frame a seated worker
controls.maxDistance = 25;

addLighting(scene, renderer);
buildOffice(scene);

const chat = new ChatPanel();
const director = new CameraDirector(camera, controls, () => ({ left: leftPanelWidth(), right: chat.coveredWidth }));
chat.onClose(() => director.returnHome());
const workers: Worker[] = [];
const agentsById = new Map<string, Awaited<ReturnType<typeof fetchAgents>>[number]>();

async function openChat(agentId: string): Promise<boolean> {
  const agent = agentsById.get(agentId);
  const worker = workers.find((w) => w.agentId === agentId);
  if (!agent || !worker) return false;
  const opened = chat.open(agent, worker); // shows the panel at once, then loads the history
  director.focus(worker.group.position);
  await opened;
  return true;
}

/** Open a worker's chat with a message, sent now or left in the box to finish. */
function askAgent(agentId: string) {
  return async (message: string, sendNow: boolean) => {
    if (await openChat(agentId)) chat.ask(message, sendNow);
  };
}

const profilePanel = new ProfilePanel();
const draftsPanel = new DraftsPanel(askAgent('content'));
const linkedInPanel = new LinkedInPanel(askAgent('optimizer'));
const jobsPanel = new JobsPanel(askAgent('scout'));
const coachingPanel = new CoachingPanel(askAgent('coach'));
const standupPanel = new StandupPanel((agentId, prompt) => void askAgent(agentId)(prompt, true));

// Standup lines appear over the workers' heads one after another, and go away when the panel closes.
const STANDUP_STAGGER_MS = 700;
let standupTimers: number[] = [];
standupPanel.onChange((standup) => {
  standupTimers.forEach((timer) => clearTimeout(timer));
  standupTimers = [];
  for (const worker of workers) worker.speech = null;
  standup?.updates.forEach((update, index) => {
    const worker = workers.find((w) => w.agentId === update.agent_id);
    if (worker) standupTimers.push(window.setTimeout(() => (worker.speech = update.line), index * STANDUP_STAGGER_MS));
  });
});

// The board panels share the left side: opening one closes the others.
const leftPanels = {
  profile: profilePanel,
  drafts: draftsPanel,
  linkedin: linkedInPanel,
  jobs: jobsPanel,
  coaching: coachingPanel,
  standup: standupPanel,
};
/** Width (px) the open left panel covers, 0 when none is open. */
function leftPanelWidth(): number {
  const open = Object.values(leftPanels).find((panel) => !panel.root.hidden);
  return open ? open.root.getBoundingClientRect().right : 0;
}

function toggleLeftPanel(name: keyof typeof leftPanels): void {
  for (const [key, panel] of Object.entries(leftPanels)) {
    const open = key === name && panel.root.hidden;
    const wasOpen = !panel.root.hidden;
    panel.root.hidden = !open;
    if (open) void panel.refresh();
    else if (wasOpen && panel === standupPanel) standupPanel.hidden();
  }
}

const profileBoard = new WallBoard(CORKBOARD, new THREE.Vector3(-5, 2.1, -6.85));
profileBoard.mesh.userData.panel = 'profile';
const jobsBoard = new WallBoard(WHITEBOARD, new THREE.Vector3(0, 2.1, -6.85));
jobsBoard.mesh.userData.panel = 'jobs';
const linkedInBoard = new WallBoard(CORKBOARD, new THREE.Vector3(5, 2.1, -6.85));
linkedInBoard.mesh.userData.panel = 'linkedin';
const draftsBoard = new WallBoard(WHITEBOARD, new THREE.Vector3(-7.85, 2.1, 2.5), Math.PI / 2);
draftsBoard.mesh.userData.panel = 'drafts';
const coachingBoard = new WallBoard(CORKBOARD, new THREE.Vector3(-7.85, 2.1, -3), Math.PI / 2);
coachingBoard.mesh.userData.panel = 'coaching';
const boards = [profileBoard.mesh, jobsBoard.mesh, linkedInBoard.mesh, draftsBoard.mesh, coachingBoard.mesh];
scene.add(...boards);

profilePanel.onChange(({ facts, gaps }) =>
  profileBoard.draw({
    title: 'CAREER PROFILE',
    subtitle: gaps.length ? `${facts.length} facts · missing: ${gaps.join(', ')}` : `${facts.length} facts · complete`,
    noteCount: facts.length,
  }),
);
draftsPanel.onChange(({ drafts, ideas }) => {
  const ready = drafts.filter((d) => d.status === 'ready').length;
  const fresh = ideas.filter((i) => i.status === 'new').length;
  draftsBoard.draw({
    title: 'DRAFTS',
    subtitle: `${drafts.length} drafts · ${ready} ready · ${fresh} new ideas`,
    noteCount: drafts.filter((d) => d.status !== 'posted').length,
  });
});
linkedInPanel.onChange(({ sections }) => {
  const applied = sections.filter((s) => s.status === 'applied').length;
  linkedInBoard.draw({
    title: 'LINKEDIN PROFILE',
    subtitle: sections.length ? `${sections.length} rewrites · ${applied} applied` : 'No rewrites yet · talk to Leo',
    noteCount: sections.filter((s) => s.status !== 'applied').length,
  });
});
jobsPanel.onChange(({ jobs, outreach }) => {
  const strong = jobs.filter((j) => (j.fit_score ?? 0) >= 60).length;
  const active = jobs.filter((j) => ['applying', 'applied', 'interview', 'offer'].includes(j.status)).length;
  jobsBoard.draw({
    title: 'JOBS',
    subtitle: jobs.length
      ? `${jobs.length} jobs · ${strong} good fits · ${active} in progress · ${outreach.length} notes`
      : 'No jobs yet · talk to Maya',
    noteCount: jobs.length,
  });
});
coachingPanel.onChange(({ interviews, gaps }) => {
  const latest = interviews.find((i) => i.average_score !== null);
  const open = gaps.filter((g) => g.status !== 'closed');
  coachingBoard.draw({
    title: 'COACHING',
    subtitle: [
      latest ? `last interview ${latest.average_score}/10` : 'no interviews yet',
      `${open.length} open gaps (${open.filter((g) => g.severity === 'high').length} high)`,
    ].join(' · '),
    noteCount: open.length,
  });
});
void profilePanel.refresh();
void draftsPanel.refresh();
void linkedInPanel.refresh();
void jobsPanel.refresh();
void coachingPanel.refresh();

const hud = document.createElement('div');
hud.className = 'hud';
const standupButton = document.createElement('button');
standupButton.type = 'button';
standupButton.className = 'hud-button standup';
standupButton.textContent = 'Morning standup';
standupButton.addEventListener('click', () => toggleLeftPanel('standup'));
hud.appendChild(standupButton);
for (const [name, label] of [['profile', 'Career Profile'], ['drafts', 'Drafts'], ['linkedin', 'LinkedIn Profile'], ['jobs', 'Jobs'], ['coaching', 'Coaching']] as const) {
  const hudButton = document.createElement('button');
  hudButton.type = 'button';
  hudButton.className = 'hud-button';
  hudButton.textContent = label;
  hudButton.addEventListener('click', () => toggleLeftPanel(name));
  hud.appendChild(hudButton);
}
document.body.appendChild(hud);

fetchAgents()
  .then((agents) => {
    agents.forEach((agent, index) => {
      agentsById.set(agent.id, agent);
      const worker = new Worker(
        agent.id,
        agent.name,
        agent.role,
        WORKER_COLORS[index % WORKER_COLORS.length],
        DESK_POSITIONS[index],
        WORKER_MODELS[agent.id],
      );
      workers.push(worker);
      scene.add(worker.group);
    });
    // ?focus=<agentId> opens the office looking at that worker (handy for screenshots).
    const focus = workers.find((w) => w.agentId === new URLSearchParams(location.search).get('focus'));
    if (focus) director.focus(focus.group.position, true);
  })
  .catch((error) => {
    const banner = document.createElement('div');
    banner.className = 'banner';
    banner.textContent = `Backend not reachable: ${error}. Start it with "uv run uvicorn app.main:app" in backend/.`;
    document.body.appendChild(banner);
  });

// Click a worker to open their chat. Ignore drags so orbiting doesn't open chats.
const raycaster = new THREE.Raycaster();
const pointer = new THREE.Vector2();
let downAt = { x: 0, y: 0 };
canvas.addEventListener('pointerdown', (event) => (downAt = { x: event.clientX, y: event.clientY }));
canvas.addEventListener('pointerup', (event) => {
  if (Math.hypot(event.clientX - downAt.x, event.clientY - downAt.y) > 5) return;
  pointer.set((event.clientX / window.innerWidth) * 2 - 1, -(event.clientY / window.innerHeight) * 2 + 1);
  raycaster.setFromCamera(pointer, camera);
  const hit = raycaster.intersectObjects([...boards, ...workers.map((w) => w.hitbox)], false)[0];
  const panel = hit?.object.userData.panel as keyof typeof leftPanels | undefined;
  if (panel) {
    toggleLeftPanel(panel);
    return;
  }
  const agentId = hit?.object.userData.agentId as string | undefined;
  if (agentId) void openChat(agentId);
});
canvas.addEventListener('pointermove', (event) => {
  pointer.set((event.clientX / window.innerWidth) * 2 - 1, -(event.clientY / window.innerHeight) * 2 + 1);
  raycaster.setFromCamera(pointer, camera);
  const overWorker = raycaster.intersectObjects([...boards, ...workers.map((w) => w.hitbox)], false).length > 0;
  canvas.style.cursor = overWorker ? 'pointer' : 'grab';
});

function resize(): void {
  const { innerWidth: width, innerHeight: height } = window;
  renderer.setSize(width, height, false);
  camera.aspect = width / height;
  camera.updateProjectionMatrix();
}
window.addEventListener('resize', resize);
resize();

renderer.setAnimationLoop((time) => {
  director.update(time);
  controls.update();
  for (const worker of workers) {
    worker.update(time);
    worker.updateLabel(camera, window.innerWidth, window.innerHeight);
  }
  renderer.render(scene, camera);
});
