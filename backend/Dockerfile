FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PROMETHEUS_DISABLE_CREATED_SERIES=True

WORKDIR /app

COPY requirements.txt .
# pip, setuptools and wheel are only needed to install dependencies. Removing them afterwards
# drops their vendored libraries (urllib3, msgpack, ...) that Trivy flags with HIGH CVEs.
RUN pip install -r requirements.txt \
    && pip uninstall -y pip setuptools wheel \
    && rm -rf /usr/local/lib/python3.12/ensurepip \
    && useradd --create-home --uid 10001 appuser

COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app

# Run as an unprivileged user, never as root.
USER 10001
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"

# Apply pending migrations, then start the API.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers"]
