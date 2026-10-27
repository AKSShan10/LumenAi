FROM python:3.11-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app

# antiword reads old Word 97-2003 (.doc) CVs; it is a small program, not a Python package
RUN apt-get update && apt-get install -y --no-install-recommends antiword && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# F7 identity check: the two face models (37 MB, checked by SHA-256), downloaded once when the image is built
COPY scripts ./scripts
RUN python scripts/download_face_models.py

COPY app ./app
COPY alembic.ini .
COPY migrations ./migrations
COPY tests ./tests

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
