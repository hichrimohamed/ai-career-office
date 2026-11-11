import { fetchStandup, type Standup } from './api';
import { button, el } from './ui';

/** Left-hand panel for the Morning standup: one line per worker and the next step they suggest. */
export class StandupPanel {
  readonly root: HTMLElement;
  private readonly subtitle: HTMLElement;
  private readonly list: HTMLElement;
  private readonly rerunButton: HTMLButtonElement;
  private readonly error: HTMLElement;
  private readonly ask: (agentId: string, prompt: string) => void;
  private readonly listeners: ((standup: Standup | null) => void)[] = [];
  private loading = false;

  /** `ask(agentId, prompt)` opens that worker's chat and sends the prompt. */
  constructor(ask: (agentId: string, prompt: string) => void) {
    this.ask = ask;
    this.root = document.createElement('aside');
    this.root.className = 'side-panel standup-panel';
    this.root.hidden = true;
    this.root.innerHTML = `
      <header>
        <div class="chat-title"><strong>Morning standup</strong><span></span></div>
        <button type="button" class="chat-close" aria-label="Close standup">×</button>
      </header>
      <div class="drafts-list standup-list"></div>
      <p class="panel-error" hidden></p>
      <footer class="standup-footer"></footer>`;
    document.body.appendChild(this.root);

    this.subtitle = this.root.querySelector('.chat-title span')!;
    this.list = this.root.querySelector('.standup-list')!;
    this.error = this.root.querySelector('.panel-error')!;
    this.rerunButton = button('Run it again', () => void this.load(true));
    this.root.querySelector('.standup-footer')!.appendChild(this.rerunButton);

    this.root.querySelector('.chat-close')!.addEventListener('click', () => {
      this.root.hidden = true;
      this.emit(null);
    });
  }

  /** Called with the standup when it's shown, and with null when the panel closes. */
  onChange(listener: (standup: Standup | null) => void): void {
    this.listeners.push(listener);
  }

  /** Called by the shared left-panel toggle when it opens this panel. */
  async refresh(): Promise<void> {
    await this.load(false);
  }

  /** The panel was hidden from outside (another left panel opened). */
  hidden(): void {
    this.emit(null);
  }

  private emit(standup: Standup | null): void {
    this.listeners.forEach((listener) => listener(standup));
  }

  private async load(rerun: boolean): Promise<void> {
    if (this.loading) return;
    this.loading = true;
    this.rerunButton.disabled = true;
    this.error.hidden = true;
    this.subtitle.textContent = 'The team is getting ready…';
    if (rerun || !this.list.childElementCount) this.list.replaceChildren(el('p', 'card-meta', 'Collecting updates from every desk…'));
    try {
      const standup = await fetchStandup(rerun);
      this.render(standup);
      if (!this.root.hidden) this.emit(standup);
    } catch (error) {
      this.list.replaceChildren();
      this.error.hidden = false;
      this.error.textContent = error instanceof Error ? error.message : String(error);
      this.subtitle.textContent = '';
    } finally {
      this.loading = false;
      this.rerunButton.disabled = false;
    }
  }

  private render(standup: Standup): void {
    const time = new Date(`${standup.created_at.replace(' ', 'T')}Z`);
    this.subtitle.textContent = `Today at ${time.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
    this.list.replaceChildren(
      ...standup.updates.map((update) => {
        const card = el('article', 'card standup-card');
        card.append(el('h3', '', update.name), el('p', 'standup-line', update.line));
        const facts = el('details', 'standup-facts');
        facts.append(el('summary', '', 'Based on'), el('p', 'card-meta', update.facts.join(' · ')));
        card.append(facts, button(update.next.label, () => this.ask(update.agent_id, update.next.prompt), 'card-button primary'));
        return card;
      }),
    );
  }
}
