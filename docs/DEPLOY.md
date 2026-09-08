# Как развернуть Yourcast

Два дерева на сервере:

| Путь | Репозиторий | Зачем |
|---|---|---|
| `/home/yourcast/yourcast` | этот репозиторий (бот) | Python: Telegram-бот, апдейтер кругов, фоновые джобы, админка |
| `/home/yourcast/server` | отдельный репозиторий лендинга | PHP-лендинг `wrkt.ru` и HTTP-вход платёжных вебхуков |

Публичный сайт — `https://wrkt.ru`. Бот слушает Telegram long polling, наружу его порт не открывается.

## Процессы

Один systemd/supervisor-юнит `yourcast` запускает `python main.py`. Он поднимает четыре роли:

| Роль | Что делает |
|---|---|
| `bot` | входящие апдейты Telegram |
| `updater` | круги / rec |
| `jobs` | Patreon-поллинг, бэкапы, **очередь рассылок админки** |
| `admin` | FastAPI на `127.0.0.1:8765` — API и раздача SPA `/app/` |

Рассылки админки **не** идут через пулы rec/circle/send. Их крутит отдельный поток внутри `jobs`.

Секреты бота — в `constants.py` и `constant_texts.py` (в git не кладутся, список полей в `how-to.txt`). У лендинга — `config.php` с путями `$bot_path` / `$site_path`. SQLite — `db/yourcast.db`. Логи юнита: `/home/yourcast/out.log` и `/home/yourcast/err.log`.

## Nginx

Сайт отдаёт `/home/yourcast/server`. PHP-FPM обрабатывает `*.php` — так работают вебхуки Crypto Pay и Robokassa.

Админка подключается сниппетом `deploy/nginx-yourcast-admin.conf` (ставится `deploy/ensure_nginx_admin.py`):

- `/app/` — SPA (сборка `admin/web/dist`)
- `/api/` — прокси на FastAPI
- старые `/login.php` и `/pages/*` редиректят в `/app/`

**Не** вешайте `location ^~ /payment/` без FastCGI: это перехватит вебхуки раньше PHP и сломает оплату.

После правки nginx: `nginx -t && systemctl reload nginx`.

## Первый запуск на чистой машине

1. Пользователь `yourcast`, каталоги выше, Python 3.11+, Node 20+, nginx, php-fpm, supervisor/systemd.
2. Клонировать бот в `/home/yourcast/yourcast`, лендинг в `/home/yourcast/server`.
3. Положить секреты (`constants.py`, `constant_texts.py`, `config.php`). Не коммитить.
4. Python-venv в каталоге бота, `pip install -r requirements.txt`. Юнит supervisor смотрит на `/home/yourcast/yourcast/venv/bin/python` (см. `supervisor.conf`).
5. `cd admin/web && npm ci && npm run build` — `dist/` в git не хранится, собирается на сервере.
6. Подключить nginx (лендинг + сниппет админки). TLS как обычно (certbot).
7. Если PHP вызывает платёжные скрипты через sudo, в visudo должны быть NOPASSWD-строки на эти скрипты (исторически `www-data` → `scripts/payment/subscription_income.py`). Без этого Result URL Robokassa примет POST и тихо не зачислит.
8. Запустить юнит `yourcast` (`supervisorctl start yourcast`).
9. Проверки:
   - `curl -fsS https://wrkt.ru/api/health` → `{"ok":true,"role":"admin"}`
   - `curl -o /dev/null -w '%{http_code}\n' https://wrkt.ru/app/` → `200`
   - `curl -o /dev/null -w '%{http_code}\n' https://wrkt.ru/payment/crypto-bot/listener.php` → `200`
   - `curl -o /dev/null -w '%{http_code}\n' https://wrkt.ru/payment/robokassa/result.php` → `200`

Админка: `https://wrkt.ru/app/`. Логины те же, таблица `admins`.

## Обычный деплой бота

Пуш в `main` → GitHub Actions «Continous deployment»:

1. `git fetch` + `git reset --hard origin/main` (локальный мусор на сервере не блокирует выкладку)
2. `pip install -r requirements.txt`
3. сборка `admin/web`
4. `deploy/ensure_nginx_admin.py` и `nginx -t`
5. `supervisorctl restart yourcast`

Лендинг (`/home/yourcast/server`) этим воркфлоу **не** обновляется — его деплоят отдельно.

Секреты GitHub Actions (репозиторий бота): `SERVER_IP`, `SERVER_USERNAME`, `SERVER_PASSWORD`, `PROJECT_PATH` (= `/home/yourcast/yourcast`). Пароли бота и админки туда не кладутся.

## Платежи

| Способ | Как деньги приходят | URL / канал |
|---|---|---|
| Telegram Stars | апдейт `successful_payment` внутри бота | URL нет, всё в long polling |
| Patreon | джоба в `jobs` периодически опрашивает API | webhook не нужен |
| Crypto Pay (@CryptoBot) | HTTPS → PHP → `scripts/payment/cryptoBot.py` | `https://wrkt.ru/payment/crypto-bot/listener.php` |
| Robokassa | HTTPS → PHP → `scripts/payment/subscription_income.py` | Result URL: `https://wrkt.ru/payment/robokassa/result.php`. Success/Fail редиректят в `https://t.me/yourcastbot` |

Кнопка Robokassa в боте сейчас открыта только создателю (остальным закомментирована). Stars — основной живой канал.

Входящий HTTPS-вебхук — нормальный вход для Crypto/Robokassa. PHP-слой сейчас только прокладка: принимает POST и через `shell_exec` вызывает Python. Это работает, но долгосрочно правильнее принять вебхук тем же FastAPI на localhost (как админка), без argv и php-fpm. **Не трогайте этот путь, пока не собрались явно мигрировать оплату.**

В кабинете Crypto Pay / Robokassa URL-ы должны совпадать с таблицей выше. После смены домена или nginx проверьте, что `*.php` под `/payment/` по-прежнему уходит в php-fpm.
