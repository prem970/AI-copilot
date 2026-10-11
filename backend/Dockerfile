FROM python:3.11-slim AS base
WORKDIR /app
COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY backend /app/backend
ENV PYTHONPATH=/app/backend
RUN useradd --uid 10001 --create-home health && mkdir -p /data/storage && chown -R health:health /data
USER health
EXPOSE 8000
CMD ["sh", "-c", "alembic -c backend/alembic.ini upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]

