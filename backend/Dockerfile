# syntax=docker/dockerfile:1.6
#
# Dev-образ backend'а. В prod (задача 6.2) заменится на multi-stage build
# с non-root user и gunicorn вместо uvicorn --reload.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Системные зависимости: curl — для Docker healthcheck
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Python-зависимости (отдельным слоем — ускоряет rebuild при изменении кода).
# BuildKit cache mount для pip cache между сборками.
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip \
    && pip install -r requirements.txt

# Код приложения. В dev-compose перекрывается bind mount'ом из ../backend:/app
COPY . .

EXPOSE 8000

# Dev-команда с hot reload. В prod: gunicorn -k uvicorn.workers.UvicornWorker
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
