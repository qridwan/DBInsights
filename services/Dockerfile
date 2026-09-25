# DBInsight collector service (FastAPI). Build context: services/.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app
COPY pyproject.toml .python-version ./
RUN uv sync --no-dev --no-install-project

COPY analyzers analyzers
COPY api api

EXPOSE 8700
CMD ["uv", "run", "--no-dev", "uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "8700"]
