# Как развернуть Yourcast

- [Два дерева](#два-дерева)
- [Как связаны PHP и Python](#как-связаны-php-и-python)
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
| `/home/yourcast/server` | отдельный репозиторий лендинга | PHP: сайт `wrkt.ru` и HTTP-вход платёжных вебхуков |

Это не «бот на двух языках». Python — вся логика. PHP — лендинг плюс тонкий вход с публичного HTTPS, потому что Crypto Pay и Robokassa умеют только POST на URL. Процессы бота снаружи не торчат.

Секреты бота — `constants.py` и `constant_texts.py` (в git не кладутся, список полей в `how-to.txt`). У лендинга `config.php` — только два пути:

```php
$bot_path = '/home/yourcast/yourcast';
$site_path = '/home/yourcast/server';
```

SQLite — `db/yourcast.db`. Логи юнита: `/home/yourcast/out.log`, `/home/yourcast/err.log`. Платёжный лог: `log/payment.log`.

## Как связаны PHP и Python

Админка на PHP **больше не живёт**. Старые `/login.php` и `/pages/*` редиректят в `/app/`. PHP остался для лендинга и оплаты.

```
Crypto Pay / Robokassa
    │  HTTPS POST
    ▼
nginx (корень /home/yourcast/server)
    │  location ~ \.php$
    ▼
php-fpm 7.4 (www-data)
    │  payment/crypto-bot/listener.php
    │  или payment/robokassa/result.php
    │  читает config.php → $bot_path
    │  тело/GET + заголовки в base64
    ▼
shell_exec: cd $bot_path && venv/bin/python scripts/payment/…
    │  argv: путь бота + payload
    ▼
Python: проверка подписи, sqlite, сообщение в Telegram
```

Контракт скриптов (они в **этом** репозитории):

| Вебхук | PHP (репозиторий лендинга) | Python |
|---|---|---|
| Crypto Pay | `payment/crypto-bot/listener.php` | `scripts/payment/cryptoBot.py $bot_path $body_b64 $headers_b64` |
| Robokassa Result | `payment/robokassa/result.php` | `scripts/payment/subscription_income.py $get_b64 $bot_path` |
| Robokassa Success/Fail | `success.php` / `fail.php` | нет — редирект на `https://t.me/yourcastbot` |

PHP **не** импортирует бота и **не** ходит в sqlite. Он только принимает HTTP и запускает короткий Python через `proc_open` (без shell, без `testfile.txt`). Это не один из четырёх долгоживущих процессов. CD копирует актуальные `listener.php` / `result.php` из `deploy/payment/`.

На проде listener вызывает `venv/bin/python` **без sudo**. Пользователь php-fpm (`www-data`) должен уметь:

- запустить `/home/yourcast/yourcast/venv/bin/python`
- прочитать код бота и `constants.py`
- писать в `db/yourcast.db` и `log/payment.log`

В `/etc/sudoers` ещё висят NOPASSWD на `cryptoBot.py` и `send_message.py` — это старый путь, его лучше вычистить. Текущие `listener.php` / `result.php` sudo не вызывают.

Stars и Patreon через PHP **не** ходят. Stars — апдейт внутри процесса `bot`. Patreon — поллер в процессе `jobs`.

Долгосрочно вебхук логичнее принять FastAPI на localhost (как админка), без argv и php-fpm. **Не трогайте этот путь, пока не собрались явно мигрировать оплату.**

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

Сайт отдаёт `/home/yourcast/server`. PHP-FPM: `location ~ \.php$` → `unix:/run/php/php7.4-fpm.sock`.

Админка — сниппет `deploy/nginx-yourcast-admin.conf` (ставит `deploy/ensure_nginx_admin.py`):

- `/app/` — SPA (`admin/web/dist`)
- `/api/` — прокси на FastAPI
- `/login.php` и `/pages/*` → `/app/`

**Не** вешайте `location ^~ /payment/` без FastCGI: это перехватит вебхуки раньше PHP.

После правки: `nginx -t && systemctl reload nginx`.

## Первый запуск на чистой машине

1. Каталоги выше, Python 3.11+, Node 20+, nginx, php-fpm 7.4, supervisor.
2. Клонировать бот в `/home/yourcast/yourcast`, лендинг в `/home/yourcast/server`.
3. Положить секреты (`constants.py`, `constant_texts.py`, `config.php`). Не коммитить.
4. Venv в каталоге бота, `pip install -r requirements.txt`. Юнит смотрит на `/home/yourcast/yourcast/venv/bin/python` (`supervisor.conf`).
5. `cd admin/web && npm ci && npm run build` — `dist/` в git нет, собирается на сервере.
6. Nginx: корень лендинга + сниппет админки. TLS — certbot.
7. php-fpm user должен запускать venv python и писать sqlite/лог (см. [связку](#как-связаны-php-и-python)).
8. `supervisorctl start yourcast`.
9. Проверки:
   - `curl -fsS https://wrkt.ru/api/health` → `{"ok":true,"role":"admin"}`
   - `curl -o /dev/null -w '%{http_code}\n' https://wrkt.ru/app/` → `200`
   - `curl -o /dev/null -w '%{http_code}\n' -X POST https://wrkt.ru/payment/crypto-bot/listener.php` → не 5xx (мусорный POST без подписи = 400, это нормально)
   - `curl -o /dev/null -w '%{http_code}\n' https://wrkt.ru/payment/robokassa/result.php` → `200`

Логины админки — таблица `admins`.

## Обычный деплой бота

Пуш в `main` → GitHub Actions «Continous deployment»:

1. `git fetch` + `git reset --hard origin/main`
2. `pip install -r requirements.txt`
3. сборка `admin/web`
4. nginx-сниппет админки, `deploy/install_payment_php.py` (копирует hardened `listener.php` / `result.php` в дерево лендинга), `nginx -t`
5. `supervisorctl restart yourcast`

Лендинг целиком этим воркфлоу не обновляется — только платёжные PHP из `deploy/payment/`. Уберите из visudo `scripts/send_message.py`, если он ещё есть: старая PHP-админка больше не шлёт рассылку.

Секреты Actions: `SERVER_IP`, `SERVER_USERNAME`, `SERVER_PASSWORD`, `PROJECT_PATH` (= `/home/yourcast/yourcast`). Пароли бота и админки туда не кладутся.

## Платежи

| Способ | Как деньги приходят | URL / канал |
|---|---|---|
| Telegram Stars | апдейт `successful_payment` внутри `bot` | URL нет |
| Patreon | поллер в `jobs` | webhook не нужен |
| Crypto Pay | PHP → `scripts/payment/cryptoBot.py` | `https://wrkt.ru/payment/crypto-bot/listener.php` |
| Robokassa | PHP → `scripts/payment/subscription_income.py` | Result: `https://wrkt.ru/payment/robokassa/result.php` |

Кнопка Robokassa в боте открыта только создателю. Stars — основной живой канал.

В кабинетах Crypto Pay / Robokassa URL-ы должны совпадать с таблицей. После смены домена или nginx проверьте, что `*.php` под `/payment/` уходит в php-fpm.
