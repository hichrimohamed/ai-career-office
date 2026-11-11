import { deleteSection, fetchLinkedIn, type LinkedInBoard, LINKEDIN_CHANGED, type LinkedInSection, updateSection } from './api';
import { button, copyButton, el } from './ui';

const SECTION_NAMES: Record<string, string> = {
  headline: 'Headline',
  about: 'About',
  experience: 'Experience',
  skills: 'Skills',
  featured: 'Featured',
};

/** Left-hand panel with Leo's rewrites, each next to the original LinkedIn text. */
export class LinkedInPanel {
  readonly root: HTMLElement;
  private readonly list: HTMLElement;
  private readonly error: HTMLElement;
  private board: LinkedInBoard = { sections: [], limits: {} };
  private readonly listeners: ((board: LinkedInBoard) => void)[] = [];
  private readonly askLeo: (message: string, send: boolean) => void;

  constructor(askLeo: (message: string, send: boolean) => void) {
    this.askLeo = askLeo;
    this.root = el('aside', 'side-panel linkedin-panel');
    this.root.hidden = true;
    this.root.innerHTML = `
      <header>
        <div class="chat-title"><strong>LinkedIn Profile</strong><span>Leo's rewrites, next to what's live now</span></div>
        <button type="button" class="chat-close" aria-label="Close LinkedIn profile">×</button>
      </header>
      <p class="panel-error" hidden></p>
      <div class="drafts-list"></div>`;
    document.body.appendChild(this.root);

    this.list = this.root.querySelector('.drafts-list')!;
    this.error = this.root.querySelector('.panel-error')!;
    this.root.querySelector('.chat-close')!.addEventListener('click', () => (this.root.hidden = true));
    window.addEventListener(LINKEDIN_CHANGED, () => void this.refresh());
  }

  onChange(listener: (board: LinkedInBoard) => void): void {
    this.listeners.push(listener);
  }

  async refresh(): Promise<void> {
    try {
      this.board = await fetchLinkedIn();
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
      window.dispatchEvent(new Event(LINKEDIN_CHANGED));
    } catch (error) {
      this.showError(error instanceof Error ? error.message : String(error));
    }
  }

  private showError(message: string | null): void {
    this.error.hidden = message === null;
    this.error.textContent = message ?? '';
  }

  private render(): void {
    this.list.replaceChildren();
    if (!this.board.sections.length) {
      const empty = el('div', 'profile-empty');
      empty.append(el('p', '', 'No rewrites yet. Paste your current headline or About section to Leo and he will put his rewrite here.'));
      empty.append(button('Start with Leo', () => this.askLeo('Here is my current headline: ', false), 'card-button primary'));
      this.list.append(empty);
      return;
    }
    this.list.append(...this.board.sections.map((section) => this.renderSection(section)));
  }

  private renderSection(section: LinkedInSection): HTMLElement {
    const name = SECTION_NAMES[section.section] ?? section.section;
    const title = section.label ? `${name}: ${section.label}` : name;
    const limit = this.board.limits[section.section];
    const card = el('article', `card status-${section.status === 'applied' ? 'posted' : 'draft'}`);

    const head = el('div', 'card-head');
    head.append(el('h3', '', title), el('span', 'card-id', `v${section.version}${section.status === 'applied' ? ' · applied' : ''}`));
    card.append(head);

    const compare = el('div', 'compare');
    const before = el('div', 'compare-col');
    before.append(el('h4', '', 'Now'), el('div', 'post-body muted', section.original || '(empty: nothing on the profile yet)'));
    const after = el('div', 'compare-col');
    const rewriteBody = el('div', 'post-body', section.rewrite);
    after.append(el('h4', '', 'Leo’s rewrite'), rewriteBody);
    compare.append(before, after);
    card.append(compare);

    const chars = section.rewrite.length;
    card.append(el('p', `char-count ${limit && chars > limit ? 'off' : 'ok'}`, `${chars} / ${limit} characters`));
    card.append(el('p', 'card-note', section.rationale));

    if (section.keywords.length) {
      const keywords = el('div', 'keyword-list');
      keywords.append(...section.keywords.map((keyword) => el('span', 'gap-tag', keyword)));
      card.append(keywords);
    }
    card.append(el('p', 'card-meta', `Based on: ${section.sources.join(' · ')}`));

    const actions = el('div', 'card-actions');
    actions.append(
      copyButton(() => section.rewrite, (message) => this.showError(message)),
      button('Edit', () => this.editInPlace(card, rewriteBody, section)),
      button('Revise with Leo', () => this.askLeo(`Revise the ${title} rewrite: `, false)),
      button(section.status === 'applied' ? 'Mark not applied' : 'Mark applied', () =>
        void this.mutate(() => updateSection(section.id, { status: section.status === 'applied' ? 'proposed' : 'applied' })),
      ),
      button('Delete', () => void this.mutate(() => deleteSection(section.id)), 'card-button danger'),
    );
    card.append(actions);
    return card;
  }

  private editInPlace(card: HTMLElement, body: HTMLElement, section: LinkedInSection): void {
    const editor = el('textarea', 'post-editor');
    editor.value = section.rewrite;
    editor.rows = Math.min(20, section.rewrite.split('\n').length + 3);
    const bar = el('div', 'card-actions');
    bar.append(
      button('Save', () => void this.mutate(() => updateSection(section.id, { rewrite: editor.value })), 'card-button primary'),
      button('Cancel', () => this.render()),
    );
    body.replaceWith(editor);
    card.querySelector('.card-actions')?.replaceWith(bar);
    editor.focus();
  }
}
