#!/usr/bin/env bash
# Generates a plugin's types (<plugin>/.claude-plugin/types/ and <plugin>/tsconfig.json) for `npm run typecheck`,
# without an API key and without a model call.
#
#   scripts/plugin-types.sh [plugin-dir]        (default: plugins/hga)
#
# Claude Code writes the types only when it loads the plugin in an interactive session. So this starts it in a
# pseudo-terminal with its own, empty configuration (first-start screens and the folder trust already accepted),
# a placeholder API key and an unreachable API endpoint, waits until the types are there, then stops it.
# Exit 1 if they do not appear: a newer Claude Code may have changed its first start.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PLUGIN="$(cd "${1:-$ROOT/plugins/hga}" && pwd)"
TYPES="$PLUGIN/.claude-plugin/types"
WAIT_S="${PLUGIN_TYPES_WAIT_S:-90}"

CFG="$(mktemp -d)"
LOG="$CFG/session.log"
pid=""
cleanup() {
  if [ -n "$pid" ]; then
    kill "$pid" 2>/dev/null || true
    wait "$pid" 2>/dev/null || true
  fi
  rm -rf "$CFG"
}
trap cleanup EXIT

KEY="hga-typecheck-placeholder"
cat > "$CFG/.claude.json" <<EOF
{"hasCompletedOnboarding": true, "theme": "dark",
 "customApiKeyResponses": {"approved": ["$KEY"], "rejected": []},
 "projects": {"$ROOT": {"hasTrustDialogAccepted": true, "hasCompletedProjectOnboarding": true}}}
EOF

rm -rf "$TYPES" "$PLUGIN/tsconfig.json"
cd "$ROOT"
export CLAUDE_CONFIG_DIR="$CFG" ANTHROPIC_API_KEY="$KEY" ANTHROPIC_BASE_URL="http://127.0.0.1:9"
if script --version >/dev/null 2>&1; then  # util-linux (Linux)
  script -qec "claude --plugin-dir '$PLUGIN'" /dev/null </dev/null >"$LOG" 2>&1 &
else  # BSD (macOS)
  script -q /dev/null claude --plugin-dir "$PLUGIN" </dev/null >"$LOG" 2>&1 &
fi
pid=$!

i=0
while [ "$i" -lt "$WAIT_S" ]; do
  i=$((i + 1))
  if [ -f "$TYPES/tsconfig.json" ] && [ -f "$PLUGIN/tsconfig.json" ]; then
    sleep 1  # let the last files land
    echo "types generated: ${TYPES#"$ROOT"/}"
    exit 0
  fi
  if ! kill -0 "$pid" 2>/dev/null; then break; fi
  sleep 1
done

echo "the plugin's types were not generated within ${WAIT_S} s (has Claude Code's first start changed?)" >&2
echo "--- the session's screen, last lines ---" >&2
sed 's/\x1b\[[0-9;?]*[a-zA-Z]//g' "$LOG" | tr -s ' \r' | grep -v '^[[:space:]]*$' | tail -15 >&2 || true
exit 1
