FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /service

RUN pip install --no-cache-dir \
    "asyncpg>=0.29.0,<0.31.0" \
    "fastapi[standard]>=0.115.11,<0.116.0" \
    "httpx>=0.27.0,<0.29.0" \
    "pydantic>=2.10.6,<3.0.0" \
    "uvicorn[standard]>=0.30.0,<0.35.0"

COPY main.py ./main.py

EXPOSE 8000

ENV APP_PORT=8000

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${APP_PORT:-8000}"]
