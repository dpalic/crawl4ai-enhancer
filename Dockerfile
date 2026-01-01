FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DATA_DIR=/data
ENV DB_URL=sqlite:////data/app.db

WORKDIR /app

RUN adduser --disabled-password --gecos "" appuser     && mkdir -p /data     && chown appuser:appuser /data

COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip     && pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY .env.example ./.env.example
COPY data/.gitkeep ./data/.gitkeep

VOLUME ["/data"]

USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
