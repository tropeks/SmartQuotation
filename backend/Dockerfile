FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# WeasyPrint (PDF proposals) + python-magic system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libpangoft2-1.0-0 \
    libgdk-pixbuf-xlib-2.0-0 \
    libffi-dev \
    shared-mime-info \
    libmagic1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements/ requirements/
RUN pip install --no-cache-dir -r requirements/base.txt

COPY backend/ .
# pricing_engine is a pure-Python lib at the repo ROOT (sibling of backend/), not
# inside backend/. settings/base.py adds /app to sys.path and imports it, so it MUST
# be in the image at /app/pricing_engine — `COPY backend/ .` alone left it out and
# `manage.py check` died with ModuleNotFoundError: No module named 'pricing_engine'.
COPY pricing_engine/ ./pricing_engine/

# Prod entrypoint: migrate_schemas (shared+tenant) + collectstatic, then exec CMD.
RUN chmod +x /app/entrypoint.sh

# Roda como usuário não-root. collectstatic (STATIC_ROOT=/app/staticfiles) e a
# geração de propostas (MEDIA_ROOT=/app/backend/media) escrevem em runtime, então
# esses diretórios precisam pertencer ao appuser.
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/staticfiles /app/backend/media \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health/ || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["gunicorn", "smartquotation.wsgi:application", "--bind", "0.0.0.0:8000", "--workers=4", "--timeout=60"]
