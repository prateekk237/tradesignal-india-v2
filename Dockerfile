# ══════════════════════════════════════════════════════
#  STAGE 1: Build React Frontend
# ══════════════════════════════════════════════════════
FROM node:20-alpine AS frontend-build
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

# ══════════════════════════════════════════════════════
#  STAGE 2: Python Backend + Serve Frontend Static Files
# ══════════════════════════════════════════════════════
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

# Copy built frontend into /app/static
COPY --from=frontend-build /frontend/dist ./static

ENV PORT=8080
EXPOSE ${PORT}

CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
