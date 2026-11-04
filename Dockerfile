# Playwright's official image ships Chromium and all its system libraries.
# Keep the tag in sync with the playwright version in requirements.txt (~=1.64).
FROM mcr.microsoft.com/playwright/python:v1.64.1-noble

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DATABASE_URL=sqlite+aiosqlite:////data/finance.db

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# The SQLite file lives on a Railway Volume mounted at /data.
# The container runs as root on purpose: Railway mounts volumes owned by root, so a non-root
# user could not write to /data. Chromium is launched by the code without relying on a user sandbox.
RUN mkdir -p /data

CMD ["python", "app.py"]
