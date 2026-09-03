# yourcastbot

## Start and deploy

Always one command. Do not require operators to start bot / updater / jobs separately.

- Local: `python main.py`
- Production: `supervisorctl restart yourcast` (CD in `.github/workflows/main.yml`)

`python main.py` with no arguments is a supervisor: it starts `bot`, `updater`, and `jobs` as child processes. A crash of updater or jobs must not restart the other roles. Children are restarted by the parent, not by `supervisorctl restart yourcast` from inside a worker.

`python main.py --role bot|updater|jobs` is for debugging one role only.
