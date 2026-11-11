import {
  deleteDraft,
  type Draft,
  type DraftBoard,
  DRAFTS_CHANGED,
  fetchDrafts,
  type Idea,
  updateDraft,
  updateIdea,
} from './api';
import { button, copyButton, el } from './ui';

const HOOK_CHARS = 140; // roughly what LinkedIn shows before "see more"
const TARGET = { min: 900, max: 1300 };
const STATUSES: Draft['status'][] = ['draft', 'ready', 'posted'];

type Tab = 'drafts' | 'ideas';

/** Left-hand panel with Nora's saved drafts (copy, edit, revise) and her idea backlog. */
export class DraftsPanel {
  readonly root: HTMLElement;
  private readonly list: HTMLElement;
  private readonly error: HTMLElement;
  private readonly tabs: Record<Tab, HTMLButtonElement>;
  private tab: Tab = 'drafts';
  private board: DraftBoard = { ideas: [], drafts: [] };
  private readonly listeners: ((board: DraftBoard) => void)[] = [];
  private readonly askNora: (message: string, send: boolean) => void;

  /** `askNora(message, send)`: open Nora's chat with the message, sending it now or leaving it to finish. */
  constructor(askNora: (message: string, send: boolean) => void) {
    this.askNora = askNora;
    this.root = el('aside', 'side-panel drafts-panel');
    this.root.hidden = true;
    this.root.innerHTML = `
      <header>
        <div class="chat-title"><strong>Drafts</strong><span>Nora's posts, ready to copy into LinkedIn</span></div>
        <button type="button" class="chat-close" aria-label="Close drafts">×</button>
      </header>
      <nav class="tabs" role="tablist">
        <button type="button" role="tab" data-tab="drafts">Drafts</button>
        <button type="button" role="tab" data-tab="ideas">Ideas</button>
      </nav>
      <p class="panel-error" hidden></p>
      <div class="drafts-list"></div>`;
    document.body.appendChild(this.root);

    this.list = this.root.querySelector('.drafts-list')!;
    this.error = this.root.querySelector('.panel-error')!;
    this.tabs = {
      drafts: this.root.querySelector('[data-tab="drafts"]')!,
      ideas: this.root.querySelector('[data-tab="ideas"]')!,
    };
    for (const [tab, node] of Object.entries(this.tabs) as [Tab, HTMLButtonElement][]) {
      node.addEventListener('click', () => {
        this.tab = tab;
        this.render();
      });
    }
    this.root.querySelector('.chat-close')!.addEventListener('click', () => (this.root.hidden = true));
    window.addEventListener(DRAFTS_CHANGED, () => void this.refresh());
  }

  onChange(listener: (board: DraftBoard) => void): void {
    this.listeners.push(listener);
  }

  async refresh(): Promise<void> {
    try {
      this.board = await fetchDrafts();
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
      window.dispatchEvent(new Event(DRAFTS_CHANGED));
    } catch (error) {
      this.showError(error instanceof Error ? error.message : String(error));
    }
  }

  private showError(message: string | null): void {
    this.error.hidden = message === null;
    this.error.textContent = message ?? '';
  }

  private render(): void {
    const { drafts, ideas } = this.board;
    this.tabs.drafts.textContent = `Drafts (${drafts.length})`;
    this.tabs.ideas.textContent = `Ideas (${ideas.filter((i) => i.status === 'new').length})`;
    for (const [tab, node] of Object.entries(this.tabs)) node.setAttribute('aria-selected', String(tab === this.tab));

    this.list.replaceChildren();
    const items = this.tab === 'drafts' ? drafts.map((d) => this.renderDraft(d)) : ideas.map((i) => this.renderIdea(i));
    if (items.length) this.list.append(...items);
    else
      this.list.append(
        el(
          'p',
          'profile-empty',
          this.tab === 'drafts'
            ? 'No drafts yet. Ask Nora for a weekly brief or to draft an idea.'
            : 'No ideas yet. Nora saves them when she writes a brief.',
        ),
      );
  }

  private renderDraft(draft: Draft): HTMLElement {
    const card = el('article', `card status-${draft.status}`);

    const head = el('div', 'card-head');
    head.append(el('h3', '', draft.title), el('span', 'card-id', `#${draft.id}`));
    const meta = el('p', 'card-meta', `${draft.pillar} · ${draft.format} · v${draft.version}`);
    card.append(head, meta);
    if (draft.change_note) card.append(el('p', 'card-note', `Last change: ${draft.change_note}`));

    const body = el('div', 'post-body');
    body.append(el('mark', 'post-hook', draft.body.slice(0, HOOK_CHARS)), draft.body.slice(HOOK_CHARS));
    body.title = 'Highlighted: what shows before "see more"';

    const chars = draft.body.length;
    const inRange = chars >= TARGET.min && chars <= TARGET.max;
    const count = el('p', `char-count ${inRange ? 'ok' : 'off'}`, `${chars} characters (target ${TARGET.min}–${TARGET.max})`);
    card.append(body, count);
    if (draft.asset_needed) card.append(el('p', 'card-asset', `Asset: ${draft.asset_needed}`));

    const actions = el('div', 'card-actions');
    const copy = copyButton(() => draft.body, (message) => this.showError(message));
    const edit = button('Edit', () => this.editInPlace(card, body, draft));
    const revise = button('Revise with Nora', () => this.askNora(`Revise draft #${draft.id}: `, false));

    const status = el('select', 'card-status');
    status.setAttribute('aria-label', `Status of draft #${draft.id}`);
    for (const value of STATUSES) status.add(new Option(value, value, false, value === draft.status));
    status.addEventListener('change', () => void this.mutate(() => updateDraft(draft.id, { status: status.value })));

    const remove = button('Delete', () => void this.mutate(() => deleteDraft(draft.id)), 'card-button danger');
    actions.append(copy, edit, revise, status, remove);
    card.append(actions);
    return card;
  }

  private editInPlace(card: HTMLElement, body: HTMLElement, draft: Draft): void {
    const editor = el('textarea', 'post-editor');
    editor.value = draft.body;
    editor.rows = Math.min(24, draft.body.split('\n').length + 3);
    const save = button('Save', () => void this.mutate(() => updateDraft(draft.id, { body: editor.value })), 'card-button primary');
    const cancel = button('Cancel', () => this.render());
    const bar = el('div', 'card-actions');
    bar.append(save, cancel);
    body.replaceWith(editor);
    card.querySelector('.card-actions')?.replaceWith(bar);
    editor.focus();
  }

  private renderIdea(idea: Idea): HTMLElement {
    const card = el('article', `card idea-${idea.status}`);
    const head = el('div', 'card-head');
    head.append(el('h3', '', idea.title), el('span', 'card-id', `#${idea.id}`));
    card.append(head, el('p', 'card-meta', `${idea.pillar}${idea.status === 'drafted' ? ' · drafted' : ''}`));
    card.append(el('blockquote', 'idea-hook', idea.hook));
    const details = el('dl', 'idea-details');
    for (const [label, value] of [['Angle', idea.angle], ['Why', idea.why], ['Proof missing', idea.proof_missing]]) {
      if (!value) continue;
      details.append(el('dt', '', label), el('dd', '', value));
    }
    card.append(details);

    const actions = el('div', 'card-actions');
    if (idea.status === 'new') actions.append(button('Draft this', () => this.askNora(`Draft idea #${idea.id}.`, true), 'card-button primary'));
    actions.append(button('Dismiss', () => void this.mutate(() => updateIdea(idea.id, 'dismissed')), 'card-button danger'));
    card.append(actions);
    return card;
  }
}
