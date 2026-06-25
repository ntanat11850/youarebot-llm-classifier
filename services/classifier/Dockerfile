FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /service

RUN pip install --no-cache-dir \
    "fastapi[standard]>=0.115.11,<0.116.0" \
    "pydantic>=2.10.6,<3.0.0" \
    "uvicorn[standard]>=0.30.0,<0.35.0"

COPY main.py ./main.py
COPY champion_classifier.json ./champion_classifier.json

EXPOSE 8001

ENV APP_PORT=8001 \
    CHAMPION_MODEL_PATH=/service/champion_classifier.json

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${APP_PORT:-8001}"]
