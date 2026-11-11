# AI Career Office — Todo

## Phase 1: Walking skeleton
- [x] **T1 Scaffold** — FastAPI `/health`, `.env`, pyproject + pytest; Vite + TS + three.js office room with 4 desks
  - Accept: `/health` returns 200 · `npm run dev` shows the room · `pytest` passes
- [x] **T2 First worker (Content)** — `core/llm.py` on Claude Agent SDK (plan login, no API key), `POST /agents/content/chat` (SSE), SQLite chats, clickable worker + chat panel + typing animation
  - Accept: ask "3 post ideas about RAG" and the reply streams · chat survives a reload · pytest with mocked `query()` passes
  - Added: Nora's full persona prompt (`backend/app/agents/prompts/nora.md`), read-only project tools
    (`backend/app/tools/projects.py`, roots in `PROJECTS_ROOTS`), WebSearch/WebFetch, Weekly brief button, tool status line
- [ ] **Checkpoint A** — review the full path and the look and feel

## Phase 2: Memory and questions
- [x] **T3 Career Profile + interviewer** — `profile_facts` table, `save_profile_fact`/`get_profile` tools, Profile board, ask-one-question-at-a-time rule
  - Accept: interview answers appear on the Profile board and in later agent prompts
- [ ] **Checkpoint B** — profile filled from a real interview

## Phase 3: Workers (any order)
- [x] **T4 Content** — `propose_ideas`, `save_draft`, Drafts whiteboard with Copy/Revise
  - Accept: the saved draft uses profile facts and can be copied
- [x] **T5 Profile Optimizer** — paste headline/About/experience → AI-Engineer rewrites side by side
  - Accept: cites profile facts, invents nothing
- [x] **T6 Job & People Scout** — SDK `WebSearch` jobs, fit score for a pasted JD, outreach notes under 300 chars, Jobs board
  - Accept: real links · job saved · fit analysis
- [x] **T7 Career Coach** — mock interview, per-answer scores, gaps saved, project suggestions
  - Accept: a 5-question session ends with saved scores and gaps
- [ ] **Checkpoint C** — use all 4 workers for a week

## Phase 4: Office life and quality
- [ ] **T8 Living office** — state animations, camera fly-to, handoffs, Morning standup
  - [x] States on the name tag (live activity line, "Has something for you" badge when a reply lands while you're elsewhere)
  - [x] Camera fly-to on click (`frontend/src/camera.ts`), fly back on close / Esc; per-worker chats keep running in the background
  - [ ] Handoffs (Coach gap → Content idea, Scout job → Optimizer tips) — after Checkpoint C
  - [x] Morning standup — board facts per worker (`backend/app/core/standup.py`), voiced in one Haiku call, cached per day; panel + speech bubbles + one-click next step
- [ ] **T9 Evals + README** — LLM-judge evals per agent, README with GIF
