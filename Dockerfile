FROM node:18-alpine AS frontend-build

# Build frontend
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# Production stage
FROM python:3.11-slim

WORKDIR /app

# Create a non-root user
RUN useradd -m -u 1000 appuser

# Install Redis and supervisor
RUN apt-get update && apt-get install -y \
    redis-server \
    supervisor \
    && rm -rf /var/lib/apt/lists/*

# Install backend dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY backend/ ./

# Copy built frontend files to be served by FastAPI
COPY --from=frontend-build /frontend/dist ./static

# Create a modified main.py that serves the frontend
RUN echo 'from fastapi.staticfiles import StaticFiles' >> serve_all.py && \
    echo 'from fastapi.responses import FileResponse' >> serve_all.py && \
    echo 'from pathlib import Path' >> serve_all.py && \
    echo 'import os' >> serve_all.py && \
    echo '' >> serve_all.py && \
    cat main.py >> serve_all.py && \
    echo '' >> serve_all.py && \
    echo '# Serve static assets (JS, CSS, etc)' >> serve_all.py && \
    echo 'app.mount("/assets", StaticFiles(directory="static/assets"), name="assets")' >> serve_all.py && \
    echo '' >> serve_all.py && \
    echo '# Catch-all route for SPA - must be after all other routes' >> serve_all.py && \
    echo '@app.get("/{full_path:path}")' >> serve_all.py && \
    echo 'async def serve_spa(full_path: str):' >> serve_all.py && \
    echo '    # Serve index.html for all unmatched routes (SPA routing)' >> serve_all.py && \
    echo '    return FileResponse("static/index.html")' >> serve_all.py

# Create Redis config to bind only to localhost
RUN echo 'bind 127.0.0.1' > /etc/redis/redis.conf && \
    echo 'protected-mode yes' >> /etc/redis/redis.conf && \
    echo 'port 6379' >> /etc/redis/redis.conf && \
    echo 'appendonly yes' >> /etc/redis/redis.conf && \
    echo 'requirepass ${REDIS_PASSWORD:-defaultpassword123}' >> /etc/redis/redis.conf

# Create supervisor config with proper user
RUN echo '[supervisord]' > /etc/supervisor/conf.d/supervisord.conf && \
    echo 'nodaemon=true' >> /etc/supervisor/conf.d/supervisord.conf && \
    echo 'user=appuser' >> /etc/supervisor/conf.d/supervisord.conf && \
    echo '' >> /etc/supervisor/conf.d/supervisord.conf && \
    echo '[program:redis]' >> /etc/supervisor/conf.d/supervisord.conf && \
    echo 'command=redis-server /etc/redis/redis.conf' >> /etc/supervisor/conf.d/supervisord.conf && \
    echo 'user=appuser' >> /etc/supervisor/conf.d/supervisord.conf && \
    echo 'autorestart=true' >> /etc/supervisor/conf.d/supervisord.conf && \
    echo 'stdout_logfile=/dev/stdout' >> /etc/supervisor/conf.d/supervisord.conf && \
    echo 'stdout_logfile_maxbytes=0' >> /etc/supervisor/conf.d/supervisord.conf && \
    echo 'stderr_logfile=/dev/stderr' >> /etc/supervisor/conf.d/supervisord.conf && \
    echo 'stderr_logfile_maxbytes=0' >> /etc/supervisor/conf.d/supervisord.conf && \
    echo '' >> /etc/supervisor/conf.d/supervisord.conf && \
    echo '[program:app]' >> /etc/supervisor/conf.d/supervisord.conf && \
    echo 'command=uvicorn serve_all:app --host 0.0.0.0 --port 8000' >> /etc/supervisor/conf.d/supervisord.conf && \
    echo 'user=appuser' >> /etc/supervisor/conf.d/supervisord.conf && \
    echo 'autorestart=true' >> /etc/supervisor/conf.d/supervisord.conf && \
    echo 'stdout_logfile=/dev/stdout' >> /etc/supervisor/conf.d/supervisord.conf && \
    echo 'stdout_logfile_maxbytes=0' >> /etc/supervisor/conf.d/supervisord.conf && \
    echo 'stderr_logfile=/dev/stderr' >> /etc/supervisor/conf.d/supervisord.conf && \
    echo 'stderr_logfile_maxbytes=0' >> /etc/supervisor/conf.d/supervisord.conf

# Create necessary directories and set permissions
RUN mkdir -p /var/run/supervisor /var/log/supervisor && \
    chown -R appuser:appuser /app /var/run/supervisor /var/log/supervisor /etc/redis

# Only expose the application port, NOT Redis
EXPOSE 8000

# Switch to non-root user
USER appuser

CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]