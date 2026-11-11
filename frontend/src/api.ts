export interface QuickAction {
  label: string;
  prompt: string;
  /** false: put the prompt in the input box for the user to finish (e.g. paste something). */
  send?: boolean;
}

export interface AgentInfo {
  id: string;
  name: string;
  role: string;
  quick_actions: QuickAction[];
}

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

export type ChatEvent =
  | { type: 'text'; text: string }
  | { type: 'tool'; name: string }
  | { type: 'done'; session_id: string }
  | { type: 'error'; message: string };

export async function fetchAgents(): Promise<AgentInfo[]> {
  const response = await fetch('/api/agents');
  if (!response.ok) throw new Error(`Failed to load agents (${response.status})`);
  return response.json();
}

export async function fetchMessages(agentId: string): Promise<ChatMessage[]> {
  const response = await fetch(`/api/agents/${agentId}/messages`);
  if (!response.ok) throw new Error(`Failed to load messages (${response.status})`);
  return response.json();
}

/** POST a message and yield server-sent events as they arrive. */
export async function* streamChat(agentId: string, message: string): AsyncGenerator<ChatEvent> {
  const response = await fetch(`/api/agents/${agentId}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message }),
  });
  if (!response.ok || !response.body) throw new Error(`Chat failed (${response.status})`);

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = '';
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value;
    const frames = buffer.split('\n\n');
    buffer = frames.pop() ?? '';
    for (const frame of frames) {
      if (frame.startsWith('data: ')) yield JSON.parse(frame.slice('data: '.length));
    }
  }
}

export interface ProfileFact {
  id: number;
  category: string;
  fact: string;
  source: string;
  updated_at: string;
}

export interface Profile {
  facts: ProfileFact[];
  gaps: string[];
  categories: string[];
}

async function send<T>(method: string, url: string, body?: unknown): Promise<T> {
  const response = await fetch(url, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    throw new Error(detail?.detail ?? `Request failed (${response.status})`);
  }
  return (response.status === 204 ? undefined : await response.json()) as T;
}

export const fetchProfile = () => send<Profile>('GET', '/api/profile');
export const addFact = (category: string, fact: string) => send<ProfileFact>('POST', '/api/profile', { category, fact });
export const editFact = (id: number, fact: string) => send<ProfileFact>('PATCH', `/api/profile/${id}`, { fact });
export const deleteFact = (id: number) => send<void>('DELETE', `/api/profile/${id}`);

/** Fired after anything (a worker's tool or the board) changes the profile. */
export const PROFILE_CHANGED = 'profile-changed';

export interface Idea {
  id: number;
  title: string;
  hook: string;
  angle: string;
  why: string;
  pillar: string;
  proof_missing: string;
  status: 'new' | 'drafted';
}

export interface Draft {
  id: number;
  idea_id: number | null;
  title: string;
  pillar: string;
  format: string;
  body: string;
  asset_needed: string;
  status: 'draft' | 'ready' | 'posted';
  version: number;
  change_note: string;
  updated_at: string;
}

export interface DraftBoard {
  ideas: Idea[];
  drafts: Draft[];
}

export const fetchDrafts = () => send<DraftBoard>('GET', '/api/drafts');
export const updateDraft = (id: number, changes: { body?: string; status?: string }) =>
  send<Draft>('PATCH', `/api/drafts/${id}`, changes);
export const deleteDraft = (id: number) => send<void>('DELETE', `/api/drafts/${id}`);
export const updateIdea = (id: number, status: string) => send<Idea>('PATCH', `/api/ideas/${id}`, { status });

/** Fired after a worker or the board changes ideas or drafts. */
export const DRAFTS_CHANGED = 'drafts-changed';

export interface LinkedInSection {
  id: number;
  section: string;
  label: string;
  original: string;
  rewrite: string;
  rationale: string;
  keywords: string[];
  sources: string[];
  status: 'proposed' | 'applied';
  version: number;
  previous_rewrite: string;
  updated_at: string;
}

export interface LinkedInBoard {
  sections: LinkedInSection[];
  limits: Record<string, number>;
}

export const fetchLinkedIn = () => send<LinkedInBoard>('GET', '/api/linkedin');
export const updateSection = (id: number, changes: { rewrite?: string; status?: string }) =>
  send<LinkedInSection>('PATCH', `/api/linkedin/${id}`, changes);
export const deleteSection = (id: number) => send<void>('DELETE', `/api/linkedin/${id}`);

/** Fired after a worker or the board changes the LinkedIn section rewrites. */
export const LINKEDIN_CHANGED = 'linkedin-changed';

export interface Job {
  id: number;
  title: string;
  company: string;
  url: string;
  location: string;
  work_mode: string;
  posted: string;
  origin: 'search' | 'pasted';
  summary: string;
  fit_score: number | null;
  matched: string[];
  gaps: string[];
  notes: string;
  status: string;
}

export interface Outreach {
  id: number;
  job_id: number | null;
  target: string;
  how_to_find: string;
  message: string;
  status: 'draft' | 'sent' | 'replied';
}

export interface JobsBoard {
  jobs: Job[];
  outreach: Outreach[];
  statuses: string[];
}

export const fetchJobs = () => send<JobsBoard>('GET', '/api/jobs');
export const updateJob = (id: number, changes: { status?: string; notes?: string }) =>
  send<Job>('PATCH', `/api/jobs/${id}`, changes);
export const deleteJob = (id: number) => send<void>('DELETE', `/api/jobs/${id}`);
export const updateOutreach = (id: number, changes: { message?: string; status?: string }) =>
  send<Outreach>('PATCH', `/api/outreach/${id}`, changes);
export const deleteOutreach = (id: number) => send<void>('DELETE', `/api/outreach/${id}`);

/** Fired after a worker or the board changes jobs or outreach notes. */
export const JOBS_CHANGED = 'jobs-changed';

export interface InterviewAnswer {
  id: number;
  area: string;
  question: string;
  answer: string;
  score: number;
  feedback: string;
  strong_answer: string;
}

export interface Interview {
  id: number;
  topic: string;
  level: string;
  planned_questions: number;
  status: 'in_progress' | 'finished';
  summary: string;
  started_at: string;
  average_score: number | null;
  answers: InterviewAnswer[];
}

export interface SkillGap {
  id: number;
  skill: string;
  severity: 'high' | 'medium' | 'low';
  evidence: string;
  next_step: string;
  status: string;
  source: string;
}

export interface PortfolioProject {
  id: number;
  title: string;
  pitch: string;
  closes_gaps: string[];
  stack: string[];
  steps: string[];
  effort: string;
  status: string;
}

export interface CoachingBoard {
  interviews: Interview[];
  gaps: SkillGap[];
  projects: PortfolioProject[];
  gap_statuses: string[];
  project_statuses: string[];
}

export const fetchCoaching = () => send<CoachingBoard>('GET', '/api/coaching');
export const updateGap = (id: number, status: string) => send<SkillGap>('PATCH', `/api/gaps/${id}`, { status });
export const deleteGap = (id: number) => send<void>('DELETE', `/api/gaps/${id}`);
export const updatePortfolioProject = (id: number, status: string) =>
  send<PortfolioProject>('PATCH', `/api/portfolio/${id}`, { status });
export const deletePortfolioProject = (id: number) => send<void>('DELETE', `/api/portfolio/${id}`);
export const deleteInterview = (id: number) => send<void>('DELETE', `/api/interviews/${id}`);

/** Fired after a worker or the board changes interviews, gaps or projects. */
export const COACHING_CHANGED = 'coaching-changed';

export interface StandupUpdate {
  agent_id: string;
  name: string;
  /** One line in the worker's voice. */
  line: string;
  /** The board facts the line is based on. */
  facts: string[];
  /** The step the worker suggests, sent to them as a chat message. */
  next: { label: string; prompt: string };
}

export interface Standup {
  day: string;
  updates: StandupUpdate[];
  created_at: string;
}

/** Today's standup (run on the first call of the day), or a fresh run with `rerun`. */
export const fetchStandup = (rerun = false) => send<Standup>(rerun ? 'POST' : 'GET', '/api/standup');
