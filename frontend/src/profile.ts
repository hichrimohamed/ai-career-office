import { addFact, deleteFact, editFact, fetchProfile, type Profile, PROFILE_CHANGED, type ProfileFact } from './api';

const SOURCE_NAMES: Record<string, string> = { user: 'you', content: 'Nora' };

/** Left-hand panel showing the shared Career Profile, editable in place. */
export class ProfilePanel {
  readonly root: HTMLElement;
  private readonly body: HTMLElement;
  private readonly gaps: HTMLElement;
  private readonly form: HTMLFormElement;
  private readonly categorySelect: HTMLSelectElement;
  private readonly error: HTMLElement;
  private readonly listeners: ((profile: Profile) => void)[] = [];

  constructor() {
    this.root = document.createElement('aside');
    this.root.className = 'side-panel profile-panel';
    this.root.hidden = true;
    this.root.innerHTML = `
      <header>
        <div class="chat-title"><strong>Career Profile</strong><span>What every worker knows about you</span></div>
        <button type="button" class="chat-close" aria-label="Close profile">×</button>
      </header>
      <div class="profile-gaps"></div>
      <div class="profile-body"></div>
      <p class="panel-error" hidden></p>
      <form class="profile-form">
        <select aria-label="Category"></select>
        <input type="text" placeholder="Add a fact, e.g. Target: AI Engineer, Barcelona or remote" aria-label="New fact" />
        <button type="submit">Add</button>
      </form>`;
    document.body.appendChild(this.root);

    this.body = this.root.querySelector('.profile-body')!;
    this.gaps = this.root.querySelector('.profile-gaps')!;
    this.form = this.root.querySelector('.profile-form')!;
    this.categorySelect = this.root.querySelector('select')!;
    this.error = this.root.querySelector('.panel-error')!;

    this.root.querySelector('.chat-close')!.addEventListener('click', () => (this.root.hidden = true));
    this.form.addEventListener('submit', (event) => {
      event.preventDefault();
      const input = this.form.querySelector('input')!;
      const text = input.value.trim();
      if (!text) return;
      void this.mutate(async () => {
        await addFact(this.categorySelect.value, text);
        input.value = '';
      });
    });
    window.addEventListener(PROFILE_CHANGED, () => void this.refresh());
  }

  onChange(listener: (profile: Profile) => void): void {
    this.listeners.push(listener);
  }

  async refresh(): Promise<void> {
    try {
      const profile = await fetchProfile();
      this.render(profile);
      this.listeners.forEach((listener) => listener(profile));
    } catch (error) {
      this.showError(String(error));
    }
  }

  private async mutate(action: () => Promise<unknown>): Promise<void> {
    this.showError(null);
    try {
      await action();
      window.dispatchEvent(new Event(PROFILE_CHANGED));
    } catch (error) {
      this.showError(error instanceof Error ? error.message : String(error));
    }
  }

  private showError(message: string | null): void {
    this.error.hidden = message === null;
    this.error.textContent = message ?? '';
  }

  private render(profile: Profile): void {
    if (this.categorySelect.options.length === 0) {
      for (const category of profile.categories) this.categorySelect.add(new Option(category, category));
    }

    this.gaps.replaceChildren();
    if (profile.gaps.length) {
      this.gaps.append('Missing: ');
      for (const gap of profile.gaps) {
        const tag = document.createElement('span');
        tag.className = 'gap-tag';
        tag.textContent = gap;
        this.gaps.append(tag);
      }
    }

    this.body.replaceChildren();
    if (profile.facts.length === 0) {
      const empty = document.createElement('p');
      empty.className = 'profile-empty';
      empty.textContent = 'Nothing saved yet. Ask Nora to interview you, or add facts below.';
      this.body.append(empty);
      return;
    }
    for (const category of profile.categories) {
      const facts = profile.facts.filter((fact) => fact.category === category);
      if (!facts.length) continue;
      const section = document.createElement('section');
      const heading = document.createElement('h3');
      heading.textContent = category;
      section.append(heading, ...facts.map((fact) => this.renderFact(fact)));
      this.body.append(section);
    }
  }

  private renderFact(fact: ProfileFact): HTMLElement {
    const row = document.createElement('div');
    row.className = 'fact';
    const text = document.createElement('p');
    text.textContent = fact.fact;
    text.contentEditable = 'plaintext-only';
    text.spellcheck = true;
    text.title = 'Click to edit';
    text.addEventListener('keydown', (event) => {
      if (event.key === 'Enter') {
        event.preventDefault();
        text.blur();
      } else if (event.key === 'Escape') {
        text.textContent = fact.fact;
        text.blur();
      }
    });
    text.addEventListener('blur', () => {
      const value = text.textContent?.trim() ?? '';
      if (value && value !== fact.fact) void this.mutate(() => editFact(fact.id, value));
      else text.textContent = fact.fact;
    });

    const meta = document.createElement('span');
    meta.className = 'fact-meta';
    meta.textContent = `by ${SOURCE_NAMES[fact.source] ?? fact.source}`;

    const remove = document.createElement('button');
    remove.type = 'button';
    remove.className = 'fact-delete';
    remove.setAttribute('aria-label', `Delete: ${fact.fact}`);
    remove.textContent = '×';
    remove.addEventListener('click', () => void this.mutate(() => deleteFact(fact.id)));

    row.append(text, meta, remove);
    return row;
  }
}
