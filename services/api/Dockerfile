# Used by Docker Compose (infrastructure/docker-compose.yml). Render builds from source instead.
FROM python:3.13-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install .
COPY alembic.ini start.sh ./
COPY migrations ./migrations
RUN useradd --system --no-create-home detour
USER detour
EXPOSE 8000
CMD ["sh", "start.sh"]
