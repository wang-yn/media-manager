FROM node:24-alpine AS frontend
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

FROM python:3.13-alpine
WORKDIR /app
ENV PYTHONPATH=/app/backend/src
ENV MEDIA_MANAGER_STATIC_DIR=/app/static
COPY backend/ ./backend/
COPY config/ ./config/
RUN pip install --no-cache-dir ./backend
COPY --from=frontend /app/frontend/dist ./static
EXPOSE 8000
CMD ["python", "-m", "media_manager.server"]
