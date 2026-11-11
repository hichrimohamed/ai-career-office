import {
  type CoachingBoard,
  COACHING_CHANGED,
  deleteGap,
  deleteInterview,
  deletePortfolioProject,
  fetchCoaching,
  type Interview,
  type PortfolioProject,
  type SkillGap,
  updateGap,
  updatePortfolioProject,
} from './api';
import { button, el } from './ui';

type Tab = 'interviews' | 'gaps' | 'projects';

function scoreClass(score: number | null): string {
  if (score === null) return 'fit-none';
  if (score >= 8) return 'fit-high';
  if (score >= 6) return 'fit-mid';
  if (score >= 4) return 'fit-low';
  return 'fit-poor';
}

function statusSelect(label: string, value: string, options: string[], onChange: (value: string) => void): HTMLSelectElement {
  const select = el('select', 'card-status');
  select.setAttribute('aria-label', label);
  for (const option of options) select.add(new Option(option, option, false, option === value));
  select.addEventListener('change', () => onChange(select.value));
  return select;
}

/** Left-hand panel with Kai's mock interviews, skill gaps and portfolio projects. */
export class CoachingPanel {
  readonly root: HTMLElement;
  private readonly list: HTMLElement;
  private readonly error: HTMLElement;
  private readonly tabs: Record<Tab, HTMLButtonElement>;
  private tab: Tab = 'interviews';
  private board: CoachingBoard = { interviews: [], gaps: [], projects: [], gap_statuses: [], project_statuses: [] };
  private readonly listeners: ((board: CoachingBoard) => void)[] = [];
  private readonly askKai: (message: string, send: boolean) => void;

  constructor(askKai: (message: string, send: boolean) => void) {
    this.askKai = askKai;
    this.root = el('aside', 'side-panel coaching-panel');
    this.root.hidden = true;
    this.root.innerHTML = `
      <header>
        <div class="chat-title"><strong>Coaching</strong><span>Kai's mock interviews, your gaps and what to build next</span></div>
        <button type="button" class="chat-close" aria-label="Close coaching">×</button>
      </header>
      <nav class="tabs" role="tablist">
        <button type="button" role="tab" data-tab="interviews">Interviews</button>
        <button type="button" role="tab" data-tab="gaps">Gaps</button>
        <button type="button" role="tab" data-tab="projects">Projects</button>
      </nav>
      <p class="panel-error" hidden></p>
      <div class="drafts-list"></div>`;
    document.body.appendChild(this.root);

    this.list = this.root.querySelector('.drafts-list')!;
    this.error = this.root.querySelector('.panel-error')!;
    this.tabs = {
      interviews: this.root.querySelector('[data-tab="interviews"]')!,
      gaps: this.root.querySelector('[data-tab="gaps"]')!,
      projects: this.root.querySelector('[data-tab="projects"]')!,
    };
    for (const [tab, node] of Object.entries(this.tabs) as [Tab, HTMLButtonElement][]) {
      node.addEventListener('click', () => {
        this.tab = tab;
        this.render();
      });
    }
    this.root.querySelector('.chat-close')!.addEventListener('click', () => (this.root.hidden = true));
    window.addEventListener(COACHING_CHANGED, () => void this.refresh());
  }

  onChange(listener: (board: CoachingBoard) => void): void {
    this.listeners.push(listener);
  }

  async refresh(): Promise<void> {
    try {
      this.board = await fetchCoaching();
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
      window.dispatchEvent(new Event(COACHING_CHANGED));
    } catch (error) {
      this.showError(error instanceof Error ? error.message : String(error));
    }
  }

  private showError(message: string | null): void {
    this.error.hidden = message === null;
    this.error.textContent = message ?? '';
  }

  private render(): void {
    const { interviews, gaps, projects } = this.board;
    this.tabs.interviews.textContent = `Interviews (${interviews.length})`;
    this.tabs.gaps.textContent = `Gaps (${gaps.filter((g) => g.status !== 'closed').length})`;
    this.tabs.projects.textContent = `Projects (${projects.length})`;
    for (const [tab, node] of Object.entries(this.tabs)) node.setAttribute('aria-selected', String(tab === this.tab));

    this.list.replaceChildren();
    const [items, emptyText, emptyAction] = {
      interviews: [interviews.map((i) => this.renderInterview(i)), 'No mock interviews yet.', ['Start a mock interview', 'Start a 5-question mock interview for a junior-to-mid AI engineer role. Mix LLM fundamentals, RAG, evals, agents and system design.']],
      gaps: [gaps.map((g) => this.renderGap(g)), 'No skill gaps tracked yet.', ['Find my gaps', 'Review my profile, saved jobs and past interviews. Update my skill gaps and suggest one portfolio project for the biggest one.']],
      projects: [projects.map((p) => this.renderProject(p)), 'No project suggestions yet.', ['Suggest a project', 'Suggest one portfolio project that closes my biggest skill gap.']],
    }[this.tab] as [HTMLElement[], string, [string, string]];

    if (items.length) {
      this.list.append(...items);
      return;
    }
    const empty = el('div', 'profile-empty');
    empty.append(el('p', '', emptyText), button(emptyAction[0], () => this.askKai(emptyAction[1], true), 'card-button primary'));
    this.list.append(empty);
  }

  private renderInterview(interview: Interview): HTMLElement {
    const card = el('article', 'card');
    const head = el('div', 'card-head');
    const average = interview.average_score;
    head.append(el('h3', '', interview.topic), el('span', `fit-badge ${scoreClass(average)}`, average === null ? 'no answers' : `${average}/10`));
    const progress = `${interview.answers.length}/${interview.planned_questions} answered`;
    card.append(head, el('p', 'card-meta', `${interview.level} · ${progress} · ${interview.status === 'finished' ? 'finished' : 'in progress'} · ${interview.started_at.slice(0, 10)}`));
    if (interview.summary) card.append(el('p', 'card-note', interview.summary));

    for (const [index, answer] of interview.answers.entries()) {
      const item = el('details', 'qa');
      const summary = el('summary');
      summary.append(el('span', `fit-badge ${scoreClass(answer.score)}`, `${answer.score}`), ` Q${index + 1} (${answer.area}): ${answer.question}`);
      item.append(summary);
      item.append(el('h4', 'tag-heading', 'Your answer'), el('p', 'qa-text', answer.answer));
      item.append(el('h4', 'tag-heading', 'Feedback'), el('p', 'qa-text', answer.feedback));
      if (answer.strong_answer) item.append(el('h4', 'tag-heading', 'A strong answer covers'), el('p', 'qa-text', answer.strong_answer));
      card.append(item);
    }

    const actions = el('div', 'card-actions');
    if (interview.status === 'in_progress') actions.append(button('Continue with Kai', () => this.askKai(`Let's continue mock interview #${interview.id}.`, true), 'card-button primary'));
    actions.append(button('Delete', () => void this.mutate(() => deleteInterview(interview.id)), 'card-button danger'));
    card.append(actions);
    return card;
  }

  private renderGap(gap: SkillGap): HTMLElement {
    const card = el('article', `card severity-${gap.severity} ${gap.status === 'closed' ? 'status-posted' : ''}`);
    const head = el('div', 'card-head');
    head.append(el('h3', '', gap.skill), el('span', `severity-badge severity-${gap.severity}`, gap.severity));
    card.append(head, el('p', '', gap.evidence));
    if (gap.next_step) card.append(el('p', 'card-asset', `Next step: ${gap.next_step}`));

    const actions = el('div', 'card-actions');
    actions.append(
      button('Plan a project', () => this.askKai(`Suggest a portfolio project that closes my "${gap.skill}" gap.`, true), 'card-button primary'),
      statusSelect(`Status of ${gap.skill}`, gap.status, this.board.gap_statuses, (value) => void this.mutate(() => updateGap(gap.id, value))),
      button('Delete', () => void this.mutate(() => deleteGap(gap.id)), 'card-button danger'),
    );
    card.append(actions);
    return card;
  }

  private renderProject(project: PortfolioProject): HTMLElement {
    const card = el('article', `card ${project.status === 'shipped' ? 'status-ready' : ''}`);
    const head = el('div', 'card-head');
    head.append(el('h3', '', project.title), el('span', 'card-id', project.effort));
    card.append(head, el('p', '', project.pitch));
    if (project.closes_gaps.length) {
      const gaps = el('div', 'keyword-list');
      gaps.append(...project.closes_gaps.map((gap) => el('span', 'gap-tag', gap)));
      card.append(el('h4', 'tag-heading', 'Closes'), gaps);
    }
    if (project.stack.length) card.append(el('p', 'card-meta', `Stack: ${project.stack.join(', ')}`));
    const steps = el('ol', 'project-steps');
    steps.append(...project.steps.map((step) => el('li', '', step)));
    card.append(el('h4', 'tag-heading', 'Plan'), steps);

    const actions = el('div', 'card-actions');
    actions.append(
      statusSelect(`Status of ${project.title}`, project.status, this.board.project_statuses, (value) =>
        void this.mutate(() => updatePortfolioProject(project.id, value)),
      ),
      button('Delete', () => void this.mutate(() => deletePortfolioProject(project.id)), 'card-button danger'),
    );
    card.append(actions);
    return card;
  }
}
