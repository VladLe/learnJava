FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DJANGO_SETTINGS_MODULE=config.settings

WORKDIR /app

# System deps for trafilatura/lxml and psycopg build are covered by wheels;
# keep the image slim.
COPY pyproject.toml ./
COPY config ./config
COPY newsroom ./newsroom
COPY manage.py ./

RUN pip install --no-cache-dir -e ".[prod]"

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
