# syntax=docker/dockerfile:1.7
# One image, two targets: `dev` (source bind-mounted, dev tools) and `prod`.

FROM python:3.13-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"
COPY --from=ghcr.io/astral-sh/uv:0.11.27 /uv /uvx /bin/
WORKDIR /app

# Runtime dependencies only (cached layer: changes only with the lockfile).
FROM base AS deps
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# Development: add dev tools; the source is bind-mounted at /app by compose.
FROM deps AS dev
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]

# Production: copy the source, collect static files, drop root.
FROM deps AS prod
COPY . .
RUN DJANGO_SETTINGS_MODULE=config.settings.prod \
    DJANGO_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(64))')" \
    python manage.py collectstatic --noinput \
 && useradd --system --uid 10001 --no-create-home app \
 && chown -R app /app
USER app
EXPOSE 8000
CMD ["gunicorn", "config.wsgi", "-b", "0.0.0.0:8000", "-w", "3", "--timeout", "30"]
