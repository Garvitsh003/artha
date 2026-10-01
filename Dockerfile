FROM node:24-alpine AS frontend
WORKDIR /app
COPY package.json pnpm-lock.yaml .npmrc ./
RUN corepack enable && corepack prepare pnpm@11.25.0 --activate && pnpm install --frozen-lockfile
COPY . .
RUN pnpm run build:web

FROM python:3.13-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DATA_DIR=/data APP_ENV=production COOKIE_SECURE=1
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home artha && mkdir /data && chown artha:artha /data
COPY --chown=artha:artha backend ./backend
COPY --chown=artha:artha scripts/reset-password.py scripts/generate-secrets.py ./scripts/
COPY --from=frontend --chown=artha:artha /app/dist-web ./dist-web
USER artha
EXPOSE 5000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request,os; urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:5000/health',headers={'Host':os.environ.get('TRUSTED_HOSTS','localhost').split(',')[0]}))" || exit 1
CMD ["gunicorn","--bind","0.0.0.0:5000","--workers","2","--threads","2","--timeout","60","backend.app:app"]
