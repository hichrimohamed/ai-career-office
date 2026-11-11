import DOMPurify from 'dompurify';
import { marked } from 'marked';
import {
  type AgentInfo,
  COACHING_CHANGED,
  DRAFTS_CHANGED,
  fetchMessages,
  JOBS_CHANGED,
  LINKEDIN_CHANGED,
  PROFILE_CHANGED,
  streamChat,
} from './api';
import type { Worker } from './worker';

const TOOL_LABELS: Record<string, string> = {
  list_recent_projects: 'Scanning your projects…',
  list_project_files: 'Looking through project files…',
  read_project_file: 'Reading a project file…',
  project_git_log: 'Checking commit history…',
  WebSearch: 'Searching the web…',
  WebFetch: 'Reading a web page…',
  save_profile_fact: 'Saving to your profile…',
  update_profile_fact: 'Updating your profile…',
  get_profile: 'Checking your profile…',
  save_ideas: 'Pinning ideas to the Drafts board…',
  save_draft: 'Saving the draft to the board…',
  update_draft: 'Updating the draft…',
  list_drafts: 'Checking the Drafts board…',
  save_section_rewrite: 'Saving the rewrite to the LinkedIn board…',
  list_section_rewrites: 'Checking the LinkedIn board…',
  save_job: 'Pinning a job to the Jobs board…',
  save_outreach: 'Saving an outreach note…',
  list_jobs: 'Checking the Jobs board…',
  start_mock_interview: 'Setting up the interview…',
  record_answer: 'Scoring your answer…',
  finish_mock_interview: 'Writing up the interview…',
  save_skill_gap: 'Updating your skill gaps…',
  suggest_project: 'Planning a portfolio project…',
  list_coaching: 'Checking your coaching history…',
};

// Which board to refresh after a worker used one of these tools.
const BOARD_EVENTS: [RegExp, string][] = [
  [/(save|update)_profile_fact$/, PROFILE_CHANGED],
  [/(save_ideas|save_draft|update_draft)$/, DRAFTS_CHANGED],
  [/save_section_rewrite$/, LINKEDIN_CHANGED],
  [/(save_job|save_outreach)$/, JOBS_CHANGED],
  [/(start_mock_interview|record_answer|finish_mock_interview|save_skill_gap|suggest_project)$/, COACHING_CHANGED],
];

function toolLabel(name: string): string {
  return TOOL_LABELS[name.replace(/^mcp__\w+__/, '')] ?? 'Working…';
}

function renderMarkdown(text: string): string {
  return DOMPurify.sanitize(marked.parse(text, { async: false }));
}

/** One worker's conversation. It lives on while the panel shows someone else, so a reply can finish in the background. */
interface Conversation {
  agent: AgentInfo;
  worker: Worker;
  log: HTMLElement;
  status: string | null;
  busy: boolean;
  /** Unsent text in the box, kept while you talk to another worker. */
  draft: string;
}

/** Side panel for talking to one worker at a time. Workers keep working when you close it or switch to another one. */
export class ChatPanel {
  private readonly root: HTMLElement;
  private readonly title: HTMLElement;
  private log: HTMLElement;
  private readonly form: HTMLFormElement;
  private readonly input: HTMLTextAreaElement;
  private readonly sendButton: HTMLButtonElement;
  private readonly status: HTMLElement;
  private readonly actions: HTMLElement;
  private readonly conversations = new Map<string, Conversation>();
  private current: Conversation | null = null;
  private readonly closeListeners: (() => void)[] = [];

  constructor() {
    this.root = document.createElement('aside');
    this.root.className = 'chat-panel';
    this.root.hidden = true;
    this.root.innerHTML = `
      <header>
        <div class="chat-title"></div>
        <button type="button" class="chat-close" aria-label="Close chat">×</button>
      </header>
      <div class="chat-log"></div>
      <div class="chat-status" hidden></div>
      <div class="chat-actions"></div>
      <form class="chat-form">
        <textarea rows="2" placeholder="Ask something… (Enter to send, Shift+Enter for a new line)"></textarea>
        <button type="submit">Send</button>
      </form>`;
    document.body.appendChild(this.root);

    this.title = this.root.querySelector('.chat-title')!;
    this.log = this.root.querySelector('.chat-log')!;
    this.form = this.root.querySelector('.chat-form')!;
    this.input = this.root.querySelector('textarea')!;
    this.sendButton = this.root.querySelector('button[type="submit"]')!;
    this.status = this.root.querySelector('.chat-status')!;
    this.actions = this.root.querySelector('.chat-actions')!;

    this.root.querySelector('.chat-close')!.addEventListener('click', () => this.close());
    this.form.addEventListener('submit', (event) => {
      event.preventDefault();
      void this.send();
    });
    this.input.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        void this.send();
      }
    });
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && !this.root.hidden) this.close();
    });
  }

  /** Width (px) the open panel covers on the right of the screen, 0 when closed. */
  get coveredWidth(): number {
    if (this.root.hidden) return 0;
    return window.innerWidth - this.root.getBoundingClientRect().left;
  }

  onClose(listener: () => void): void {
    this.closeListeners.push(listener);
  }

  async open(agent: AgentInfo, worker: Worker): Promise<void> {
    if (this.current) this.current.draft = this.input.value;
    let conversation = this.conversations.get(agent.id);
    const isNew = !conversation;
    if (!conversation) {
      const log = document.createElement('div');
      log.className = 'chat-log';
      log.setAttribute('aria-live', 'polite');
      conversation = { agent, worker, log, status: null, busy: false, draft: '' };
      this.conversations.set(agent.id, conversation);
    }
    this.current = conversation;
    worker.hasNews = false;
    this.root.hidden = false;

    this.title.innerHTML = '<strong></strong><span></span>';
    this.title.querySelector('strong')!.textContent = agent.name;
    this.title.querySelector('span')!.textContent = agent.role;
    this.actions.replaceChildren(
      ...agent.quick_actions.map(({ label, prompt, send = true }) => {
        const chip = document.createElement('button');
        chip.type = 'button';
        chip.className = 'chip';
        chip.textContent = label;
        chip.addEventListener('click', () => this.ask(prompt, send));
        return chip;
      }),
    );
    this.log.replaceWith(conversation.log);
    this.log = conversation.log;
    this.input.value = conversation.draft;
    this.render(conversation);

    if (isNew) {
      try {
        for (const message of await fetchMessages(agent.id)) this.addBubble(conversation, message.role, message.content);
      } catch (error) {
        this.addBubble(conversation, 'error', String(error));
      }
    }
    this.log.scrollTop = this.log.scrollHeight;
    if (!conversation.busy) this.input.focus();
  }

  /** Put a message in the box (to finish typing) or send it straight away. */
  ask(message: string, sendNow: boolean): void {
    if (!this.current || this.current.busy) return;
    if (sendNow) {
      void this.send(message);
      return;
    }
    this.input.value = message;
    this.input.focus();
    this.input.setSelectionRange(message.length, message.length);
  }

  close(): void {
    if (this.root.hidden) return;
    if (this.current) this.current.draft = this.input.value;
    this.root.hidden = true;
    this.current = null;
    this.closeListeners.forEach((listener) => listener());
  }

  private isShowing(conversation: Conversation): boolean {
    return !this.root.hidden && this.current === conversation;
  }

  private addBubble(conversation: Conversation, role: 'user' | 'assistant' | 'error', content: string): HTMLElement {
    const bubble = document.createElement('div');
    bubble.className = `bubble ${role}`;
    if (role === 'assistant') bubble.innerHTML = renderMarkdown(content);
    else bubble.textContent = content;
    conversation.log.appendChild(bubble);
    conversation.log.scrollTop = conversation.log.scrollHeight;
    return bubble;
  }

  /** Show the conversation's busy state and status line, if it's the one on screen. */
  private render(conversation: Conversation): void {
    if (this.current !== conversation) return;
    this.sendButton.disabled = conversation.busy;
    this.input.disabled = conversation.busy;
    this.actions.querySelectorAll('button').forEach((chip) => (chip.disabled = conversation.busy));
    this.status.hidden = conversation.status === null;
    this.status.textContent = conversation.status ?? '';
  }

  private setBusy(conversation: Conversation, busy: boolean): void {
    conversation.busy = busy;
    this.render(conversation);
  }

  private setStatus(conversation: Conversation, text: string | null): void {
    conversation.status = text;
    conversation.worker.activity = text;
    this.render(conversation);
  }

  private async send(preset?: string): Promise<void> {
    const conversation = this.current;
    const text = (preset ?? this.input.value).trim();
    if (!text || !conversation || conversation.busy) return;
    const { agent, worker } = conversation;

    if (!preset) this.input.value = '';
    this.addBubble(conversation, 'user', text);
    const reply = this.addBubble(conversation, 'assistant', '');
    reply.classList.add('pending');
    this.setBusy(conversation, true);
    worker.state = 'thinking';

    let content = '';
    const changedBoards = new Set<string>();
    try {
      for await (const event of streamChat(agent.id, text)) {
        if (event.type === 'text') {
          worker.state = 'typing';
          this.setStatus(conversation, null);
          content += event.text;
          reply.innerHTML = renderMarkdown(content);
          conversation.log.scrollTop = conversation.log.scrollHeight;
        } else if (event.type === 'tool') {
          worker.state = 'thinking';
          this.setStatus(conversation, toolLabel(event.name));
          for (const [pattern, boardEvent] of BOARD_EVENTS) {
            if (pattern.test(event.name)) changedBoards.add(boardEvent);
          }
        } else if (event.type === 'error') {
          this.addBubble(conversation, 'error', event.message);
        }
      }
    } catch (error) {
      this.addBubble(conversation, 'error', String(error));
    } finally {
      this.setStatus(conversation, null);
      changedBoards.forEach((boardEvent) => window.dispatchEvent(new Event(boardEvent)));
      reply.classList.remove('pending');
      if (!content) reply.remove();
      worker.state = 'idle';
      if (!this.isShowing(conversation)) worker.hasNews = true;
      this.setBusy(conversation, false);
      if (this.isShowing(conversation)) this.input.focus();
    }
  }
}
