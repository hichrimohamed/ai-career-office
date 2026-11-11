# Plan: "AI Career Office" — LinkedIn agents for landing an AI Engineer role

## Context
You want AI agents that help you on LinkedIn: find post ideas, ask you questions to learn your story, and move you toward an AI Engineer job. You picked:
- **Agents:** Content (post ideas + drafts), Profile Optimizer, Job & People Scout, Career Coach (interview prep)
- **UI:** a 3D office in **three.js** where each agent is a worker at a desk; you click a worker to talk to them
- **LinkedIn access:** none. You copy and paste text in and out, so there's no account risk.
- **Stack:** Python + **Claude Agent SDK** (`claude-agent-sdk`), running on your **Claude plan** through your Claude Code login. No API key, runs locally.

The project folder is empty, and there's no spec or existing code to reuse. The project also works as a portfolio piece for AI Engineer applications (agents, tool use, streaming, memory, evals).

## Architecture
```
frontend/ (Vite + TypeScript + three.js)          backend/ (Python, FastAPI)
  office scene: room, desks, 4 workers   <--SSE--   /agents/{id}/chat  (streamed)
  click worker -> chat panel (HTML overlay)          agents/ : one module per worker (system prompt + tools)
  worker state anim: idle / thinking / typing        core/llm.py : Agent SDK query(), in-process MCP tools, streaming
  boards: Drafts, Profile, Jobs (HTML panels)         core/store.py : SQLite (profile facts, chats, drafts, jobs)
```
- **Shared memory = "Career Profile":** facts about you (skills, projects, goals, location, voice samples). Every agent reads it, and any agent can add to it through a `save_profile_fact` tool. This is how the "ask me questions" part feeds every other agent.
- **LLM access:** `claude_agent_sdk.query()` with `ClaudeAgentOptions`. The SDK runs the local `claude` CLI and uses its login. Each agent's tools are `@tool` functions in an in-process MCP server (`create_sdk_mcp_server`). Built-in file and shell tools are turned off (`tools=[]`, `setting_sources=[]`), so the agents can only use the tools we give them. Tokens stream with `include_partial_messages=True`.
- **Models:** set as aliases in `.env`: `MODEL_DEFAULT=sonnet`, `MODEL_FAST=haiku`.
- **Plan limits:** usage counts against your Claude plan's limits, shared with your normal Claude use. Keep `max_turns` small. `ANTHROPIC_API_KEY` must stay unset, because if it's set the SDK bills the API instead.
- **Job search:** uses the SDK's built-in `WebSearch`/`WebFetch` tools, turned on only for the Scout, to find public AI Engineer job posts, with no LinkedIn scraping. You can also paste in a job description.
- **Workers:** built from simple three.js primitives (capsule body, sphere head, desk box), so they need no 3D assets. GLTF models can be added later.

## Dependency graph
```
T1 scaffold ─┬─> T2 first worker chat (vertical slice) ─> T3 Career Profile + interviewer
             └─> (scene)                                   │
                                     ┌─────────────┬───────┼──────────────┐
                                     T4 Content    T5 Profile Opt  T6 Job Scout  T7 Coach
                                     └─────────────┴───────┬──────────────┘
                                                           T8 office life (states, handoffs, standup)
                                                           T9 evals + README
```
T4 through T7 are independent of each other once T3 is done.

## Tasks (each one is a vertical slice: scene → API → agent → storage)

### Phase 1: Walking skeleton
**T1. Scaffold the backend and frontend**
- Backend: `backend/` with FastAPI, a `/health` endpoint, `.env` (model aliases, no key), `uv`/`pyproject.toml`, and pytest.
- Frontend: `frontend/` with Vite + TS + three.js, an office room (floor, walls, lights, OrbitControls) and 4 empty desks.
- Done when: `uvicorn` serves `/health` with a 200, `npm run dev` shows the room, and `pytest` passes.

**T2. First worker you can talk to (Content Strategist)**
- `core/llm.py`: wraps the Agent SDK `query()` and turns its stream events into SSE text deltas and tool events (the SDK handles the tool-use loop). `agents/content.py`: system prompt.
- `POST /agents/content/chat` streams tokens over SSE. Chats are saved in SQLite.
- Frontend: one worker at a desk. Clicking it opens a chat panel that streams the reply, and the worker plays a "typing" animation while it answers.
- Done when: you click the worker, ask for "3 post ideas about RAG", and the reply streams in. The chat is still there after a page reload.
- Verify with a pytest test that mocks `query()`, plus a manual browser check.

**Checkpoint A:** the whole path (3D click → API → Claude → stream → DB) works. Review the look and feel before adding more workers.

### Phase 2: Memory and questions
**T3. Career Profile + interviewer behavior**
- `profile_facts` table, and the tools `save_profile_fact`, `get_profile`. A Profile board in the UI where you can view and edit facts.
- The shared prompt rule: when the agent is missing information, it asks you one question at a time and saves your answer.
- Done when: a new user gets asked about background, skills, projects, target location and post tone, and the answers show up on the Profile board and in later agent prompts.

**Checkpoint B:** the profile is filled from a real interview with you.

### Phase 3: The four workers (in any order)
**T4. Content: ideas → interview → draft**
- Tools: `propose_ideas` (structured list with hook, angle, and why it helps an AI Engineer job search), `save_draft`.
- Flow: it suggests ideas, asks 2–3 questions about your real experience, then drafts the post in your voice. Drafts go to a Drafts whiteboard in the office with Copy and Revise buttons.
- Done when: a draft is saved, copyable, and uses facts from your profile.

**T5. Profile Optimizer**
- You paste your current headline, About section and experience. It returns rewrites targeting AI Engineer keywords, shown side by side with the original and a Copy button.
- Done when: the rewrites cite your profile facts and the output doesn't invent anything.

**T6. Job & People Scout**
- `WebSearch` finds recent AI Engineer posts (using the location from your profile). Pasting a job description gives you a fit score, matched skills and gaps.
- It suggests the kinds of people or roles to connect with and drafts outreach notes under 300 characters for you to copy. A Jobs board lists saved jobs with their status.
- Done when: a search returns real links, you can save a job, and you get a fit analysis for a pasted job description.

**T7. Career Coach**
- Mock interview mode covering LLM fundamentals, RAG, evals, agents and system design. It asks one question at a time and scores each answer with feedback.
- It tracks gaps in the DB and suggests portfolio projects to close them.
- Done when: a 5-question session gives you scores and a gap list that is saved.

**Checkpoint C:** all 4 workers work end to end. Use them for a week before Phase 4.

### Phase 4: Office life and quality
**T8. Living office**
- Workers show their state (idle, thinking, typing, "has something for you" bubble), and a camera fly-to moves to the worker you click.
- Handoffs: a gap found by the Coach can become a post idea for Content, and a job found by the Scout can trigger profile tips from the Optimizer.
- A "Morning standup" button has each worker give a one-line update.

**T9. Evals + README**
- `evals/`: a small set of cases per agent (for example, no invented facts and outreach under 300 characters), run with pytest, with Claude judging the answers through the Agent SDK on your plan.
- A README with screenshots or a GIF, for your portfolio.

## Verification
- Backend: `pytest` (mocked `query()` for unit tests, plus `evals/` run on demand with your plan).
- Frontend: `npm run build` with no type errors, and a manual check in Chrome at each checkpoint (click each worker, stream a reply, copy a draft).
- End to end: the interview fills your profile, Content drafts a post using those facts, the Scout finds a job, and the Coach runs a mock interview, all in one session.

## On approval
Write this plan to `tasks/plan.md` and the checklist (T1–T9 with acceptance criteria) to `tasks/todo.md` in the project folder, then start T1.
