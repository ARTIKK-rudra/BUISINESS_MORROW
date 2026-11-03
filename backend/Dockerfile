FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr && rm -rf /var/lib/apt/lists/*
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /service
COPY pyproject.toml ./
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./alembic.ini
RUN pip install --no-cache-dir .
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /service/var/models \
    && chown -R appuser:appuser /service
USER 10001:10001
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
