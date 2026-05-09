FROM node:22-alpine AS web-build
WORKDIR /app/web
COPY web/package*.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.13-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src \
    JOBRADAR_WEB_HOST=0.0.0.0 \
    JOBRADAR_WEB_PORT=8765
WORKDIR /app

RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home-dir /app --shell /usr/sbin/nologin app
COPY pyproject.toml README.md ./
COPY config/ ./config/
COPY src/ ./src/
COPY --from=web-build /app/web/dist ./web/dist
RUN mkdir -p /app/runs/latest /app/runs/history /app/runs/state /app/runs/cv /tmp/jobradai \
    && chown -R app:app /app/runs /tmp/jobradai

USER app
EXPOSE 8765
CMD ["python", "-m", "jobradai", "web", "--host", "0.0.0.0", "--port", "8765"]
