# Plain Python 3.11 image (aiogram 2.x pins aiohttp<3.9, which has no wheels for Python 3.12+).
# Chromium and its system libraries are installed below via `playwright install --with-deps`.
FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DATABASE_URL=sqlite+aiosqlite:////data/finance.db

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Needs apt and root: installs Chromium plus the system libraries it depends on.
# The apt lists are removed in the same layer to keep the image small.
RUN python -m playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*

COPY . .

# The SQLite file lives on a Railway Volume mounted at /data.
# The container runs as root on purpose: Railway mounts volumes owned by root, so a non-root
# user could not write to /data. Chromium is launched by the code without relying on a user sandbox.
RUN mkdir -p /data

CMD ["python", "app.py"]
