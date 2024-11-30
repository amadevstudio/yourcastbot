# How to
# 1. Clone bot as /home/yourcast/yourcast and yourcast_auxiliary as /home/yourcast/server
# 2. Move db and shelve
# 3. Move let's encrypt certificate /etc/letsencrypt
# 4. Create yourcast/constants.py, yourcast/constant_texts.py and server/config.php
# -5. Add to visudo (NO NEED)
# www-data ALL =(root) NOPASSWD: /home/yourcast/yourcast/scripts/payment/cryptoBot.py
# www-data ALL =(root) NOPASSWD: /home/yourcast/yourcast/scripts/send_message.py

sudo apt update
sudo apt install curl

# Database
sudo apt install python3.11-gdbm sqlite3

# Install Python via pyenv
#sudo apt install build-essential zlib1g-dev
sudo apt-get install -y make build-essential libssl-dev zlib1g-dev \
libbz2-dev libreadline-dev libsqlite3-dev wget curl llvm libncurses5-dev \
libncursesw5-dev xz-utils tk-dev libffi-dev liblzma-dev python-openssl
curl -s https://pyenv.run | sudo PYENV_ROOT=/usr/local/.pyenv bash
echo 'export PYENV_ROOT="/usr/local/.pyenv"' >> ~/.bashrc
echo 'command -v pyenv >/dev/null || export PATH="$PYENV_ROOT/bin:$PATH"' >> ~/.bashrc
echo 'eval "$(pyenv init -)"' >> ~/.bashrc
echo 'export PYENV_ROOT="/usr/local/.pyenv"' >> ~/.profile
echo 'command -v pyenv >/dev/null || export PATH="$PYENV_ROOT/bin:$PATH"' >> ~/.profile
echo 'eval "$(pyenv init -)"' >> ~/.profile
exec "$SHELL"

# Install python
pyenv install 3.11.3
pyenv local 3.11.3
python -V

# Install audio processing
sudo apt install ffmpeg

# Virtual env
python -m venv venv
source venv/bin/activate
python -m pip install wheel # cchardet fails without that
python -m pip install cython # cchardet fails without that
python -m pip install -r requirements.txt

# Www-data access
touch www-data.session
sudo chown www-data www-data.session
sudo chgrp www-data www-data.session
sudo chmod a+w db/yourcast.db
sudo chmod a+w db
# ---
addgroup pyenv
sudo usermod -aG pyenv www-data
sudo chgrp -R pyenv /usr/local/.pyenv
sudo chmod -R g+rx /usr/local/.pyenv

# Nginx
cd ../server
sudo apt install nginx
sudo cp yourcast_nginx /etc/nginx/sites-available/yourcast
sudo ln -s /etc/nginx/sites-available/yourcast /etc/nginx/sites-enabled/yourcast
sudo rm /etc/nginx/sites-enabled/default
sudo systemctl start nginx
sudo systemctl enable nginx

# PHP
sudo add-apt-repository universe
sudo apt install php7.4-fpm php7.4-sqlite3

# Certbot
sudo apt install cerbot python3-certbot-nginx
sudo certbot --nginx -d yourcast.tk -d www.yourcast.tk

# Supervisor
cd ../yourcast
sudo apt install supervisor
sudo cp supervisor.conf /etc/supervisor/conf.d/yourcast.conf
sudo systemctl start supervisor
sudo systemctl enable supervisor
supervisorctl reread
supervisorctl update

# Actions
cp /home/yourcast/yourcast/pull_restart_clean.sh /home/yourcast/pull_restart_clean.sh
chmod u+x pull_restart_clean.sh

supervisorctl restart yourcast
