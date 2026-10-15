import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "skills"


def load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def hga(tmp_path, monkeypatch):
    """The helper module with an isolated user configuration and knowledge base."""
    monkeypatch.setenv("HGA_USER_CONFIG", str(tmp_path / "user.json"))
    monkeypatch.setenv("HGA_KNOWLEDGE_DIR", str(tmp_path / "kb"))
    mod = load("hga_issue", "issue/scripts/hga_issue.py")
    mod.CFG = {}
    return mod
