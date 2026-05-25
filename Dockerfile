FROM python:3.14-slim AS builder

WORKDIR /app

RUN pip install --no-cache-dir poetry

ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=1 \
    POETRY_VIRTUALENVS_CREATE=1 \
    POETRY_CACHE_DIR=/tmp/poetry_cache

COPY pyproject.toml ./
RUN poetry install --without dev --no-root --no-interaction && rm -rf $POETRY_CACHE_DIR

COPY src ./src
RUN poetry install --without dev

FROM python:3.14-slim AS runtime

WORKDIR /app

ENV PATH=/app/.venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src

# Create a non-root user
RUN useradd -m -u 1000 logintel && chown -R logintel:logintel /app
USER logintel

ENTRYPOINT ["python", "-m", "logintel"]
CMD ["--config", "/etc/logintel/.logintelrc.yaml"]
