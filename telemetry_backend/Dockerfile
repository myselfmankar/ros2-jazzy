FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    DB_PATH=/data/local_robot.db

WORKDIR /app
COPY telemetry_backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY telemetry_backend/telemetry_backend /app/telemetry_backend
RUN mkdir -p /data
VOLUME ["/data"]
EXPOSE 8000
CMD ["uvicorn", "telemetry_backend.api:app", "--host", "0.0.0.0", "--port", "8000"]
