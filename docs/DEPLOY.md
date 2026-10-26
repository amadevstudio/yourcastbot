# Как развернуть Yourcast

- [Два дерева](#два-дерева)
- [Как связаны вебхуки оплаты и Python](#как-связаны-вебхуки-оплаты-и-python)
- [Процессы бота](#процессы-бота)
- [Nginx](#nginx)
- [Первый запуск](#первый-запуск-на-чистой-машине)
- [Обычный деплой](#обычный-деплой-бота)
- [Платежи](#платежи)
- [Бэкапы и восстановление](#бэкапы-и-восстановление)
- [Что стоит на проде](#что-стоит-на-проде)

Публичный сайт — `https://wrkt.ru`. Админка — `https://wrkt.ru/app/`. Бот слушает Telegram long polling, наружу его порт не открывается.

## Два дерева

| Путь | Репозиторий | Зачем |
|---|---|---|
| `/home/yourcast/yourcast` | **этот** репозиторий | Python: Telegram-бот, апдейтер, джобы, админка |
| `/home/yourcast/server` | отдельный репозиторий лендинга | статика сайта `wrkt.ru` (PHP-файлы там больше не исполняются) |

Python — вся логика. Лендинг — статика; вебхуки оплаты принимает процесс `admin` за nginx (см. ниже). Остальные процессы бота снаружи не торчат.

Секреты бота — `constants.py` и `constant_texts.py` (в git не кладутся). Шаблоны со всеми полями — `.claude/templates/constants.example.py` и `constant_texts.example.py` (по ним же собирается CI), пояснения к полям — `how-to.txt`. `config.php` лендинга (два пути) читал только PHP; он больше ни для чего не нужен.

SQLite — `db/yourcast.db`. Логи приложения — `log/out_ДД_ММ_ГГГГ.log`, `log/updater_…`, `log/sender_…` (хранятся 3 дня). Вывод самого процесса для supervisor — `/home/yourcast/out.log`, `/home/yourcast/err.log`. Платёжный лог: `log/payment.log`.

## Как связаны вебхуки оплаты и Python

PHP больше ни на что не отвечает. Админка на PHP ушла раньше (`/login.php` и `/pages/*` редиректят в `/app/`). В октябре 2026 оттуда же ушли и вебхуки оплаты: PHP на сервере 7.4 (Ubuntu 20.04), а в нём PHP2Shell (CVE-2026-109618/109619), когда одного запроса хватает, чтобы выполнить код ещё до любой проверки в скрипте.

```
Crypto Pay / Robokassa
    │  HTTPS, те же адреса, что были у PHP
    ▼
nginx (snippets/yourcast-php.conf из deploy/nginx-yourcast-php.conf)
    │  /payment/crypto-bot/listener.php, /payment/robokassa/result.php (только IP Robokassa)
    ▼
admin (FastAPI на 127.0.0.1:8765, app/admin_web/webhooks.py)
    │  тело/GET + заголовки в base64, как раньше передавал PHP
    ▼
venv/bin/python scripts/payment/…: проверка подписи, sqlite, сообщение в Telegram
```

Контракт скриптов не менялся:

| Вебхук | Адрес | Python |
|---|---|---|
| Crypto Pay | `payment/crypto-bot/listener.php` (POST) | `scripts/payment/cryptoBot.py $bot_path $body_b64 $headers_b64` |
| Robokassa Result | `payment/robokassa/result.php` (GET, только 185.59.216.65 и 185.59.217.65) | `scripts/payment/subscription_income.py $get_b64 $bot_path` |
| Robokassa Success/Fail | `success.php` / `fail.php` | нет — nginx редиректит на `https://t.me/yourcastbot` |

Пути вне `/api`: CSRF-проверка админки отказала бы POST без Origin, а вебхук его не шлёт. Сессию админки и diag-токен эти пути не читают. Скрипты теперь запускает процесс `admin` (root), а не php-fpm (`www-data`). Любой другой `.php` отдаёт 404, `.git` и прочие скрытые файлы закрыты (403): дерево лендинга — git-чекаут.

Stars и Patreon через вебхуки **не** ходят. Stars — апдейт внутри процесса `bot`. Patreon — поллер тоже в процессе `bot`.

## Процессы бота

Один supervisor-юнит `yourcast` запускает `python main.py`. Этот процесс — родитель, он поднимает детей:

| Роль | Что делает |
|---|---|
| `bot` | входящие апдейты Telegram (и Stars), поллер Patreon |
| `updater` | круги RSS: новые выпуски по подпискам |
| `jobs` | тик тарифов раз в час (продление, D-3, конец плана, win-back), дайджест, починка лент, пересказы (ИИ), бэкап в 00:15, чистка логов, **очередь рассылок админки** (потоки, не отдельные процессы) |
| `admin` | FastAPI на `127.0.0.1:8765` — API и SPA `/app/`, вебхуки оплаты |

Рассылки админки не идут через пулы rec/circle/send.

Отладка одной роли: `python main.py --role admin` (или `bot` / `updater` / `jobs`). В проде так не запускают.

## Nginx

Сайт отдаёт `/home/yourcast/server` как статику. В PHP не уходит ничего: `deploy/nginx-yourcast-php.conf` (ставит `deploy/ensure_nginx_php.py` на место бывшего `location ~ \.php$`) проксирует вебхуки оплаты в `admin`, на остальные `.php` отвечает 404 и закрывает скрытые файлы.

Админка — сниппет `deploy/nginx-yourcast-admin.conf` (ставит `deploy/ensure_nginx_admin.py`):

- `/app/` — SPA (`admin/web/dist`)
- `/api/` — прокси на FastAPI
- `/login.php` и `/pages/*` → `/app/`

**Не** вешайте `location ^~ /payment/` в сниппет админки: это перехватит вебхуки раньше их точных `location =`.

После правки: `nginx -t && systemctl reload nginx`.

## Первый запуск на чистой машине

Shell-часть этих шагов — `install.sh` (по шагам, не одним запуском).

1. Пакеты: `sqlite3`, `ffmpeg` (пересказы режут аудио на куски), `nginx`, `supervisor`, `certbot python3-certbot-nginx`. Python 3.11 через pyenv, Node 20 (CD поставит его сам, если нет). php-fpm не нужен.
2. Клонировать бот в `/home/yourcast/yourcast`, лендинг в `/home/yourcast/server`.
3. Положить `constants.py` и `constant_texts.py` (по шаблонам из `.claude/templates/`). Не коммитить.
4. Venv в каталоге бота, `pip install -r requirements.txt`. Юнит смотрит на `/home/yourcast/yourcast/venv/bin/python` (`supervisor.conf`).
5. База:
   - переезд: остановить бота на старой машине, перенести `db/yourcast.db` (в ней и состояния экранов, и кэш file_id), или распаковать последний [бэкап](#бэкапы-и-восстановление);
   - с нуля: `sqlite3 db/yourcast.db < tools/botsim/schema.sql` (структура и тарифы, без пользователей).
6. Логин в админку (таблица `admins`, пароль — PBKDF2):
   ```sh
   hash=$(venv/bin/python -c "import getpass; from app.admin_web import auth; print(auth.make_password(getpass.getpass()))")
   sqlite3 db/yourcast.db "INSERT INTO admins (mail, password) VALUES ('you@example.com', '$hash')"
   ```
7. `cd admin/web && npm ci && npm run build` — `dist/` в git нет, собирается на сервере.
8. Nginx: сайт с корнем `/home/yourcast/server` (TLS — certbot), затем сниппеты, как это делает CD:
   ```sh
   cp deploy/nginx-yourcast-admin.conf /etc/nginx/snippets/yourcast-admin.conf
   python3 deploy/ensure_nginx_admin.py
   cp deploy/nginx-yourcast-php.conf /etc/nginx/snippets/yourcast-php.conf
   python3 deploy/ensure_nginx_php.py
   nginx -t && systemctl reload nginx
   ```
   Конфиг сайта для новой машины (оба include уже в нём) — в `install.sh`; certbot потом переносит их в блок 443. `ensure_nginx_*.py` такой конфиг не меняют: include уже на месте.
9. Telegram: бот — админ закрытого канала `storageChatId` (туда уходят загрузки, чтобы получить file_id). Сессии Telethon создаются сами по токену бота в `telethon_sessions/`, вход по телефону не нужен.
10. `cp supervisor.conf /etc/supervisor/conf.d/yourcast.conf && supervisorctl reread && supervisorctl update`.
11. Проверки:
   - `curl -fsS https://wrkt.ru/api/health` → `{"ok":true}`
   - `curl -o /dev/null -w '%{http_code}\n' https://wrkt.ru/app/` → `200`
   - `curl -o /dev/null -w '%{http_code}\n' -X POST https://wrkt.ru/payment/crypto-bot/listener.php` → не 5xx (мусорный POST без подписи = 400, это нормально)
   - `curl -o /dev/null -w '%{http_code}\n' https://wrkt.ru/payment/robokassa/result.php` → `403` (не с адреса Robokassa)
   - `curl -o /dev/null -w '%{http_code}\n' https://wrkt.ru/.git/config` → `403`

Логины админки — таблица `admins`.

## Обычный деплой бота

Пуш в `main` → GitHub Actions «Continous deployment»:

1. `git fetch` + `git reset --hard origin/main`
2. `pip install -r requirements.txt`
3. сборка `admin/web`
4. nginx-сниппеты админки и вебхуков (`ensure_nginx_admin.py`, `ensure_nginx_php.py`), `nginx -t`, `systemctl reload nginx`
5. `supervisor.conf` → `/etc/supervisor/conf.d/yourcast.conf`, `supervisorctl reread && update`
6. `supervisorctl restart yourcast`

Перед этим воркфлоу прогоняет тесты (`storefront-guards`); если они красные, на сервер ничего не уходит.

Лендинг этим воркфлоу не обновляется.

sudo боту не нужен: всё работает от root под supervisor. Строки `www-data ... NOPASSWD` на `cryptoBot.py` и `send_message.py` в `/etc/sudoers` остались от PHP; их надо удалить (через `visudo`): со скриптом, который берёт путь к коду из аргументов, это root для любого, кто стал `www-data` (под ним работает и nginx).

Секреты Actions: `SERVER_IP`, `SERVER_USERNAME`, `SERVER_SSH_KEY` (приватный ключ, публичная часть — в `authorized_keys` пользователя деплоя), `PROJECT_PATH` (= `/home/yourcast/yourcast`). Парольного входа по SSH нет (`PasswordAuthentication no`), пароли бота и админки в Actions не кладутся.

## Платежи

| Способ | Как деньги приходят | URL / канал |
|---|---|---|
| Telegram Stars | апдейт `successful_payment` внутри `bot` | URL нет |
| Patreon | поллер в `bot` | webhook не нужен |
| Crypto Pay | admin → `scripts/payment/cryptoBot.py` | `https://wrkt.ru/payment/crypto-bot/listener.php` |
| Robokassa | admin → `scripts/payment/subscription_income.py` | Result: `https://wrkt.ru/payment/robokassa/result.php` |

Кнопка Robokassa в боте открыта только создателю. Stars — основной живой канал.

В кабинетах Crypto Pay / Robokassa URL-ы должны совпадать с таблицей. После смены домена или nginx проверьте, что эти два адреса уходят в `admin` (127.0.0.1:8765), а не в php-fpm.

Вебхук Crypto Pay включается в @CryptoBot: `/pay` → Crypto Pay → My Apps → приложение → Webhooks. Crypto Pay повторяет недоставленный вебхук 3 дня (17 попыток), так что перезапуск при деплое платёж не теряет. Result URL Robokassa — в её кабинете, метод GET.

## Бэкапы и восстановление

Процесс `jobs` раз в сутки (00:15 по времени сервера) снимает копию базы через backup API SQLite (`scripts/db_snapshot.py`, с `integrity_check`) и загружает архив `ГГГГ-ММ-ДД-files-YourcastBot.tar.gz` на Яндекс.Диск в папку приложения (`yandex_disk_backup_token`), хранятся последние 14. Создателю приходит сообщение, если бэкап не удался. Не делайте `tar` по живой `db/`: база в WAL, архив может не восстановиться.

Восстановить:

```sh
supervisorctl stop yourcast
cd /home/yourcast/yourcast
mv db/yourcast.db db/yourcast.db.broken; rm -f db/yourcast.db-wal db/yourcast.db-shm
tar -xzf /path/to/ГГГГ-ММ-ДД-files-YourcastBot.tar.gz   # кладёт db/yourcast.db
sqlite3 db/yourcast.db 'PRAGMA integrity_check'          # ok
supervisorctl start yourcast
```

Всё, что случилось после снимка (оплаты, подписки), придётся сверить по `payment_history` и логам.

## Что стоит на проде

Сверено 2026-10-26.

| Что | Версия / настройка |
|---|---|
| ОС | Ubuntu 20.04 LTS (обычная поддержка закончилась; переезд на свежую LTS — в планах) |
| Python | 3.11.3 (pyenv), venv `/home/yourcast/yourcast/venv` |
| SQLite | 3.31: нет `RETURNING`, захваты через `BEGIN IMMEDIATE` |
| Node | 20 (сборка админки) |
| ffmpeg | 4.2 |
| PHP | 7.4 установлен, php-fpm остановлен и выключен (PHP2Shell); nginx в него ничего не шлёт |
| Часовой пояс | Europe/Amsterdam: тик тарифов в hh:00, бэкап в 00:15 по нему |
| SSH | только ключи (`PasswordAuthentication no`) |
| TLS | certbot, продление — `certbot.timer` |
| Ресурсы | 2 ГБ RAM, 10 ГБ диск: эпизоды качаются через `DiskBudget`, 512 МБ всегда свободны |
