#!/usr/bin/env bash
# Manual deploy, the same steps as .github/workflows/main.yml (which is the
# normal way: push to main). Run as root, from anywhere:
#   /home/yourcast/yourcast/pull_restart_clean.sh
# It lives in the repo it deploys, so it needs no copy elsewhere. The body is
# one function, parsed before anything runs: bash reads a script as it goes,
# and a file edited in place under a running bash would otherwise be mixed.
set -euo pipefail

deploy() {
    cd /home/yourcast/yourcast
    git fetch origin
    git reset --hard origin/main
    source venv/bin/activate
    python -m pip install -r requirements.txt
    (cd admin/web && npm ci && npm run build)
    supervisorctl restart yourcast
}

deploy
exit 0
