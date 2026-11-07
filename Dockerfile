FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install dependencies first so Docker caches this layer.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

EXPOSE 8000
# Default: serve the API. docker-compose overrides this for the ingestion job.
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
