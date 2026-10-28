FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv/app
COPY requirements.txt .
RUN apt-get update \
    && apt-get install -y --no-install-recommends gosu \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY worker.py ./worker.py
COPY scripts ./scripts
COPY docker-entrypoint.sh ./docker-entrypoint.sh
RUN chmod 0755 /srv/app/docker-entrypoint.sh \
    && mkdir -p /var/lib/control \
    && chown -R 10001:10001 /srv/app
ENV CONTROL_DB_PATH=/var/lib/control/control.db
EXPOSE 8000
ENTRYPOINT ["/srv/app/docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
