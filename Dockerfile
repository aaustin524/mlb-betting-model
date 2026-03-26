FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=10000 \
    REFLEX_ENV=prod

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    nginx \
    gettext-base \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

RUN chmod +x /app/deploy/render/start.sh \
    && mkdir -p /var/data/history /var/cache/nginx /var/log/nginx /etc/nginx/templates

COPY deploy/render/nginx.conf.template /etc/nginx/templates/default.conf.template

EXPOSE 10000

CMD ["/app/deploy/render/start.sh"]
