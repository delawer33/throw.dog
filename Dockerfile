# syntax=docker/dockerfile:1

# ---------- build stage: собираем зависимости в изолированный venv ----------
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Только рантайм-зависимости. requirements-dev.txt в образ не попадает.
COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# ---------- runtime stage: только артефакты, без тулчейна ----------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_PORT=8000 \
    PATH="/opt/venv/bin:$PATH"

# Непривилегированный пользователь
RUN useradd --system --create-home --uid 10001 --shell /usr/sbin/nologin throwdog

COPY --from=builder /opt/venv /opt/venv

WORKDIR /srv
COPY app ./app

USER throwdog

# Документирующий EXPOSE; реальный порт берётся из APP_PORT.
EXPOSE 8000

# Команда запуска задаётся ЗДЕСЬ и только здесь (в compose command не дублируется).
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${APP_PORT:-8000}"]
