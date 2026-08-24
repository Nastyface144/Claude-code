FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY freelance_bot ./freelance_bot
VOLUME ["/app/data"]
ENV DB_PATH=/app/data/freelance.db

CMD ["python", "-m", "freelance_bot", "run"]
