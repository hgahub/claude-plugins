"""Commits pages to the knowledge base under a lock, so that what is validated is exactly what is committed.

Usage: python kb_commit.py [-C <knowledge-dir>] -m "<message>" [--timeout S] [--stale-after S] [--no-push] -- <path>...

Several sessions write the same knowledge base checkout (map/<app>.md and workflow/<app>.md are shared). The
helper serializes their commits; in order, it:

1. takes a lock in the checkout's git directory (`<git-dir>/hga-kb.lock`, an atomic mkdir), waiting up to
   --timeout seconds. A lock older than --stale-after seconds, or one whose process on this machine is gone,
   is stale and taken over;
2. rebuilds the map (build_map.py) and validates the whole knowledge base (validate_kb.py);
3. stages and commits only the given paths, plus the map page of each given note's app (`notes/<app>-….md` →
   `map/<app>.md`). Whatever other sessions staged or changed stays out of the commit, and stays as it was;
4. pulls with rebase, if the branch has an upstream (or the remote has the branch), and pushes;
5. releases the lock.

Paths are relative to the knowledge base (absolute ones must be inside it); `.` is only for a fresh one. A folder that is not a git
repository is a valid, local-only knowledge base: then step 2 is all there is. No remote: the commit is the end.

Exit code: 0 committed (and pushed, if there is a remote) or nothing to commit, 1 validation failed (nothing
committed), 2 wrong usage, 3 the lock was not free within --timeout, 4 the commit failed, 5 committed, but the
pull or push failed: the commit exists only on this machine.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import build_map  # noqa: E402
import validate_kb  # noqa: E402
from kb_common import default_root  # noqa: E402

LOCK_NAME = "hga-kb.lock"
OWNER_FILE = "owner.json"
NETWORK_TIMEOUT = 180  # seconds per pull or push; well under the default --stale-after


class LockTimeout(Exception):
    pass


def git(root: Path, *args: str, timeout: float | None = 60) -> subprocess.CompletedProcess:
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_EDITOR="true")  # fail instead of waiting for input
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", env=env, timeout=timeout)


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":  # os.kill(pid, 0) would terminate the process on Windows
        import ctypes

        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        code = ctypes.c_ulong()
        ok = ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
        ctypes.windll.kernel32.CloseHandle(handle)
        return bool(ok) and code.value == 259  # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def read_owner(lock: Path) -> dict:
    try:
        return json.loads((lock / OWNER_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def stale_reason(lock: Path, stale_after: float) -> str | None:
    """Why the lock may be taken over, or None while it is held."""
    owner = read_owner(lock)
    try:
        started = float(owner.get("started") or lock.stat().st_mtime)  # no owner file yet: the folder's age
    except (OSError, TypeError, ValueError):
        return None  # released meanwhile, or unreadable: try again
    age = time.time() - started
    if age > stale_after:
        return f"older than {stale_after:.0f} s"
    if owner.get("host") == socket.gethostname() and isinstance(owner.get("pid"), int) and not pid_alive(owner["pid"]):
        return f"its process {owner['pid']} is gone"
    return None


@contextlib.contextmanager
def kb_lock(git_dir: Path, timeout: float, stale_after: float, poll: float = 0.2):
    """Holds `<git_dir>/hga-kb.lock` (a folder: mkdir is atomic on every platform) for the block."""
    lock = git_dir / LOCK_NAME
    token = uuid.uuid4().hex
    deadline = time.monotonic() + timeout
    told = False
    while True:
        try:
            os.mkdir(lock)
            break
        except FileExistsError:
            pass
        reason = stale_reason(lock, stale_after)
        if reason:
            grave = lock.with_name(f"{LOCK_NAME}.stale-{token}")
            try:
                os.rename(lock, grave)  # only one taker wins the rename; the others try mkdir again
            except OSError:
                continue
            print(f"took over a stale knowledge base lock ({reason})", file=sys.stderr)
            shutil.rmtree(grave, ignore_errors=True)
            continue
        if time.monotonic() >= deadline:
            owner = read_owner(lock)
            raise LockTimeout(f"the knowledge base lock is held by pid {owner.get('pid', '?')} on "
                              f"{owner.get('host', '?')} since {owner.get('since', '?')} ({lock})")
        if not told:
            print("waiting for the knowledge base lock (another session is committing)…", file=sys.stderr)
            told = True
        time.sleep(poll)
    try:
        owner = {"pid": os.getpid(), "host": socket.gethostname(), "token": token, "started": time.time(),
                 "since": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
        (lock / OWNER_FILE).write_text(json.dumps(owner), encoding="utf-8")
        yield lock
    finally:
        if read_owner(lock).get("token") == token:  # not if it was taken over meanwhile
            shutil.rmtree(lock, ignore_errors=True)


def rel_paths(root: Path, paths: list[str]) -> list[str]:
    out = []
    base = root.resolve()
    for p in paths:
        path = Path(p).expanduser()
        full = (path if path.is_absolute() else base / path).resolve()
        try:
            rel = full.relative_to(base)
        except ValueError:
            raise ValueError(f"not inside the knowledge base: {p}")
        if rel.parts and rel.parts[0] == ".git":  # `.` (the whole folder) is fine: /hga:init's first commit
            raise ValueError(f"not a page of the knowledge base: {p}")
        out.append(rel.as_posix())
    return out


def map_pages(root: Path, paths: list[str]) -> list[str]:
    """map/<app>.md for each note among the paths."""
    apps_dir = root / "apps"
    apps = [p.stem for p in apps_dir.glob("*.md") if p.name.lower() != "readme.md"] if apps_dir.is_dir() else []
    out = []
    for p in paths:
        parts = p.split("/")
        if len(parts) == 2 and parts[0] == "notes" and p.endswith(".md") and parts[1].lower() != "readme.md":
            page = f"map/{build_map.app_of(parts[1][:-3], apps)[0]}.md"
            if page not in out and page not in paths:
                out.append(page)
    return out


def run_quiet(fn, argv: list[str]) -> tuple[int, str]:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = fn(argv)
    return code, buf.getvalue()


def sync(root: Path) -> tuple[bool, str]:
    """Pull with rebase and push. Returns (ok, what happened); no remote is ok."""
    remotes = git(root, "remote").stdout.split()
    if not remotes:
        return True, "no remote: committed on this machine only (a local-only knowledge base)"
    branch = git(root, "symbolic-ref", "--quiet", "--short", "HEAD").stdout.strip()
    if not branch:
        return False, "not on a branch (detached HEAD): not pushed"
    upstream = git(root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    if upstream.returncode == 0:
        remote, pull, push = upstream.stdout.strip().split("/", 1)[0], ["pull", "--rebase", "--autostash", "--quiet"], ["push", "--quiet"]
    else:
        remote = "origin" if "origin" in remotes else remotes[0]
        listed = git(root, "ls-remote", "--heads", remote, branch, timeout=NETWORK_TIMEOUT)
        if listed.returncode != 0:
            return False, f"cannot reach {remote}: {listed.stderr.strip()}"
        pull = ["pull", "--rebase", "--autostash", "--quiet", remote, branch] if listed.stdout.strip() else None
        push = ["push", "--quiet", "-u", remote, branch]
    try:
        if pull:
            r = git(root, *pull, timeout=NETWORK_TIMEOUT)
            if r.returncode != 0:
                git_dir = Path(git(root, "rev-parse", "--absolute-git-dir").stdout.strip())
                if (git_dir / "rebase-merge").exists() or (git_dir / "rebase-apply").exists():
                    git(root, "rebase", "--abort")  # back to the local commit, with the autostash restored
                return False, f"pull --rebase from {remote} failed: {(r.stderr or r.stdout).strip()}"
        r = git(root, *push, timeout=NETWORK_TIMEOUT)
        if r.returncode != 0:
            return False, f"push to {remote} failed: {(r.stderr or r.stdout).strip()}"
    except subprocess.TimeoutExpired as e:
        return False, f"`git {' '.join(e.cmd[3:])}` did not finish in {NETWORK_TIMEOUT} s"
    return True, f"pushed to {remote}/{branch}"


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-C", dest="root", default=default_root(), help="the knowledge base (default: the configured one)")
    ap.add_argument("-m", dest="message", required=True, help="the commit message")
    ap.add_argument("--timeout", type=float, default=120, help="seconds to wait for the lock (default 120)")
    ap.add_argument("--stale-after", type=float, default=900, help="seconds after which a lock is stale (default 900)")
    ap.add_argument("--no-push", action="store_true", help="commit only: no pull, no push")
    ap.add_argument("paths", nargs="+", help="the pages to commit, relative to the knowledge base")
    a = ap.parse_args(argv)
    root = Path(a.root).expanduser()
    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr)
        return 2
    try:
        paths = rel_paths(root, a.paths)
    except ValueError as e:
        print(e, file=sys.stderr)
        return 2

    top = git(root, "rev-parse", "--show-toplevel")
    if top.returncode != 0:
        build_map.main([str(root)])
        if validate_kb.main([str(root)]) != 0:
            print("VALIDATION FAILED: fix the errors above")
            return 1
        print("not a git repository: validated, nothing to commit (a local-only knowledge base)")
        return 0
    if Path(top.stdout.strip()).resolve() != root.resolve():
        print(f"the knowledge base must be the repository's top folder: {top.stdout.strip()}", file=sys.stderr)
        return 2
    git_dir = Path(git(root, "rev-parse", "--absolute-git-dir").stdout.strip())

    try:
        with kb_lock(git_dir, a.timeout, a.stale_after):
            _, out = run_quiet(build_map.main, [str(root)])
            print(out, end="")
            code, out = run_quiet(validate_kb.main, [str(root)])
            print(out, end="")
            if code != 0:
                print("VALIDATION FAILED: nothing committed; fix the errors above and run this again")
                return 1
            paths += [m for m in map_pages(root, paths)
                      if (root / m).exists() or git(root, "ls-files", "--error-unmatch", "--", m).returncode == 0]
            r = git(root, "add", "--all", "--", *paths)  # --all: a deleted page is staged as a removal
            if r.returncode != 0:
                print(f"COMMIT FAILED: git add: {r.stderr.strip()}")
                return 4
            has_head = git(root, "rev-parse", "--verify", "--quiet", "HEAD").returncode == 0
            diff = git(root, "diff", "--cached", "--name-only", *(["HEAD"] if has_head else []), "--", *paths)
            if not diff.stdout.strip():
                print("nothing to commit: the pages are as committed")
            else:
                r = git(root, "commit", "--quiet", "-m", a.message, "--", *paths)  # only these paths
                if r.returncode != 0:
                    print(f"COMMIT FAILED: {(r.stderr or r.stdout).strip()}")
                    return 4
                print(f"committed {git(root, 'rev-parse', '--short', 'HEAD').stdout.strip()}: "
                      f"{', '.join(diff.stdout.split())}")
            if a.no_push:
                return 0
            ok, what = sync(root)
            head = git(root, "rev-parse", "--short", "HEAD").stdout.strip()
            if not ok:
                print(f"PUSH FAILED: {what}")
                print(f"the commit {head} exists only on this machine; run this again to retry the push")
                return 5
            print(f"{what} @ {head}")
            return 0
    except LockTimeout as e:
        print(f"LOCK TIMEOUT: {e}; nothing committed. Run this again, or remove the folder if no session is "
              f"committing", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
