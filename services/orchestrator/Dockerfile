FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /service

RUN pip install --no-cache-dir \
    "fastapi[standard]>=0.115.11,<0.116.0" \
    "pydantic>=2.10.6,<3.0.0" \
    "requests>=2.32.0,<3.0.0"

COPY main.py ./main.py

EXPOSE 8000

CMD ["fastapi", "run", "main.py", "--host", "0.0.0.0", "--port", "8000"]
