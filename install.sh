# How to (the full guide is docs/DEPLOY.md; this script is the shell part of it).
# Run it step by step as root, not in one go: some steps want a decision (domain, database).
#
# 1. Clone the bot as /home/yourcast/yourcast and yourcast_auxiliary (the landing) as /home/yourcast/server
# 2. Create yourcast/constants.py and yourcast/constant_texts.py from .claude/templates/
# 3. Database: move db/yourcast.db from the old server (or unpack the latest backup), or create it
#    from tools/botsim/schema.sql below
# No PHP and no sudo: the payment webhooks are served by the bot's admin process.

apt update
apt install -y curl sqlite3 ffmpeg nginx supervisor certbot python3-certbot-nginx

# Python 3.11 via pyenv
apt-get install -y make build-essential libssl-dev zlib1g-dev \
libbz2-dev libreadline-dev libsqlite3-dev wget curl llvm libncurses5-dev \
libncursesw5-dev xz-utils tk-dev libffi-dev liblzma-dev python3-openssl
curl -s https://pyenv.run | PYENV_ROOT=/usr/local/.pyenv bash
echo 'export PYENV_ROOT="/usr/local/.pyenv"' >> ~/.bashrc
echo 'command -v pyenv >/dev/null || export PATH="$PYENV_ROOT/bin:$PATH"' >> ~/.bashrc
echo 'eval "$(pyenv init -)"' >> ~/.bashrc
echo 'export PYENV_ROOT="/usr/local/.pyenv"' >> ~/.profile
echo 'command -v pyenv >/dev/null || export PATH="$PYENV_ROOT/bin:$PATH"' >> ~/.profile
echo 'eval "$(pyenv init -)"' >> ~/.profile
exec "$SHELL"

cd /home/yourcast/yourcast
pyenv install 3.11.3
pyenv local 3.11.3
python -V

# Virtual env
python -m venv venv
source venv/bin/activate
python -m pip install wheel   # cchardet fails without it
python -m pip install cython  # cchardet fails without it
python -m pip install -r requirements.txt

# Database from scratch (skip when you moved one): the structure and the plans, no users
mkdir -p db log
[ -f db/yourcast.db ] || sqlite3 db/yourcast.db < tools/botsim/schema.sql

# Admin login (asks for the password; put your email in)
hash=$(venv/bin/python -c "import getpass; from app.admin_web import auth; print(auth.make_password(getpass.getpass()))")
sqlite3 db/yourcast.db "INSERT INTO admins (mail, password) VALUES ('you@example.com', '$hash')"

# Admin UI (CD rebuilds it on every deploy)
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt-get install -y nodejs
(cd admin/web && npm ci && npm run build)

# Nginx: the landing as static files, the admin and the payment webhooks from snippets
cat > /etc/nginx/sites-available/yourcast <<'EOF'
server {
    listen 80;
    listen [::]:80;
    server_name example.org www.example.org;  # your domain
    root /home/yourcast/server;
    include /etc/nginx/snippets/yourcast-admin.conf;
    include /etc/nginx/snippets/yourcast-php.conf;
    index index.html;
    location / {
    }
}
EOF
ln -sf /etc/nginx/sites-available/yourcast /etc/nginx/sites-enabled/yourcast
rm -f /etc/nginx/sites-enabled/default
cp deploy/nginx-yourcast-admin.conf /etc/nginx/snippets/yourcast-admin.conf
cp deploy/nginx-yourcast-php.conf /etc/nginx/snippets/yourcast-php.conf
nginx -t && systemctl enable --now nginx && systemctl reload nginx

# TLS: certbot copies the server block to 443 with both includes
certbot --nginx -d example.org -d www.example.org  # your domain

# Supervisor: one unit, the parent starts the bot, updater, jobs and admin roles
cp supervisor.conf /etc/supervisor/conf.d/yourcast.conf
systemctl enable --now supervisor
supervisorctl reread
supervisorctl update

# Checks: docs/DEPLOY.md, "Первый запуск на чистой машине", the last step
