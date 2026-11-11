import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

BACKEND_DIR = Path(__file__).resolve().parents[2]

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS profile_facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    fact TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'user',
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS ideas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    hook TEXT NOT NULL,
    angle TEXT NOT NULL,
    why TEXT NOT NULL,
    pillar TEXT NOT NULL,
    proof_missing TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'new',
    source TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    idea_id INTEGER REFERENCES ideas(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    pillar TEXT NOT NULL,
    format TEXT NOT NULL,
    body TEXT NOT NULL,
    asset_needed TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'draft',
    version INTEGER NOT NULL DEFAULT 1,
    change_note TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS draft_revisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    draft_id INTEGER NOT NULL REFERENCES drafts(id) ON DELETE CASCADE,
    version INTEGER NOT NULL,
    body TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS linkedin_sections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    section TEXT NOT NULL,
    label TEXT NOT NULL DEFAULT '',
    original TEXT NOT NULL DEFAULT '',
    rewrite TEXT NOT NULL,
    rationale TEXT NOT NULL DEFAULT '',
    keywords TEXT NOT NULL DEFAULT '[]',
    sources TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'proposed',
    version INTEGER NOT NULL DEFAULT 1,
    previous_rewrite TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (section, label)
);
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    company TEXT NOT NULL,
    url TEXT NOT NULL DEFAULT '',
    location TEXT NOT NULL DEFAULT '',
    work_mode TEXT NOT NULL DEFAULT 'unknown',
    posted TEXT NOT NULL DEFAULT 'unknown',
    origin TEXT NOT NULL DEFAULT 'search',
    summary TEXT NOT NULL DEFAULT '',
    fit_score INTEGER,
    matched TEXT NOT NULL DEFAULT '[]',
    gaps TEXT NOT NULL DEFAULT '[]',
    notes TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'saved',
    source TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS outreach (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER REFERENCES jobs(id) ON DELETE SET NULL,
    target TEXT NOT NULL,
    how_to_find TEXT NOT NULL DEFAULT '',
    message TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    source TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS interview_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic TEXT NOT NULL,
    level TEXT NOT NULL,
    planned_questions INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'in_progress',
    summary TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL,
    started_at TEXT NOT NULL DEFAULT (datetime('now')),
    finished_at TEXT
);
CREATE TABLE IF NOT EXISTS interview_answers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES interview_sessions(id) ON DELETE CASCADE,
    area TEXT NOT NULL,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    score INTEGER NOT NULL,
    feedback TEXT NOT NULL,
    strong_answer TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS skill_gaps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    skill TEXT NOT NULL UNIQUE COLLATE NOCASE,
    severity TEXT NOT NULL,
    evidence TEXT NOT NULL,
    next_step TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'open',
    source TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS portfolio_projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    pitch TEXT NOT NULL,
    closes_gaps TEXT NOT NULL DEFAULT '[]',
    stack TEXT NOT NULL DEFAULT '[]',
    steps TEXT NOT NULL DEFAULT '[]',
    effort TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'idea',
    source TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS sessions (
    agent_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS standups (
    day TEXT PRIMARY KEY,
    updates TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def db_path() -> Path:
    return Path(os.environ.get("DB_PATH", BACKEND_DIR / "office.db"))


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        conn.executescript(SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def add_message(agent_id: str, role: str, content: str) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO messages (agent_id, role, content) VALUES (?, ?, ?)",
            (agent_id, role, content),
        )


def list_messages(agent_id: str) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT role, content, created_at FROM messages WHERE agent_id = ? ORDER BY id",
            (agent_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_session(agent_id: str) -> str | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT session_id FROM sessions WHERE agent_id = ?", (agent_id,)
        ).fetchone()
    return row["session_id"] if row else None


def set_session(agent_id: str, session_id: str) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO sessions (agent_id, session_id) VALUES (?, ?) "
            "ON CONFLICT(agent_id) DO UPDATE SET session_id = excluded.session_id",
            (agent_id, session_id),
        )


PROFILE_CATEGORIES = ["background", "skills", "projects", "goals", "location", "voice", "preferences"]
# Without these the agents can't write or advise well, so they ask about them first.
CORE_CATEGORIES = ["background", "skills", "projects", "goals", "location", "voice"]


def list_facts() -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, category, fact, source, updated_at FROM profile_facts ORDER BY category, id"
        ).fetchall()
    return [dict(row) for row in rows]


def get_fact(fact_id: int) -> dict | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT id, category, fact, source, updated_at FROM profile_facts WHERE id = ?", (fact_id,)
        ).fetchone()
    return dict(row) if row else None


def add_fact(category: str, fact: str, source: str) -> dict:
    with connect() as conn:
        cursor = conn.execute(
            "INSERT INTO profile_facts (category, fact, source) VALUES (?, ?, ?)", (category, fact, source)
        )
        fact_id = cursor.lastrowid
    return get_fact(fact_id)


def update_fact(fact_id: int, fact: str | None = None, category: str | None = None) -> dict | None:
    with connect() as conn:
        conn.execute(
            "UPDATE profile_facts SET fact = COALESCE(?, fact), category = COALESCE(?, category), "
            "updated_at = datetime('now') WHERE id = ?",
            (fact, category, fact_id),
        )
    return get_fact(fact_id)


def delete_fact(fact_id: int) -> bool:
    with connect() as conn:
        return conn.execute("DELETE FROM profile_facts WHERE id = ?", (fact_id,)).rowcount > 0


def profile_gaps(facts: list[dict]) -> list[str]:
    covered = {f["category"] for f in facts}
    return [c for c in CORE_CATEGORIES if c not in covered]


PILLARS = [
    "build-in-public", "engineering-decision", "lesson", "career-transition",
    "business-automation", "trend-opinion",
]
FORMATS = ["text", "carousel", "video", "retro"]
DRAFT_STATUSES = ["draft", "ready", "posted"]
IDEA_STATUSES = ["new", "drafted", "dismissed"]

IDEA_COLUMNS = "id, title, hook, angle, why, pillar, proof_missing, status, source, created_at"
DRAFT_COLUMNS = (
    "id, idea_id, title, pillar, format, body, asset_needed, status, version, change_note, "
    "source, created_at, updated_at"
)


def list_ideas() -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            f"SELECT {IDEA_COLUMNS} FROM ideas WHERE status != 'dismissed' ORDER BY id DESC"
        ).fetchall()
    return [dict(row) for row in rows]


def get_idea(idea_id: int) -> dict | None:
    with connect() as conn:
        row = conn.execute(f"SELECT {IDEA_COLUMNS} FROM ideas WHERE id = ?", (idea_id,)).fetchone()
    return dict(row) if row else None


def add_idea(idea: dict, source: str) -> dict:
    with connect() as conn:
        cursor = conn.execute(
            "INSERT INTO ideas (title, hook, angle, why, pillar, proof_missing, source) "
            "VALUES (:title, :hook, :angle, :why, :pillar, :proof_missing, :source)",
            {**idea, "source": source},
        )
        idea_id = cursor.lastrowid
    return get_idea(idea_id)


def set_idea_status(idea_id: int, status: str) -> dict | None:
    with connect() as conn:
        conn.execute("UPDATE ideas SET status = ? WHERE id = ?", (status, idea_id))
    return get_idea(idea_id)


def list_drafts() -> list[dict]:
    with connect() as conn:
        rows = conn.execute(f"SELECT {DRAFT_COLUMNS} FROM drafts ORDER BY updated_at DESC, id DESC").fetchall()
    return [dict(row) for row in rows]


def get_draft(draft_id: int) -> dict | None:
    with connect() as conn:
        row = conn.execute(f"SELECT {DRAFT_COLUMNS} FROM drafts WHERE id = ?", (draft_id,)).fetchone()
    return dict(row) if row else None


def add_draft(draft: dict, source: str) -> dict:
    with connect() as conn:
        cursor = conn.execute(
            "INSERT INTO drafts (idea_id, title, pillar, format, body, asset_needed, source) "
            "VALUES (:idea_id, :title, :pillar, :format, :body, :asset_needed, :source)",
            {**draft, "source": source},
        )
        draft_id = cursor.lastrowid
        if draft.get("idea_id"):
            conn.execute("UPDATE ideas SET status = 'drafted' WHERE id = ?", (draft["idea_id"],))
    return get_draft(draft_id)


def revise_draft(draft_id: int, body: str, change_note: str) -> dict | None:
    """Replace the body, keeping the previous version in draft_revisions."""
    with connect() as conn:
        current = conn.execute("SELECT body, version FROM drafts WHERE id = ?", (draft_id,)).fetchone()
        if current is None:
            return None
        if body != current["body"]:
            conn.execute(
                "INSERT INTO draft_revisions (draft_id, version, body) VALUES (?, ?, ?)",
                (draft_id, current["version"], current["body"]),
            )
            conn.execute(
                "UPDATE drafts SET body = ?, version = version + 1, change_note = ?, "
                "updated_at = datetime('now') WHERE id = ?",
                (body, change_note, draft_id),
            )
    return get_draft(draft_id)


def set_draft_status(draft_id: int, status: str) -> dict | None:
    with connect() as conn:
        conn.execute(
            "UPDATE drafts SET status = ?, updated_at = datetime('now') WHERE id = ?", (status, draft_id)
        )
    return get_draft(draft_id)


def delete_draft(draft_id: int) -> bool:
    with connect() as conn:
        return conn.execute("DELETE FROM drafts WHERE id = ?", (draft_id,)).rowcount > 0


# LinkedIn's own character limits per section ("skills" is a comma-separated list we keep short).
LINKEDIN_SECTIONS = {"headline": 220, "about": 2600, "experience": 2000, "skills": 1000, "featured": 1000}
SECTION_STATUSES = ["proposed", "applied"]
SECTION_COLUMNS = (
    "id, section, label, original, rewrite, rationale, keywords, sources, status, version, "
    "previous_rewrite, source, updated_at"
)


def _section_row(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    data = dict(row)
    data["keywords"] = json.loads(data["keywords"])
    data["sources"] = json.loads(data["sources"])
    return data


def list_sections() -> list[dict]:
    order = " ".join(f"WHEN '{name}' THEN {i}" for i, name in enumerate(LINKEDIN_SECTIONS))
    with connect() as conn:
        rows = conn.execute(
            f"SELECT {SECTION_COLUMNS} FROM linkedin_sections ORDER BY CASE section {order} END, label"
        ).fetchall()
    return [_section_row(row) for row in rows]


def get_section(section_id: int) -> dict | None:
    with connect() as conn:
        row = conn.execute(f"SELECT {SECTION_COLUMNS} FROM linkedin_sections WHERE id = ?", (section_id,)).fetchone()
    return _section_row(row)


def save_section(data: dict, source: str) -> dict:
    """Insert or replace the rewrite for (section, label). A new rewrite bumps the version and goes back to 'proposed'."""
    params = {**data, "keywords": json.dumps(data["keywords"]), "sources": json.dumps(data["sources"]), "source": source}
    with connect() as conn:
        existing = conn.execute(
            "SELECT id, original, rewrite FROM linkedin_sections WHERE section = :section AND label = :label", params
        ).fetchone()
        if existing is None:
            section_id = conn.execute(
                "INSERT INTO linkedin_sections (section, label, original, rewrite, rationale, keywords, sources, source) "
                "VALUES (:section, :label, :original, :rewrite, :rationale, :keywords, :sources, :source)",
                params,
            ).lastrowid
        else:
            section_id = existing["id"]
            conn.execute(
                "UPDATE linkedin_sections SET original = :original, rewrite = :rewrite, rationale = :rationale, "
                "keywords = :keywords, sources = :sources, source = :source, status = 'proposed', "
                "previous_rewrite = :previous, version = version + 1, updated_at = datetime('now') WHERE id = :id",
                {**params, "original": params["original"] or existing["original"],
                 "previous": existing["rewrite"], "id": section_id},
            )
    return get_section(section_id)


def update_section(section_id: int, rewrite: str | None = None, status: str | None = None) -> dict | None:
    with connect() as conn:
        if rewrite is not None:
            conn.execute(
                "UPDATE linkedin_sections SET previous_rewrite = rewrite, rewrite = ?, version = version + 1, "
                "updated_at = datetime('now') WHERE id = ? AND rewrite != ?",
                (rewrite, section_id, rewrite),
            )
        if status is not None:
            conn.execute(
                "UPDATE linkedin_sections SET status = ?, updated_at = datetime('now') WHERE id = ?", (status, section_id)
            )
    return get_section(section_id)


def delete_section(section_id: int) -> bool:
    with connect() as conn:
        return conn.execute("DELETE FROM linkedin_sections WHERE id = ?", (section_id,)).rowcount > 0


JOB_STATUSES = ["saved", "applying", "applied", "interview", "offer", "rejected", "archived"]
WORK_MODES = ["remote", "hybrid", "onsite", "unknown"]
JOB_ORIGINS = ["search", "pasted"]
OUTREACH_STATUSES = ["draft", "sent", "replied"]
OUTREACH_MAX_CHARS = 300  # LinkedIn's limit for a connection request note
JOB_COLUMNS = (
    "id, title, company, url, location, work_mode, posted, origin, summary, fit_score, matched, gaps, notes, "
    "status, source, created_at, updated_at"
)
OUTREACH_COLUMNS = "id, job_id, target, how_to_find, message, status, source, created_at"


def _job_row(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    data = dict(row)
    data["matched"] = json.loads(data["matched"])
    data["gaps"] = json.loads(data["gaps"])
    return data


def list_jobs() -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            f"SELECT {JOB_COLUMNS} FROM jobs WHERE status != 'archived' "
            "ORDER BY fit_score IS NULL, fit_score DESC, id DESC"
        ).fetchall()
    return [_job_row(row) for row in rows]


def get_job(job_id: int) -> dict | None:
    with connect() as conn:
        return _job_row(conn.execute(f"SELECT {JOB_COLUMNS} FROM jobs WHERE id = ?", (job_id,)).fetchone())


def save_job(job: dict, source: str) -> dict:
    """Insert, or update the same posting (same URL, or same company and title when there is no URL)."""
    params = {**job, "matched": json.dumps(job["matched"]), "gaps": json.dumps(job["gaps"]), "source": source}
    with connect() as conn:
        if job["url"]:
            existing = conn.execute("SELECT id FROM jobs WHERE url = :url", params).fetchone()
        else:
            existing = conn.execute(
                "SELECT id FROM jobs WHERE url = '' AND lower(company) = lower(:company) AND lower(title) = lower(:title)",
                params,
            ).fetchone()
        if existing is None:
            job_id = conn.execute(
                "INSERT INTO jobs (title, company, url, location, work_mode, posted, origin, summary, fit_score, "
                "matched, gaps, notes, source) VALUES (:title, :company, :url, :location, :work_mode, :posted, "
                ":origin, :summary, :fit_score, :matched, :gaps, :notes, :source)",
                params,
            ).lastrowid
        else:
            job_id = existing["id"]
            conn.execute(
                "UPDATE jobs SET title = :title, company = :company, location = :location, work_mode = :work_mode, "
                "posted = :posted, summary = :summary, fit_score = COALESCE(:fit_score, fit_score), "
                "matched = :matched, gaps = :gaps, notes = :notes, updated_at = datetime('now') WHERE id = :id",
                {**params, "id": job_id},
            )
    return get_job(job_id)


def update_job(job_id: int, status: str | None = None, notes: str | None = None) -> dict | None:
    with connect() as conn:
        conn.execute(
            "UPDATE jobs SET status = COALESCE(?, status), notes = COALESCE(?, notes), "
            "updated_at = datetime('now') WHERE id = ?",
            (status, notes, job_id),
        )
    return get_job(job_id)


def delete_job(job_id: int) -> bool:
    with connect() as conn:
        return conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,)).rowcount > 0


def list_outreach() -> list[dict]:
    with connect() as conn:
        rows = conn.execute(f"SELECT {OUTREACH_COLUMNS} FROM outreach ORDER BY id DESC").fetchall()
    return [dict(row) for row in rows]


def get_outreach(outreach_id: int) -> dict | None:
    with connect() as conn:
        row = conn.execute(f"SELECT {OUTREACH_COLUMNS} FROM outreach WHERE id = ?", (outreach_id,)).fetchone()
    return dict(row) if row else None


def add_outreach(item: dict, source: str) -> dict:
    with connect() as conn:
        outreach_id = conn.execute(
            "INSERT INTO outreach (job_id, target, how_to_find, message, source) "
            "VALUES (:job_id, :target, :how_to_find, :message, :source)",
            {**item, "source": source},
        ).lastrowid
    return get_outreach(outreach_id)


def update_outreach(outreach_id: int, message: str | None = None, status: str | None = None) -> dict | None:
    with connect() as conn:
        conn.execute(
            "UPDATE outreach SET message = COALESCE(?, message), status = COALESCE(?, status) WHERE id = ?",
            (message, status, outreach_id),
        )
    return get_outreach(outreach_id)


def delete_outreach(outreach_id: int) -> bool:
    with connect() as conn:
        return conn.execute("DELETE FROM outreach WHERE id = ?", (outreach_id,)).rowcount > 0


INTERVIEW_AREAS = ["llm-fundamentals", "rag", "evals", "agents", "system-design", "python", "behavioral", "other"]
GAP_SEVERITIES = ["high", "medium", "low"]
GAP_STATUSES = ["open", "working", "closed"]
PROJECT_STATUSES = ["idea", "building", "shipped"]


def _decode(row: sqlite3.Row | None, *json_fields: str) -> dict | None:
    if row is None:
        return None
    data = dict(row)
    for name in json_fields:
        data[name] = json.loads(data[name])
    return data


def start_interview(topic: str, level: str, planned_questions: int, source: str) -> dict:
    with connect() as conn:
        session_id = conn.execute(
            "INSERT INTO interview_sessions (topic, level, planned_questions, source) VALUES (?, ?, ?, ?)",
            (topic, level, planned_questions, source),
        ).lastrowid
    return get_interview(session_id)


def get_interview(session_id: int) -> dict | None:
    with connect() as conn:
        session = conn.execute("SELECT * FROM interview_sessions WHERE id = ?", (session_id,)).fetchone()
        if session is None:
            return None
        answers = conn.execute(
            "SELECT id, area, question, answer, score, feedback, strong_answer, created_at "
            "FROM interview_answers WHERE session_id = ? ORDER BY id",
            (session_id,),
        ).fetchall()
    data = dict(session)
    data["answers"] = [dict(a) for a in answers]
    scores = [a["score"] for a in answers]
    data["average_score"] = round(sum(scores) / len(scores), 1) if scores else None
    return data


def list_interviews() -> list[dict]:
    with connect() as conn:
        ids = [r["id"] for r in conn.execute("SELECT id FROM interview_sessions ORDER BY id DESC").fetchall()]
    return [get_interview(i) for i in ids]


def add_answer(session_id: int, answer: dict) -> dict:
    with connect() as conn:
        conn.execute(
            "INSERT INTO interview_answers (session_id, area, question, answer, score, feedback, strong_answer) "
            "VALUES (:session_id, :area, :question, :answer, :score, :feedback, :strong_answer)",
            {**answer, "session_id": session_id},
        )
    return get_interview(session_id)


def finish_interview(session_id: int, summary: str) -> dict | None:
    with connect() as conn:
        conn.execute(
            "UPDATE interview_sessions SET status = 'finished', summary = ?, finished_at = datetime('now') WHERE id = ?",
            (summary, session_id),
        )
    return get_interview(session_id)


def delete_interview(session_id: int) -> bool:
    with connect() as conn:
        return conn.execute("DELETE FROM interview_sessions WHERE id = ?", (session_id,)).rowcount > 0


def list_gaps() -> list[dict]:
    order = "CASE severity WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END"
    with connect() as conn:
        rows = conn.execute(f"SELECT * FROM skill_gaps ORDER BY status = 'closed', {order}, id").fetchall()
    return [dict(r) for r in rows]


def get_gap(gap_id: int) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM skill_gaps WHERE id = ?", (gap_id,)).fetchone()
    return dict(row) if row else None


def save_gap(gap: dict, source: str) -> dict:
    """Insert, or update the gap with the same skill name (case-insensitive). Re-saving reopens a closed gap."""
    with connect() as conn:
        conn.execute(
            "INSERT INTO skill_gaps (skill, severity, evidence, next_step, source) "
            "VALUES (:skill, :severity, :evidence, :next_step, :source) "
            "ON CONFLICT(skill) DO UPDATE SET severity = excluded.severity, evidence = excluded.evidence, "
            "next_step = excluded.next_step, source = excluded.source, "
            "status = CASE WHEN skill_gaps.status = 'closed' THEN 'open' ELSE skill_gaps.status END, "
            "updated_at = datetime('now')",
            {**gap, "source": source},
        )
        row = conn.execute("SELECT id FROM skill_gaps WHERE skill = ?", (gap["skill"],)).fetchone()
    return get_gap(row["id"])


def update_gap(gap_id: int, status: str) -> dict | None:
    with connect() as conn:
        conn.execute(
            "UPDATE skill_gaps SET status = ?, updated_at = datetime('now') WHERE id = ?", (status, gap_id)
        )
    return get_gap(gap_id)


def delete_gap(gap_id: int) -> bool:
    with connect() as conn:
        return conn.execute("DELETE FROM skill_gaps WHERE id = ?", (gap_id,)).rowcount > 0


def list_portfolio_projects() -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM portfolio_projects ORDER BY status = 'shipped', id DESC"
        ).fetchall()
    return [_decode(r, "closes_gaps", "stack", "steps") for r in rows]


def get_portfolio_project(project_id: int) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM portfolio_projects WHERE id = ?", (project_id,)).fetchone()
    return _decode(row, "closes_gaps", "stack", "steps")


def add_portfolio_project(project: dict, source: str) -> dict:
    params = {**project, "source": source}
    for name in ("closes_gaps", "stack", "steps"):
        params[name] = json.dumps(project[name])
    with connect() as conn:
        project_id = conn.execute(
            "INSERT INTO portfolio_projects (title, pitch, closes_gaps, stack, steps, effort, source) "
            "VALUES (:title, :pitch, :closes_gaps, :stack, :steps, :effort, :source)",
            params,
        ).lastrowid
    return get_portfolio_project(project_id)


def update_portfolio_project(project_id: int, status: str) -> dict | None:
    with connect() as conn:
        conn.execute("UPDATE portfolio_projects SET status = ? WHERE id = ?", (status, project_id))
    return get_portfolio_project(project_id)


def delete_portfolio_project(project_id: int) -> bool:
    with connect() as conn:
        return conn.execute("DELETE FROM portfolio_projects WHERE id = ?", (project_id,)).rowcount > 0


def get_standup(day: str) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT day, updates, created_at FROM standups WHERE day = ?", (day,)).fetchone()
    return _decode(row, "updates")


def save_standup(day: str, updates: list[dict]) -> dict:
    with connect() as conn:
        conn.execute(
            "INSERT INTO standups (day, updates) VALUES (?, ?) "
            "ON CONFLICT(day) DO UPDATE SET updates = excluded.updates, created_at = datetime('now')",
            (day, json.dumps(updates)),
        )
    return get_standup(day)
