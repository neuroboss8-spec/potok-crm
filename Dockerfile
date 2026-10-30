FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 curl ca-certificates && rm -rf /var/lib/apt/lists/*
COPY requirements.lock ./
RUN pip install --requirement requirements.lock
COPY . .
RUN addgroup --system app && adduser --system --ingroup app app && mkdir -p /app/staticfiles && chown -R app:app /app
USER app
RUN DJANGO_DEBUG=0 DJANGO_SECRET_KEY=build-only-static-key-not-used-at-runtime-0123456789abcdefghijklmnop python manage.py collectstatic --noinput
EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "1", "--no-control-socket", "--access-logfile", "-", "--error-logfile", "-"]
