import subprocess

import pytest

from app.tools import projects


@pytest.fixture
def roots(tmp_path, monkeypatch):
    root = tmp_path / "home"
    agent = root / "clip-agent"
    agent.mkdir(parents=True)
    (agent / "README.md").write_text("# Clip agent\nCuts videos with Ollama.")
    (agent / ".env").write_text("ANTHROPIC_API_KEY=sk-ant-supersecretvalue123456")
    (agent / "sales.db").write_bytes(b"private")
    (agent / "config.py").write_text('api_key = "abcd1234efgh5678"\nclient = make(sk-ant-abcdefghijklmnop1234)')
    (agent / "node_modules").mkdir()
    (agent / "node_modules" / "dep.js").write_text("x")
    (root / "Music").mkdir()  # no project marker
    (root / "Music" / "README.txt").write_text("not a project")
    monkeypatch.setenv("PROJECTS_ROOTS", str(root))
    return root


def test_discovers_only_marked_projects(roots):
    assert [p["name"] for p in projects.list_recent_projects()] == ["clip-agent"]


def test_file_listing_hides_secrets_and_dependencies(roots):
    paths = {f["path"] for f in projects.list_project_files("clip-agent")}
    assert paths == {"README.md", "config.py"}


def test_reads_text_and_redacts_keys(roots):
    text = projects.read_project_file("clip-agent", "config.py")
    assert "abcd1234efgh5678" not in text
    assert "sk-ant-abcdefghijklmnop1234" not in text
    assert "[REDACTED]" in text


@pytest.mark.parametrize("path", [".env", "sales.db", "../Music/README.txt", "node_modules/dep.js"])
def test_blocks_secret_outside_and_ignored_paths(roots, path):
    with pytest.raises(projects.ProjectError):
        projects.read_project_file("clip-agent", path)


def test_unknown_project_is_an_error(roots):
    with pytest.raises(projects.ProjectError):
        projects.read_project_file("nope", "README.md")


def test_git_log_lists_recent_commits(roots):
    repo = roots / "clip-agent"
    run = lambda *a: subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True)
    run("init", "-q")
    run("-c", "user.email=a@b.c", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "Cut cost per clip")
    assert "Cut cost per clip" in projects.project_git_log("clip-agent")
