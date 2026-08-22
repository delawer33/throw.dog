#!/usr/bin/env bash
#
# throw.dog — деплой одной командой с ноутбука.
#
#   ./deploy.sh
#   DEPLOY_HOST=user@1.2.3.4 DEPLOY_DIR=/opt/throwdog ./deploy.sh
#
# Идемпотентен: гоняй сколько угодно раз. Реальный .env и сертификаты
# живут на сервере и никогда не перезаписываются.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

# ---------------------------------------------------------------------------
# Настройки
# ---------------------------------------------------------------------------

# Значения из локального .env (если он есть) — как дефолты, env-переменные
# из окружения имеют приоритет. Парсим только нужные ключи, .env не сорсим.
read_local_env() {
	local key="$1" file="${SCRIPT_DIR}/.env"
	[ -f "$file" ] || return 0
	sed -n "s/^[[:space:]]*${key}[[:space:]]*=[[:space:]]*//p" "$file" |
		tail -n 1 | tr -d "\"'" | tr -d '\r'
}

DEPLOY_HOST="${DEPLOY_HOST:-$(read_local_env DEPLOY_HOST)}"
DEPLOY_HOST="${DEPLOY_HOST:-throwdog}"

DEPLOY_DIR="${DEPLOY_DIR:-$(read_local_env DEPLOY_DIR)}"
DEPLOY_DIR="${DEPLOY_DIR:-/opt/throwdog}"

APP_CONTAINER="${APP_CONTAINER:-throwdog_app}"

# Сколько ждём зелёного healthcheck: HEALTH_RETRIES попыток по HEALTH_DELAY сек.
HEALTH_RETRIES="${HEALTH_RETRIES:-30}"
HEALTH_DELAY="${HEALTH_DELAY:-5}"

SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=10)

# ---------------------------------------------------------------------------
# Вывод
# ---------------------------------------------------------------------------

step() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
info() { printf '    %s\n' "$*"; }
fail() {
	printf '\n\033[1;31mОШИБКА: %s\033[0m\n' "$*" >&2
	exit 1
}

# Команды собираем локально (подставляя $DEPLOY_DIR) и выполняем на сервере —
# это намеренно, поэтому глушим SC2029.
# shellcheck disable=SC2029
remote() { ssh "${SSH_OPTS[@]}" "$DEPLOY_HOST" "$@"; }

# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------

step "Preflight"

for tool in rsync ssh; do
	command -v "$tool" >/dev/null 2>&1 ||
		fail "локально не установлен '$tool'. Поставь его: sudo apt install $tool"
done

info "хост:    $DEPLOY_HOST"
info "каталог: $DEPLOY_DIR"

if ! remote true 2>/dev/null; then
	fail "не могу подключиться по ssh к '$DEPLOY_HOST'.
      Проверь блок 'Host throwdog' в ~/.ssh/config и доступность сервера
      (см. раздел «Первичная настройка» в README.md)."
fi
info "ssh: ок"

if ! remote "command -v docker >/dev/null 2>&1"; then
	fail "на сервере нет docker. Установи его (см. README.md, первичная настройка)."
fi
info "docker на сервере: ок"

if ! remote "test -f '$DEPLOY_DIR/.env'"; then
	fail "на сервере нет '$DEPLOY_DIR/.env'.
      Создай его из .env.example — скрипт его намеренно не перезаписывает:
      scp .env.example $DEPLOY_HOST:$DEPLOY_DIR/.env && ssh $DEPLOY_HOST 'nano $DEPLOY_DIR/.env'"
fi
info ".env на сервере: ок"

if ! remote "test -f '$DEPLOY_DIR/certs/origin.pem' && test -f '$DEPLOY_DIR/certs/origin.key'"; then
	fail "на сервере нет сертификата Cloudflare Origin CA.
      Ожидаются файлы '$DEPLOY_DIR/certs/origin.pem' и '$DEPLOY_DIR/certs/origin.key' (chmod 600).
      Без них Caddy не поднимется, а Full (strict) не заработает (см. README.md)."
fi
info "сертификаты на сервере: ок"

# ---------------------------------------------------------------------------
# Синхронизация исходников
# ---------------------------------------------------------------------------

step "Синхронизация исходников на $DEPLOY_HOST:$DEPLOY_DIR"

remote "mkdir -p '$DEPLOY_DIR'"

# --delete не трогает исключённое, поэтому .env и certs/ на сервере целы.
rsync -az --delete --human-readable \
	--exclude '.git/' \
	--exclude '.venv/' \
	--exclude 'venv/' \
	--exclude 'certs/' \
	--exclude '.env' \
	--exclude '__pycache__/' \
	--exclude '*.pyc' \
	--exclude '.pytest_cache/' \
	--exclude '.mypy_cache/' \
	--exclude '.ruff_cache/' \
	--exclude 'tests/' \
	--exclude '*.log' \
	--exclude '.DS_Store' \
	-e "ssh ${SSH_OPTS[*]}" \
	"${SCRIPT_DIR}/" "${DEPLOY_HOST}:${DEPLOY_DIR}/"

info "rsync: ок"

# ---------------------------------------------------------------------------
# Сборка и запуск
# ---------------------------------------------------------------------------

step "docker compose up -d --build"

remote "cd '$DEPLOY_DIR' && docker compose up -d --build"

step "Состояние контейнеров"

remote "cd '$DEPLOY_DIR' && docker compose ps"

# ---------------------------------------------------------------------------
# Ждём зелёный healthcheck приложения
# ---------------------------------------------------------------------------

step "Ждём healthcheck приложения ($APP_CONTAINER)"

attempt=1
while [ "$attempt" -le "$HEALTH_RETRIES" ]; do
	status="$(remote "docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' '$APP_CONTAINER' 2>/dev/null" || true)"
	status="$(printf '%s' "$status" | tr -d '[:space:]')"

	case "$status" in
	healthy)
		info "healthcheck: healthy (попытка $attempt)"
		step "Готово. Деплой завершён."
		exit 0
		;;
	unhealthy)
		printf '\n'
		remote "cd '$DEPLOY_DIR' && docker compose logs --tail 50 app" || true
		fail "контейнер '$APP_CONTAINER' в состоянии unhealthy (см. лог выше)."
		;;
	none)
		fail "у контейнера '$APP_CONTAINER' нет healthcheck или контейнер не запущен."
		;;
	*)
		info "healthcheck: ${status:-неизвестно} (попытка $attempt/$HEALTH_RETRIES), ждём ${HEALTH_DELAY}с"
		sleep "$HEALTH_DELAY"
		;;
	esac
	attempt=$((attempt + 1))
done

printf '\n'
remote "cd '$DEPLOY_DIR' && docker compose logs --tail 50 app" || true
fail "healthcheck не позеленел за $((HEALTH_RETRIES * HEALTH_DELAY))с. Смотри лог выше."
