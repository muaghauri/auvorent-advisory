FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt "psycopg[binary]>=3.2,<4"
COPY alembic.ini ./
COPY backend ./backend
COPY frontend ./frontend
COPY seed ./seed
RUN mkdir -p /data/media /data/publishing && adduser --system --group --disabled-password auvorent && chown -R auvorent:auvorent /app /data
USER auvorent
EXPOSE 8900
# Run schema migrations as a separate release job, NOT concurrently on all replicas.
CMD ["uvicorn","backend.app.main:app","--host","0.0.0.0","--port","8900","--proxy-headers","--forwarded-allow-ips","127.0.0.1"]
