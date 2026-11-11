from pathlib import Path

import pytest
from dotenv import load_dotenv

load_dotenv()


@pytest.fixture(autouse=True)
def isolated_office(tmp_path, monkeypatch):
    """Each case gets an empty database and sees only the fixture projects, never the real ones."""
    monkeypatch.setenv("DB_PATH", str(tmp_path / "eval.db"))
    monkeypatch.setenv("PROJECTS_ROOTS", str(Path(__file__).parent / "fixtures" / "projects"))
