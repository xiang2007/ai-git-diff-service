FROM python:3.14-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY src ./src

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "src.backend:app", "--host", "0.0.0.0", "--port", "8000"]