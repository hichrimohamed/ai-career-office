"""Read-only access to the user's project folders, for agents that write about his work.

Agents never get raw filesystem tools. They see projects only through these functions,
which stay inside the configured roots, skip secret-looking files and redact keys.
"""

import fnmatch
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

PROJECT_MARKERS = {
    ".git", "README.md", "package.json", "pyproject.toml", "requirements.txt", "pubspec.yaml",
    "Cargo.toml", "go.mod", "build.gradle", "build.gradle.kts", "Package.swift", "CLAUDE.md",
}
IGNORED_DIRS = {
    ".git", "node_modules", ".venv", "venv", "__pycache__", "build", "dist", ".next", "target",
    "Pods", ".dart_tool", ".gradle", ".idea", ".vscode", "DerivedData", ".pytest_cache", "coverage",
}
SECRET_PATTERNS = [
    ".env", ".env.*", "*.pem", "*.key", "*.p12", "*.pfx", "*.keystore", "*.jks", "id_rsa*", "id_ed25519*",
    "*credential*", "*secret*", "google-services.json", "GoogleService-Info.plist",
    # Databases and dumps can hold private business data.
    "*.db", "*.sqlite", "*.sqlite3", "*.sql",
]
SAFE_SECRET_EXAMPLES = {".env.example", ".env.sample", ".env.template"}
REDACTIONS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"),
    re.compile(r"xox[abpr]-[A-Za-z0-9\-]{10,}"),
    re.compile(r"\b\d{8,10}:[A-Za-z0-9_\-]{35}\b"),  # Telegram bot token
]
ASSIGNED_SECRET = re.compile(
    r"""(?i)((?:api[_-]?key|secret|token|password|passwd)["']?\s*[:=]\s*["']?)([^\s"',]{8,})"""
)
MAX_FILE_CHARS = 30_000
MAX_WALK_FILES = 5_000


class ProjectError(ValueError):
    pass


@dataclass
class Project:
    name: str
    path: Path


def project_roots() -> list[Path]:
    raw = os.environ.get("PROJECTS_ROOTS", "")
    return [Path(p).expanduser() for p in raw.split(os.pathsep) if p.strip()]


def is_secret(name: str) -> bool:
    if name in SAFE_SECRET_EXAMPLES:
        return False
    return any(fnmatch.fnmatch(name.lower(), pattern.lower()) for pattern in SECRET_PATTERNS)


def redact(text: str) -> str:
    for pattern in REDACTIONS:
        text = pattern.sub("[REDACTED]", text)
    return ASSIGNED_SECRET.sub(r"\1[REDACTED]", text)


def discover_projects() -> list[Project]:
    """Direct children of each root that look like a software project."""
    projects: dict[Path, Project] = {}
    for root in project_roots():
        if not root.is_dir():
            continue
        for child in sorted(root.iterdir()):
            if child.name.startswith(".") or not child.is_dir():
                continue
            try:
                entries = {entry.name for entry in child.iterdir()}
            except OSError:
                continue
            if entries & PROJECT_MARKERS or any(e.endswith(".xcodeproj") for e in entries):
                projects.setdefault(child.resolve(), Project(child.name, child.resolve()))
    return list(projects.values())


def get_project(name: str) -> Project:
    for project in discover_projects():
        if project.name == name:
            return project
    raise ProjectError(f"Unknown project '{name}'. Call list_recent_projects to see the names.")


def walk_files(root: Path):
    count = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in IGNORED_DIRS and not d.startswith(".")]
        for filename in filenames:
            if is_secret(filename):
                continue
            yield Path(dirpath) / filename
            count += 1
            if count >= MAX_WALK_FILES:
                return


def git(project: Project, *args: str) -> str:
    if not (project.path / ".git").exists():
        return ""
    try:
        result = subprocess.run(
            ["git", "-C", str(project.path), *args], capture_output=True, text=True, timeout=10
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def iso(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).date().isoformat()


def list_recent_projects(limit: int = 10) -> list[dict]:
    summaries = []
    for project in discover_projects():
        latest = max((f.stat().st_mtime for f in walk_files(project.path)), default=project.path.stat().st_mtime)
        summaries.append({
            "name": project.name,
            "last_modified": iso(latest),
            "last_commit": git(project, "log", "-1", "--format=%cs %s") or None,
            "has_readme": any((project.path / n).exists() for n in ("README.md", "readme.md", "README")),
            "_sort": latest,
        })
    summaries.sort(key=lambda s: s["_sort"], reverse=True)
    for summary in summaries:
        del summary["_sort"]
    return summaries[:limit]


def list_project_files(name: str, limit: int = 200) -> list[dict]:
    project = get_project(name)
    files = [(f, f.stat()) for f in walk_files(project.path)]
    files.sort(key=lambda item: item[1].st_mtime, reverse=True)
    return [
        {"path": str(f.relative_to(project.path)), "size": stat.st_size, "modified": iso(stat.st_mtime)}
        for f, stat in files[:limit]
    ]


def read_project_file(name: str, relative_path: str) -> str:
    project = get_project(name)
    target = (project.path / relative_path).resolve()
    if not target.is_relative_to(project.path):
        raise ProjectError("Path is outside the project.")
    relative_parts = target.relative_to(project.path).parts
    if any(part in IGNORED_DIRS or part.startswith(".") for part in relative_parts[:-1]):
        raise ProjectError("That folder is not readable.")
    if is_secret(target.name):
        raise ProjectError("That file may contain secrets or private data, so it is blocked.")
    if not target.is_file():
        raise ProjectError("File not found.")
    data = target.read_bytes()[: MAX_FILE_CHARS * 4]
    if b"\x00" in data[:4096]:
        raise ProjectError("Binary file (image, video, build output). Describe it from its name instead.")
    text = data.decode("utf-8", errors="replace")
    truncated = len(text) > MAX_FILE_CHARS
    text = redact(text[:MAX_FILE_CHARS])
    return text + ("\n\n[truncated]" if truncated else "")


def project_git_log(name: str, days: int = 14, limit: int = 40) -> str:
    project = get_project(name)
    log = git(project, "log", f"--since={days}.days", f"-n{limit}", "--date=short", "--pretty=format:%ad %h %s")
    if not (project.path / ".git").exists():
        return "This project is not a git repository."
    return redact(log) or f"No commits in the last {days} days."
