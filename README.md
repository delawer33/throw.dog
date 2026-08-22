# throw.dog

Мгновенная передача текста между устройствами через браузер.

Боевой контур:

```
браузер → Cloudflare (proxy, Full (strict)) → VPS → Caddy (TLS, Origin CA) → приложение (uvicorn)
```

Между Cloudflare и VPS открытого HTTP нет: TLS терминируется на Caddy сертификатом
Cloudflare Origin CA. Режим **Flexible недопустим** — через сервис ходят пароли.

---

## Промежуточный режим: домена ещё нет

Пока `throw.dog` не куплен, сервис живёт на временном имени вида
`<ip-с-точками>.sslip.io` — это бесплатный wildcard-DNS, который резолвится в тот
самый IP, никакой регистрации не нужно. Сертификат при этом настоящий, от Let's
Encrypt: Caddy получает его сам по ACME (нужен открытый порт 80). Самоподписанный
сертификат для этого не годится — предупреждение браузера «соединение
небезопасно» крадёт секунды и ломает замер ворот этапа 0.

В `.env` на сервере:

```env
SITE_DOMAIN=94.241.172.33.sslip.io
CADDYFILE=./Caddyfile.acme
```

Дальше как обычно — `./deploy.sh`. Проверить: `curl https://94.241.172.33.sslip.io/healthz`
(без `-k`: сертификат должен проходить проверку сам).

Когда домен куплен и заведён в Cloudflare — пройти шаги ниже и вернуть в `.env`
`SITE_DOMAIN=throw.dog` и `CADDYFILE=./Caddyfile`.

> Замер ворот в этом режиме занижает результат: набирать
> `94.241.172.33.sslip.io/red-fox` руками дольше, чем `throw.dog/red-fox`.
> Транспортную часть смотри по серверному логу (`created` → `read`), а
> человеческую перемеряй уже на домене.

---

## Первичная настройка (ручные шаги)

> **HITL — делает человек, один раз.** Автоматизировать это в прототипе не нужно:
> шаги требуют аккаунтов, оплаты и кликов в чужих панелях.
> Пока они не сделаны, `./deploy.sh` намеренно падает с внятной ошибкой.

### 1. Арендовать VPS

Timeweb Cloud, локация в ЕС, минимальный тариф (1–2 vCPU / 2 GB). ОС — Ubuntu 24.04 LTS.
Записать выданный публичный IP.

### 2. Установить Docker на VPS

Зайти на сервер по IP и выполнить:

```bash
curl -fsSL https://get.docker.com | sh
sudo systemctl enable --now docker
sudo mkdir -p /opt/throwdog
```

`systemctl enable` — то, из-за чего контейнеры поднимутся сами после перезагрузки VPS
(вместе с `restart: unless-stopped` в compose).

### 3. Прописать ssh-хост на ноутбуке

Ключ `~/.ssh/throwdog_ed25519` уже есть, записи `Host` в `~/.ssh/config` — нет.
Добавить в `~/.ssh/config` (подставить реальный IP):

```sshconfig
Host throwdog
    HostName 203.0.113.10
    User root
    IdentityFile ~/.ssh/throwdog_ed25519
    IdentitiesOnly yes
    ServerAliveInterval 30
```

Проверить: `ssh throwdog true` должно отработать молча и без пароля.

### 4. Перевести домен на Cloudflare

1. В Cloudflare добавить сайт `throw.dog`, получить два NS-сервера.
2. У регистратора домена заменить NS-серверы на выданные Cloudflare. Ждать делегирования
   (обычно минуты, иногда до суток).
3. В Cloudflare → **DNS** создать запись:
   - Type `A`, Name `@`, Content — IP VPS, **Proxy status: Proxied (оранжевое облако)**.
   - При желании такую же запись `A` для `www`.

### 5. SSL/TLS = Full (strict)

Cloudflare → **SSL/TLS → Overview** → режим **Full (strict)**.
Дополнительно в **SSL/TLS → Edge Certificates** включить **Always Use HTTPS**.

### 6. Выпустить сертификат Cloudflare Origin CA

Cloudflare → **SSL/TLS → Origin Server → Create Certificate**:

- тип ключа RSA (или ECDSA), hostnames: `throw.dog`, `*.throw.dog`, срок 15 лет;
- Cloudflare один раз покажет **сертификат** и **приватный ключ** — скопировать оба.

Положить их на сервер (не в git!):

```bash
ssh throwdog 'mkdir -p /opt/throwdog/certs && chmod 700 /opt/throwdog/certs'

# вставить содержимое сертификата, закончить Ctrl-D
ssh throwdog 'cat > /opt/throwdog/certs/origin.pem'

# вставить содержимое приватного ключа, закончить Ctrl-D
ssh throwdog 'cat > /opt/throwdog/certs/origin.key'

ssh throwdog 'chmod 600 /opt/throwdog/certs/origin.pem /opt/throwdog/certs/origin.key'
```

`certs/` и `*.pem`/`*.key` в `.gitignore` — в репозиторий они не попадут.

### 7. Создать `.env` на сервере

```bash
scp .env.example throwdog:/opt/throwdog/.env
ssh throwdog 'nano /opt/throwdog/.env'   # проставить SITE_DOMAIN и параметры броска
```

`deploy.sh` этот файл не перезаписывает — он живёт на сервере.

---

## Повседневный деплой

Одна команда с ноутбука:

```bash
./deploy.sh
```

Скрипт проверит окружение, зальёт исходники по rsync, сделает
`docker compose up -d --build`, покажет `docker compose ps` и дождётся зелёного
healthcheck приложения. Идемпотентен — гонять можно сколько угодно раз.

Переопределить цель разово:

```bash
DEPLOY_HOST=user@203.0.113.10 DEPLOY_DIR=/opt/throwdog ./deploy.sh
```

---

## Локальный запуск для разработки

Вариант без TLS и Caddy — просто приложение:

```bash
cp .env.example .env
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Открыть http://127.0.0.1:8000

Поднять весь контур локально (Caddy будет ругаться на отсутствие сертификатов,
пока не положишь свои в `./certs/`):

```bash
cp .env.example .env
docker compose up --build
```

Проверить конфигурацию compose, ничего не запуская:

```bash
docker compose config -q
```

---

## Событийный лог

Приложение пишет события в stdout (`PYTHONUNBUFFERED=1`), поэтому всё видно через docker:

```bash
# на сервере
ssh throwdog 'cd /opt/throwdog && docker compose logs -f app'

# только Caddy (access-логи)
ssh throwdog 'cd /opt/throwdog && docker compose logs -f caddy'

# оба сервиса, последние 100 строк
ssh throwdog 'cd /opt/throwdog && docker compose logs --tail 100'
```

---

## Что где лежит

| Файл                 | Зачем                                                        |
| -------------------- | ------------------------------------------------------------ |
| `Dockerfile`         | multi-stage образ приложения, запуск uvicorn                 |
| `docker-compose.yml` | два сервиса: `app` (внутрь сети) и `caddy` (80/443 наружу)   |
| `Caddyfile`          | TLS через Origin CA + reverse proxy на `app`                 |
| `.env.example`       | шаблон конфигурации; реальный `.env` только на сервере       |
| `deploy.sh`          | деплой одной командой с ноутбука                             |

Секреты (`.env`) и сертификаты (`certs/`) в git не попадают никогда.
