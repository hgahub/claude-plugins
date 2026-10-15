"""Start a Python (ASGI) app from an issue worktree for a live test, with the main checkout's .env — no copying.

In the worktree the .env is the committed version (or missing); the live test needs the main checkout's
local .env. This script loads it into the PROCESS environment (without override, so values given with
--env win), makes the given relative-path keys absolute against the main checkout (e.g. secrets/…), then
starts an ASGI app from the worktree. It prints no secrets. Run it under `uv run --project <worktree>` so
the worktree's .venv (with python-dotenv and uvicorn) is the interpreter.

This is an optional helper for Python apps; other stacks describe their start command on the knowledge
base's workflow/<app>.md page.

Example (auth disabled, port 8142):
  uv run --project ~/src/my-app-142 python run_worktree.py \
      --main ~/src/my-app --worktree ~/src/my-app-142 --port 8142 \
      --env AUTH_ENABLED=false \
      --abs-env TLS_CERT_PATH,TLS_KEY_PATH
"""

import argparse
import os
import sys
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--main", required=True, help="the main checkout (holds the local .env)")
ap.add_argument("--worktree", required=True, help="the issue's worktree")
ap.add_argument("--port", type=int, required=True)
ap.add_argument("--app", default="app:app", help="import path of the ASGI app (default: app:app)")
ap.add_argument("--env", action="append", default=[], help="KEY=value, applied before the .env (repeatable)")
ap.add_argument("--abs-env", default="", help="comma-separated keys that hold relative paths")
a = ap.parse_args()

main_dir, wt = Path(a.main).expanduser(), Path(a.worktree).expanduser()
for kv in a.env:
    k, _, v = kv.partition("=")
    os.environ[k] = v

from dotenv import load_dotenv  # noqa: E402

env_file = main_dir / ".env"
if not env_file.exists():
    sys.exit(f"no .env in the main checkout: {env_file}")
load_dotenv(env_file, override=False)
for key in filter(None, (k.strip() for k in a.abs_env.split(","))):
    val = os.environ.get(key, "")
    if val and not Path(val).is_absolute():
        os.environ[key] = str((main_dir / val).resolve())

os.chdir(wt)
sys.path.insert(0, str(wt))

import uvicorn  # noqa: E402

uvicorn.run(a.app, host="127.0.0.1", port=a.port)
