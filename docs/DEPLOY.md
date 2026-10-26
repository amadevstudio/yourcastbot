# Как развернуть Yourcast

- [Два дерева](#два-дерева)
- [Как связаны вебхуки оплаты и Python](#как-связаны-вебхуки-оплаты-и-python)
- [Процессы бота](#процессы-бота)
- [Nginx](#nginx)
- [Первый запуск](#первый-запуск-на-чистой-машине)
- [Обычный деплой](#обычный-деплой-бота)
- [Платежи](#платежи)

Публичный сайт — `https://wrkt.ru`. Админка — `https://wrkt.ru/app/`. Бот слушает Telegram long polling, наружу его порт не открывается.

## Два дерева

| Путь | Репозиторий | Зачем |
|---|---|---|
| `/home/yourcast/yourcast` | **этот** репозиторий | Python: Telegram-бот, апдейтер, джобы, админка |
| `/home/yourcast/server` | отдельный репозиторий лендинга | статика сайта `wrkt.ru` (PHP-файлы там больше не исполняются) |

Python — вся логика. Лендинг — статика; вебхуки оплаты принимает процесс `admin` за nginx (см. ниже). Остальные процессы бота снаружи не торчат.

Секреты бота — `constants.py` и `constant_texts.py` (в git не кладутся, список полей в `how-to.txt`). У лендинга `config.php` — только два пути:

```php
$bot_path = '/home/yourcast/yourcast';
$site_path = '/home/yourcast/server';
```

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

Stars и Patreon через вебхуки **не** ходят. Stars — апдейт внутри процесса `bot`. Patreon — поллер в процессе `jobs`.

## Процессы бота

Один supervisor-юнит `yourcast` запускает `python main.py`. Этот процесс — родитель, он поднимает детей:

| Роль | Что делает |
|---|---|
| `bot` | входящие апдейты Telegram |
| `updater` | круги RSS / rec |
| `jobs` | Patreon, бэкапы, **очередь рассылок админки** (поток, не пятый процесс) |
| `admin` | FastAPI на `127.0.0.1:8765` — API и SPA `/app/` |

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

1. Каталоги выше, Python 3.11+, Node 20+, nginx, supervisor (php-fpm не нужен).
2. Клонировать бот в `/home/yourcast/yourcast`, лендинг в `/home/yourcast/server`.
3. Положить секреты (`constants.py`, `constant_texts.py`, `config.php`). Не коммитить.
4. Venv в каталоге бота, `pip install -r requirements.txt`. Юнит смотрит на `/home/yourcast/yourcast/venv/bin/python` (`supervisor.conf`).
5. `cd admin/web && npm ci && npm run build` — `dist/` в git нет, собирается на сервере.
6. Nginx: корень лендинга + сниппет админки. TLS — certbot.
7. Nginx: сниппет вебхуков `deploy/nginx-yourcast-php.conf` + `deploy/ensure_nginx_php.py` (см. [связку](#как-связаны-вебхуки-оплаты-и-python)).
8. `supervisorctl start yourcast`.
9. Проверки:
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

Лендинг этим воркфлоу не обновляется. Уберите из visudo `scripts/send_message.py`, если он ещё есть: старая PHP-админка больше не шлёт рассылку.

Секреты Actions: `SERVER_IP`, `SERVER_USERNAME`, `SERVER_SSH_KEY` (приватный ключ, публичная часть — в `authorized_keys` пользователя деплоя), `PROJECT_PATH` (= `/home/yourcast/yourcast`). Парольного входа по SSH нет (`PasswordAuthentication no`), пароли бота и админки в Actions не кладутся.

## Платежи

| Способ | Как деньги приходят | URL / канал |
|---|---|---|
| Telegram Stars | апдейт `successful_payment` внутри `bot` | URL нет |
| Patreon | поллер в `jobs` | webhook не нужен |
| Crypto Pay | admin → `scripts/payment/cryptoBot.py` | `https://wrkt.ru/payment/crypto-bot/listener.php` |
| Robokassa | admin → `scripts/payment/subscription_income.py` | Result: `https://wrkt.ru/payment/robokassa/result.php` |

Кнопка Robokassa в боте открыта только создателю. Stars — основной живой канал.

В кабинетах Crypto Pay / Robokassa URL-ы должны совпадать с таблицей. После смены домена или nginx проверьте, что эти два адреса уходят в `admin` (127.0.0.1:8765), а не в php-fpm.
