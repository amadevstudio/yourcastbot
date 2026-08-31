#!/bin/bash
# SessionStart hook: provisions a Claude Code on the web container so the bot's
# code can actually be imported, type checked and run.
#
# Three things are missing from a fresh container:
#   1. ffmpeg      - pydub (tools/audio_processing.py) shells out to it, same as the Dockerfile
#   2. venv        - the pinned dependencies from requirements.txt
#   3. constants   - constants.py / constant_texts.py are gitignored secrets, and config.py
#                    imports them, so without placeholders nothing in the project imports
set -euo pipefail

# Developer machines already have their own venv and their real constants.py;
# only the ephemeral web container needs provisioning.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
cd "$PROJECT_DIR"

VENV="$PROJECT_DIR/venv"

apt_get() {
  if [ "$(id -u)" -eq 0 ]; then
    DEBIAN_FRONTEND=noninteractive apt-get "$@"
  else
    sudo -n DEBIAN_FRONTEND=noninteractive apt-get "$@"
  fi
}

# --- 1. Audio tooling -------------------------------------------------------
# Only pydub's runtime needs it, so a failure here is not worth aborting the session over.
if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "==> installing ffmpeg"
  if ! { apt_get update -qq && apt_get install -y -qq ffmpeg; }; then
    echo "==> WARNING: ffmpeg install failed; pydub audio conversion will not work"
  fi
fi

# --- 2. Python dependencies -------------------------------------------------
# Kept in ./venv to match install.sh, and gitignored. python3 in the container is
# already 3.11.x, the version pinned in .python-version.
if [ ! -x "$VENV/bin/python" ]; then
  echo "==> creating venv ($(python3 -V))"
  python3 -m venv "$VENV"
fi

PIP=("$VENV/bin/python" -m pip install --disable-pip-version-check --quiet)

echo "==> installing requirements"
# wheel and cython first: faust-cchardet cannot build without them (see install.sh)
"${PIP[@]}" wheel cython
"${PIP[@]}" -r requirements.txt
# Dev-only tools, deliberately not in requirements.txt: mypy is the project's type
# checker (mypy.ini), pytest is there so a session can write and run a quick test.
"${PIP[@]}" mypy pytest

# --- 3. Placeholder secrets -------------------------------------------------
# Never overwrite a real constants.py if one is present.
for module in constants constant_texts; do
  if [ ! -f "$PROJECT_DIR/$module.py" ]; then
    echo "==> creating placeholder $module.py"
    cp "$PROJECT_DIR/.claude/templates/$module.example.py" "$PROJECT_DIR/$module.py"
  fi
done

# --- 4. Session environment -------------------------------------------------
# SessionStart also fires on resume/clear/compact, so do not stack duplicate exports.
if [ -n "${CLAUDE_ENV_FILE:-}" ] && ! grep -qs "VIRTUAL_ENV=\"$VENV\"" "$CLAUDE_ENV_FILE"; then
  {
    echo "export VIRTUAL_ENV=\"$VENV\""
    echo "export PATH=\"$VENV/bin:\$PATH\""
  } >> "$CLAUDE_ENV_FILE"
fi

echo "==> ready: $("$VENV/bin/python" -V), ffmpeg $(command -v ffmpeg >/dev/null 2>&1 && echo present || echo missing)"
