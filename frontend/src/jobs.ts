import {
  deleteJob,
  deleteOutreach,
  fetchJobs,
  type Job,
  type JobsBoard,
  JOBS_CHANGED,
  type Outreach,
  updateJob,
  updateOutreach,
} from './api';
import { button, copyButton, el } from './ui';

const NOTE_LIMIT = 300;
const OUTREACH_STATUSES: Outreach['status'][] = ['draft', 'sent', 'replied'];

type Tab = 'jobs' | 'outreach';

function fitClass(score: number | null): string {
  if (score === null) return 'fit-none';
  if (score >= 80) return 'fit-high';
  if (score >= 60) return 'fit-mid';
  if (score >= 40) return 'fit-low';
  return 'fit-poor';
}

function tagList(values: string[], className: string): HTMLElement {
  const list = el('div', 'keyword-list');
  list.append(...values.map((value) => el('span', className, value)));
  return list;
}

/** Left-hand panel with Maya's saved jobs (fit, status) and outreach notes. */
export class JobsPanel {
  readonly root: HTMLElement;
  private readonly list: HTMLElement;
  private readonly error: HTMLElement;
  private readonly tabs: Record<Tab, HTMLButtonElement>;
  private tab: Tab = 'jobs';
  private board: JobsBoard = { jobs: [], outreach: [], statuses: [] };
  private readonly listeners: ((board: JobsBoard) => void)[] = [];
  private readonly askMaya: (message: string, send: boolean) => void;

  constructor(askMaya: (message: string, send: boolean) => void) {
    this.askMaya = askMaya;
    this.root = el('aside', 'side-panel jobs-panel');
    this.root.hidden = true;
    this.root.innerHTML = `
      <header>
        <div class="chat-title"><strong>Jobs</strong><span>Maya's openings, fit scores and outreach notes</span></div>
        <button type="button" class="chat-close" aria-label="Close jobs">×</button>
      </header>
      <nav class="tabs" role="tablist">
        <button type="button" role="tab" data-tab="jobs">Jobs</button>
        <button type="button" role="tab" data-tab="outreach">Outreach</button>
      </nav>
      <p class="panel-error" hidden></p>
      <div class="drafts-list"></div>`;
    document.body.appendChild(this.root);

    this.list = this.root.querySelector('.drafts-list')!;
    this.error = this.root.querySelector('.panel-error')!;
    this.tabs = {
      jobs: this.root.querySelector('[data-tab="jobs"]')!,
      outreach: this.root.querySelector('[data-tab="outreach"]')!,
    };
    for (const [tab, node] of Object.entries(this.tabs) as [Tab, HTMLButtonElement][]) {
      node.addEventListener('click', () => {
        this.tab = tab;
        this.render();
      });
    }
    this.root.querySelector('.chat-close')!.addEventListener('click', () => (this.root.hidden = true));
    window.addEventListener(JOBS_CHANGED, () => void this.refresh());
  }

  onChange(listener: (board: JobsBoard) => void): void {
    this.listeners.push(listener);
  }

  async refresh(): Promise<void> {
    try {
      this.board = await fetchJobs();
      this.render();
      this.listeners.forEach((listener) => listener(this.board));
    } catch (error) {
      this.showError(String(error));
    }
  }

  private async mutate(action: () => Promise<unknown>): Promise<void> {
    this.showError(null);
    try {
      await action();
      window.dispatchEvent(new Event(JOBS_CHANGED));
    } catch (error) {
      this.showError(error instanceof Error ? error.message : String(error));
    }
  }

  private showError(message: string | null): void {
    this.error.hidden = message === null;
    this.error.textContent = message ?? '';
  }

  private render(): void {
    const { jobs, outreach } = this.board;
    this.tabs.jobs.textContent = `Jobs (${jobs.length})`;
    this.tabs.outreach.textContent = `Outreach (${outreach.filter((o) => o.status === 'draft').length})`;
    for (const [tab, node] of Object.entries(this.tabs)) node.setAttribute('aria-selected', String(tab === this.tab));

    this.list.replaceChildren();
    if (this.tab === 'jobs') {
      if (jobs.length) this.list.append(...jobs.map((job) => this.renderJob(job)));
      else {
        const empty = el('div', 'profile-empty');
        empty.append(el('p', '', 'No jobs yet. Ask Maya to find openings, or paste a job post for a fit check.'));
        empty.append(
          button('Find AI jobs', () => this.askMaya('Find 5 recent AI engineer openings that fit my profile and target location. Save them with an honest fit score.', true), 'card-button primary'),
          button('Check a job post', () => this.askMaya('Check my fit for this job post:\n\n', false)),
        );
        this.list.append(empty);
      }
    } else if (outreach.length) {
      this.list.append(...outreach.map((note) => this.renderOutreach(note)));
    } else {
      this.list.append(el('p', 'profile-empty', 'No outreach notes yet. Ask Maya who to contact for a saved job.'));
    }
  }

  private renderJob(job: Job): HTMLElement {
    const card = el('article', `card job-status-${job.status}`);
    const head = el('div', 'card-head');
    const title = el('h3');
    title.append(`${job.title} · `, el('span', 'job-company', job.company));
    head.append(title, el('span', `fit-badge ${fitClass(job.fit_score)}`, job.fit_score === null ? 'no score' : `${job.fit_score}% fit`));
    card.append(head);

    const meta = [job.location, job.work_mode !== 'unknown' ? job.work_mode : '', job.posted !== 'unknown' ? `posted ${job.posted}` : 'posted date unknown', job.origin === 'pasted' ? 'pasted by you' : '']
      .filter(Boolean)
      .join(' · ');
    card.append(el('p', 'card-meta', meta));
    if (job.summary) card.append(el('p', '', job.summary));
    if (job.matched.length) card.append(el('h4', 'tag-heading', 'Matches'), tagList(job.matched, 'tag-match'));
    if (job.gaps.length) card.append(el('h4', 'tag-heading', 'Gaps'), tagList(job.gaps, 'gap-tag'));
    if (job.notes) card.append(el('p', 'card-note', job.notes));

    const actions = el('div', 'card-actions');
    if (job.url) {
      const link = el('a', 'card-button primary', 'Open posting');
      link.href = job.url;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      actions.append(link);
    }
    actions.append(button('Who to contact', () => this.askMaya(`For job #${job.id} (${job.title} at ${job.company}), who should I contact and what should I write? Save the notes.`, true)));

    const status = el('select', 'card-status');
    status.setAttribute('aria-label', `Status of ${job.title} at ${job.company}`);
    for (const value of this.board.statuses) status.add(new Option(value, value, false, value === job.status));
    status.addEventListener('change', () => void this.mutate(() => updateJob(job.id, { status: status.value })));
    actions.append(status, button('Delete', () => void this.mutate(() => deleteJob(job.id)), 'card-button danger'));
    card.append(actions);
    return card;
  }

  private renderOutreach(note: Outreach): HTMLElement {
    const card = el('article', `card status-${note.status === 'draft' ? 'draft' : 'posted'}`);
    const job = this.board.jobs.find((j) => j.id === note.job_id);
    const head = el('div', 'card-head');
    head.append(el('h3', '', note.target), el('span', 'card-id', `#${note.id}`));
    card.append(head);
    if (job) card.append(el('p', 'card-meta', `For: ${job.title} at ${job.company}`));
    if (note.how_to_find) {
      const find = el('p', 'card-meta');
      find.append('Find them on LinkedIn: ', el('code', '', note.how_to_find));
      card.append(find);
    }

    const body = el('div', 'post-body', note.message);
    card.append(body, el('p', `char-count ${note.message.length <= NOTE_LIMIT ? 'ok' : 'off'}`, `${note.message.length} / ${NOTE_LIMIT} characters`));

    const actions = el('div', 'card-actions');
    const status = el('select', 'card-status');
    status.setAttribute('aria-label', `Status of note #${note.id}`);
    for (const value of OUTREACH_STATUSES) status.add(new Option(value, value, false, value === note.status));
    status.addEventListener('change', () => void this.mutate(() => updateOutreach(note.id, { status: status.value })));
    actions.append(
      copyButton(() => note.message, (message) => this.showError(message)),
      ...(note.how_to_find
        ? [copyButton(() => note.how_to_find, (message) => this.showError(message), 'Copy search', 'card-button')]
        : []),
      button('Edit', () => this.editInPlace(card, body, note)),
      status,
      button('Delete', () => void this.mutate(() => deleteOutreach(note.id)), 'card-button danger'),
    );
    card.append(actions);
    return card;
  }

  private editInPlace(card: HTMLElement, body: HTMLElement, note: Outreach): void {
    const editor = el('textarea', 'post-editor');
    editor.value = note.message;
    editor.maxLength = NOTE_LIMIT;
    editor.rows = 5;
    const counter = el('p', 'char-count ok', `${note.message.length} / ${NOTE_LIMIT} characters`);
    editor.addEventListener('input', () => (counter.textContent = `${editor.value.length} / ${NOTE_LIMIT} characters`));
    const bar = el('div', 'card-actions');
    bar.append(
      button('Save', () => void this.mutate(() => updateOutreach(note.id, { message: editor.value })), 'card-button primary'),
      button('Cancel', () => this.render()),
    );
    body.replaceWith(editor);
    card.querySelector('.char-count')?.replaceWith(counter);
    card.querySelector('.card-actions')?.replaceWith(bar);
    editor.focus();
  }
}

