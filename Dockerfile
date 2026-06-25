FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN pip install --no-cache-dir \
    "torch==2.2.2" \
    --index-url https://download.pytorch.org/whl/cpu

RUN pip install --no-cache-dir \
    "fastapi[standard]>=0.115.11,<0.116.0" \
    "numpy>=1.26.0,<2.0.0" \
    "pydantic>=2.10.6,<3.0.0" \
    "requests>=2.32.0,<3.0.0" \
    "streamlit==1.43.1" \
    "transformers>=4.40.0,<4.41.0"

COPY app ./app
COPY artifacts ./artifacts

EXPOSE 6872 8501
