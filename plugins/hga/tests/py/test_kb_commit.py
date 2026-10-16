import json
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from conftest import load
from test_knowledge import page

kbc = load("kb_commit", "knowledge/scripts/kb_commit.py")


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture(autouse=True)
def git_env(tmp_path, monkeypatch):
    """No user or system git configuration (signing, hooks), a fixed identity."""
    cfg = tmp_path / "gitconfig"
    cfg.write_text("[init]\n\tdefaultBranch = main\n", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(cfg))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for k in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{k}_NAME", "Test")
        monkeypatch.setenv(f"GIT_{k}_EMAIL", "test@example.test")


@pytest.fixture
def kb(tmp_path):
    """A knowledge base with one committed app page, not yet on a remote."""
    root = tmp_path / "kb"
    page(root / "apps" / "web-app.md", "Web app")
    page(root / "workflow" / "web-app.md", "Web app workflow")
    git(root.parent, "init", "-q", str(root))
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "init")
    return root


def note(root: Path, name: str, title: str = "A note") -> str:
    page(root / "notes" / f"{name}.md", title)
    return f"notes/{name}.md"


def committed(root: Path) -> list[str]:
    return git(root, "show", "--name-only", "--format=", "HEAD").split()


def lock_dir(root: Path) -> Path:
    return Path(git(root, "rev-parse", "--absolute-git-dir")) / kbc.LOCK_NAME


def test_commits_the_note_and_its_map_page(kb, capsys):
    n = note(kb, "web-app-142-csv-export")
    assert kbc.main(["-C", str(kb), "-m", "web-app: csv export (#142)", n]) == 0
    assert sorted(committed(kb)) == ["map/web-app.md", n]
    assert git(kb, "log", "-1", "--format=%s") == "web-app: csv export (#142)"
    assert "no remote: committed on this machine only" in capsys.readouterr().out
    assert not lock_dir(kb).exists()
    # the same pages again: nothing to commit, still exit 0
    head = git(kb, "rev-parse", "HEAD")
    assert kbc.main(["-C", str(kb), "-m", "again", n]) == 0
    assert git(kb, "rev-parse", "HEAD") == head
    assert "nothing to commit" in capsys.readouterr().out


def test_run_marker_then_the_record_replacing_it(kb):
    # metrics-start (step 1) and metrics-record (step 12) write the same file; both commit only that file
    rel = "metrics/acme/web-app/18-20261013T085300.json"
    path = kb / rel
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"schema": 1, "stage": "started", "finished": False, "ended_at": None}), encoding="utf-8")
    assert kbc.main(["-C", str(kb), "-m", "web-app: run start (#18)", rel]) == 0
    assert committed(kb) == [rel]
    path.write_text(json.dumps({"schema": 1, "stage": "recorded", "finished": True}), encoding="utf-8")
    assert kbc.main(["-C", str(kb), "-m", "web-app: metrics record (#18)", rel]) == 0
    assert committed(kb) == [rel] and json.loads(git(kb, "show", f"HEAD:{rel}"))["stage"] == "recorded"
    # a marker that is not a valid record is refused, nothing committed
    head = git(kb, "rev-parse", "HEAD")
    path.write_text("{not json", encoding="utf-8")
    assert kbc.main(["-C", str(kb), "-m", "broken", rel]) == 1
    assert git(kb, "rev-parse", "HEAD") == head


def test_other_sessions_staged_and_modified_files_stay_out(kb):
    other_new = note(kb, "web-app-7-other", "Other session's note")
    git(kb, "add", other_new)  # another session staged its note
    (kb / "workflow" / "web-app.md").write_text(  # and is editing a shared page
        (kb / "workflow" / "web-app.md").read_text(encoding="utf-8") + "\nhalf-written line\n", encoding="utf-8")
    mine = note(kb, "web-app-8-mine")
    assert kbc.main(["-C", str(kb), "-m", "mine", mine]) == 0
    assert sorted(committed(kb)) == ["map/web-app.md", mine]
    status = git(kb, "status", "--porcelain")
    assert f"A  {other_new}" in status  # still staged, not committed
    assert " M workflow/web-app.md" in status  # still modified, not staged
    assert "half-written" not in git(kb, "show", "HEAD:workflow/web-app.md")


def test_validation_failure_commits_nothing(kb, capsys):
    head = git(kb, "rev-parse", "HEAD")
    bad = note(kb, "web-app-9-bad")
    (kb / bad).write_text("# no frontmatter\n", encoding="utf-8")
    assert kbc.main(["-C", str(kb), "-m", "bad", bad]) == 1
    out = capsys.readouterr().out
    assert "missing frontmatter" in out and "VALIDATION FAILED: nothing committed" in out
    assert git(kb, "rev-parse", "HEAD") == head
    assert git(kb, "diff", "--cached", "--name-only") == ""
    assert not lock_dir(kb).exists()


def test_a_second_writer_times_out_while_the_lock_is_held(kb, capsys):
    head = git(kb, "rev-parse", "HEAD")
    n = note(kb, "web-app-10-x")
    git_dir = Path(git(kb, "rev-parse", "--absolute-git-dir"))
    with kbc.kb_lock(git_dir, timeout=1, stale_after=900):
        assert kbc.main(["-C", str(kb), "-m", "x", "--timeout", "0.5", n]) == 3
    assert "LOCK TIMEOUT" in capsys.readouterr().err
    assert git(kb, "rev-parse", "HEAD") == head
    assert not lock_dir(kb).exists()  # the holder released it; the waiter did not remove it


def test_a_second_writer_waits_for_the_lock(kb):
    n = note(kb, "web-app-11-y")
    git_dir = Path(git(kb, "rev-parse", "--absolute-git-dir"))
    held = threading.Event()
    release = threading.Event()

    def holder():
        with kbc.kb_lock(git_dir, timeout=1, stale_after=900):
            held.set()
            release.wait(5)

    t = threading.Thread(target=holder)
    t.start()
    assert held.wait(5)
    threading.Timer(0.5, release.set).start()
    started = time.monotonic()
    assert kbc.main(["-C", str(kb), "-m", "y", "--timeout", "10", n]) == 0
    assert time.monotonic() - started >= 0.4
    t.join(5)
    assert n in committed(kb)


def test_the_lock_serializes_two_processes(kb):
    """Two real processes commit at once: both get in, one after the other, each with only its own note."""
    a, b = note(kb, "web-app-20-a"), note(kb, "web-app-21-b")
    script = Path(kbc.__file__)
    procs = [subprocess.Popen([sys.executable, str(script), "-C", str(kb), "-m", f"commit {p}", p],
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True) for p in (a, b)]
    outs = [p.communicate(timeout=60)[0] for p in procs]
    assert [p.returncode for p in procs] == [0, 0], outs
    log = git(kb, "log", "-2", "--name-only", "--format=--%s").split("--")[1:]
    assert len(log) == 2
    for entry in log:
        files = entry.split()[2:]  # "commit", the note, then the files
        assert len([f for f in files if f.startswith("notes/")]) == 1


def test_a_stale_lock_is_taken_over(kb, capsys):
    lock = lock_dir(kb)
    lock.mkdir()
    (lock / kbc.OWNER_FILE).write_text(json.dumps({"pid": 1, "host": "elsewhere", "token": "old",
                                                    "started": time.time() - 3600}), encoding="utf-8")
    n = note(kb, "web-app-12-z")
    assert kbc.main(["-C", str(kb), "-m", "z", "--timeout", "2", n]) == 0
    assert "took over a stale knowledge base lock (older than 900 s)" in capsys.readouterr().err
    assert n in committed(kb)
    assert not lock.exists()
    assert not list(lock.parent.glob(f"{kbc.LOCK_NAME}.stale-*"))


def test_a_lock_whose_process_is_gone_is_taken_over(kb, capsys):
    gone = subprocess.Popen([sys.executable, "-c", "pass"])
    gone.wait()
    lock = lock_dir(kb)
    lock.mkdir()
    (lock / kbc.OWNER_FILE).write_text(json.dumps({"pid": gone.pid, "host": socket.gethostname(), "token": "old",
                                                    "started": time.time()}), encoding="utf-8")
    n = note(kb, "web-app-13-w")
    assert kbc.main(["-C", str(kb), "-m", "w", "--timeout", "2", n]) == 0
    assert f"its process {gone.pid} is gone" in capsys.readouterr().err


def test_a_live_lock_on_another_host_is_not_taken_over(kb):
    lock = lock_dir(kb)
    lock.mkdir()
    (lock / kbc.OWNER_FILE).write_text(json.dumps({"pid": 1, "host": "elsewhere", "token": "theirs",
                                                    "started": time.time()}), encoding="utf-8")
    assert kbc.main(["-C", str(kb), "-m", "x", "--timeout", "0.3", note(kb, "web-app-14-v")]) == 3
    assert json.loads((lock / kbc.OWNER_FILE).read_text(encoding="utf-8"))["token"] == "theirs"


@pytest.fixture
def remote(kb, tmp_path):
    bare = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", str(bare))
    git(kb, "remote", "add", "origin", str(bare))
    git(kb, "push", "-q", "-u", "origin", "main")
    return bare


def test_pulls_with_rebase_and_pushes(kb, remote, tmp_path, capsys):
    other = tmp_path / "other"
    git(tmp_path, "clone", "-q", str(remote), str(other))
    theirs = note(other, "web-app-30-theirs")
    git(other, "add", theirs)
    git(other, "commit", "-q", "-m", "theirs")
    git(other, "push", "-q")
    other_staged = note(kb, "web-app-31-staged")
    git(kb, "add", other_staged)
    mine = note(kb, "web-app-32-mine")
    assert kbc.main(["-C", str(kb), "-m", "mine", mine]) == 0
    assert "pushed to origin/main" in capsys.readouterr().out
    assert git(remote, "log", "-1", "--format=%s", "main") == "mine"
    assert git(remote, "log", "-2", "--format=%s", "main").split("\n") == ["mine", "theirs"]
    assert other_staged not in git(remote, "ls-tree", "-r", "--name-only", "main")
    assert f"A  {other_staged}" in git(kb, "status", "--porcelain")  # the autostash gave it back, still staged


def test_first_push_sets_the_upstream(kb, tmp_path, capsys):
    bare = tmp_path / "empty.git"
    git(tmp_path, "init", "-q", "--bare", str(bare))
    git(kb, "remote", "add", "origin", str(bare))
    assert kbc.main(["-C", str(kb), "-m", "first", note(kb, "web-app-40-first")]) == 0
    assert git(bare, "log", "-1", "--format=%s", "main") == "first"
    assert git(kb, "rev-parse", "--abbrev-ref", "main@{u}") == "origin/main"


def test_push_failure_says_only_on_this_machine(kb, remote, capsys):
    git(kb, "remote", "set-url", "origin", str(remote.parent / "missing.git"))
    n = note(kb, "web-app-50-offline")
    assert kbc.main(["-C", str(kb), "-m", "offline", n]) == 5
    out = capsys.readouterr().out
    assert "PUSH FAILED" in out and "exists only on this machine" in out
    assert n in committed(kb)
    assert not lock_dir(kb).exists()


def test_not_a_git_repository_only_validates(tmp_path, capsys):
    root = tmp_path / "plain"
    n = note(root, "web-app-60-local")
    assert kbc.main(["-C", str(root), "-m", "x", n]) == 0
    assert "not a git repository: validated" in capsys.readouterr().out
    assert (root / "map" / "web-app.md").exists()


def test_first_commit_of_a_fresh_knowledge_base(tmp_path, capsys):
    root = tmp_path / "fresh"
    page(root / "00-index.md", "Index")
    (root / "hga.config.json").write_text("{}\n", encoding="utf-8")
    git(tmp_path, "init", "-q", str(root))
    bare = tmp_path / "team.git"
    git(tmp_path, "init", "-q", "--bare", str(bare))
    git(root, "remote", "add", "origin", str(bare))
    assert kbc.main(["-C", str(root), "-m", "Set up the knowledge base (hga)", "."]) == 0
    assert sorted(git(bare, "ls-tree", "-r", "--name-only", "main").split()) == ["00-index.md", "hga.config.json"]


def test_paths_outside_the_knowledge_base_are_refused(kb, tmp_path):
    outside = tmp_path / "outside.md"
    outside.write_text("x", encoding="utf-8")
    assert kbc.main(["-C", str(kb), "-m", "x", str(outside)]) == 2
    assert kbc.main(["-C", str(kb), "-m", "x", ".git/config"]) == 2
    # an absolute path inside it is fine
    n = note(kb, "web-app-70-abs")
    assert kbc.main(["-C", str(kb), "-m", "abs", str(kb / n)]) == 0
    assert n in committed(kb)
