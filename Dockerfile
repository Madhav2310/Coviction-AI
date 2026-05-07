FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY api/requirements.txt /app/api/requirements.txt
RUN pip install --no-cache-dir -r /app/api/requirements.txt

COPY api /app/api
COPY static /app/static
COPY uploads /app/uploads

EXPOSE 8000

CMD ["sh", "-c", "cd /app/api && uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
