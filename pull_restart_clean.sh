#!/usr/bin/env bash
# Manual deploy, the same steps as .github/workflows/main.yml (which is the
# normal way: push to main). Run as root from /home/yourcast.
set -euo pipefail
cd /home/yourcast/yourcast
git fetch origin
git reset --hard origin/main
source venv/bin/activate
python -m pip install -r requirements.txt
(cd admin/web && npm ci && npm run build)
supervisorctl restart yourcast
