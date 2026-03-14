# Multi-stage build: frontend + backend
FROM node:22-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS runtime
WORKDIR /app

# Install backend dependencies
COPY backend/pyproject.toml backend/
RUN pip install --no-cache-dir -e backend/

# Copy backend source
COPY backend/app/ backend/app/

# Copy built frontend
COPY --from=frontend-build /app/frontend/dist/ frontend/dist/

# Expose port
EXPOSE 8000

# Default environment
ENV KANFEI_SERIAL_PORT=/dev/ttyUSB0
ENV KANFEI_BAUD_RATE=19200
ENV KANFEI_DB_PATH=/app/data/weather.db

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--app-dir", "backend"]
