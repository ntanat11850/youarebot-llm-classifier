from __future__ import annotations

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID, uuid4

import asyncpg
import httpx
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field


logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("youarebot.orchestrator")

CLASSIFIER_URL = os.getenv("CLASSIFIER_URL", "http://classifier:8000")
DATABASE_URL = os.getenv("DATABASE_URL", "")
REQUEST_TIMEOUT_SECONDS = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "2.0"))
DB_CONNECT_RETRIES = int(os.getenv("DB_CONNECT_RETRIES", "30"))
DB_CONNECT_SLEEP_SECONDS = float(os.getenv("DB_CONNECT_SLEEP_SECONDS", "1.0"))


class IncomingMessage(BaseModel):
    text: str = Field(min_length=1, max_length=5_000)
    dialog_id: UUID | None = None
    id: UUID | None = None
    participant_index: int = Field(default=0, ge=0)


class Prediction(BaseModel):
    id: UUID
    message_id: UUID | None
    dialog_id: UUID | None
    participant_index: int
    label: str
    proba: float = Field(ge=0.0, le=1.0)
    is_bot_probability: float = Field(ge=0.0, le=1.0)
    model_name: str
    model_version: str
    latency_ms: float = Field(ge=0.0)


CREATE_PREDICTIONS_TABLE = """
CREATE TABLE IF NOT EXISTS predictions (
    id UUID PRIMARY KEY,
    message_id UUID,
    dialog_id UUID,
    participant_index INTEGER NOT NULL,
    text TEXT NOT NULL,
    label TEXT NOT NULL,
    proba DOUBLE PRECISION NOT NULL,
    is_bot_probability DOUBLE PRECISION NOT NULL,
    model_name TEXT NOT NULL,
    model_version TEXT NOT NULL,
    latency_ms DOUBLE PRECISION NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


async def create_db_pool() -> asyncpg.Pool | None:
    if not DATABASE_URL:
        return None

    last_error: Exception | None = None
    for attempt in range(1, DB_CONNECT_RETRIES + 1):
        try:
            pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=4)
            async with pool.acquire() as connection:
                await connection.execute(CREATE_PREDICTIONS_TABLE)
            return pool
        except (OSError, asyncpg.PostgresError) as exc:
            last_error = exc
            logger.info("database_connect_attempt=%s status=retry error=%s", attempt, exc)
            await asyncio.sleep(DB_CONNECT_SLEEP_SECONDS)

    raise RuntimeError("database connection failed") from last_error


async def check_database(pool: asyncpg.Pool | None) -> dict[str, str]:
    if pool is None:
        return {"status": "disabled"}

    try:
        async with pool.acquire() as connection:
            await connection.fetchval("SELECT 1")
    except (OSError, asyncpg.PostgresError) as exc:
        raise HTTPException(status_code=503, detail="database is not ready") from exc

    return {"status": "ready"}


@asynccontextmanager
async def lifespan(app_: FastAPI):
    app_.state.http = httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS)
    app_.state.db = await create_db_pool()
    try:
        yield
    finally:
        await app_.state.http.aclose()
        if app_.state.db is not None:
            await app_.state.db.close()


app = FastAPI(title="YouAreBot Public Orchestrator", version="2.0.0", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
async def ready() -> dict[str, Any]:
    try:
        response = await app.state.http.get(f"{CLASSIFIER_URL}/ready")
        response.raise_for_status()
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="classifier readiness timeout") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="classifier is not ready") from exc

    return {
        "status": "ready",
        "classifier": response.json(),
        "database": await check_database(app.state.db),
    }


@app.post("/predict", response_model=Prediction)
async def predict(message: IncomingMessage) -> Prediction:
    started = time.perf_counter()
    request_id = uuid4()

    try:
        response = await app.state.http.post(
            f"{CLASSIFIER_URL}/score",
            json={"text": message.text},
        )
        response.raise_for_status()
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="classifier timeout") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="classifier request failed") from exc

    payload = response.json()
    latency_ms = (time.perf_counter() - started) * 1000
    prediction = Prediction(
        id=request_id,
        message_id=message.id,
        dialog_id=message.dialog_id,
        participant_index=message.participant_index,
        label=payload["label"],
        proba=payload["proba"],
        is_bot_probability=payload["is_bot_probability"],
        model_name=payload["model_name"],
        model_version=payload["model_version"],
        latency_ms=round(latency_ms, 3),
    )

    if app.state.db is not None:
        try:
            async with app.state.db.acquire() as connection:
                await connection.execute(
                    """
                    INSERT INTO predictions (
                        id, message_id, dialog_id, participant_index, text, label, proba,
                        is_bot_probability, model_name, model_version, latency_ms
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                    """,
                    prediction.id,
                    prediction.message_id,
                    prediction.dialog_id,
                    prediction.participant_index,
                    message.text,
                    prediction.label,
                    prediction.proba,
                    prediction.is_bot_probability,
                    prediction.model_name,
                    prediction.model_version,
                    prediction.latency_ms,
                )
        except (OSError, asyncpg.PostgresError) as exc:
            raise HTTPException(status_code=503, detail="database write failed") from exc

    logger.info(
        "request_id=%s model_name=%s model_version=%s latency_ms=%.2f status_code=200",
        request_id,
        prediction.model_name,
        prediction.model_version,
        latency_ms,
    )
    return prediction


@app.get("/predictions/recent")
async def recent_predictions(limit: int = Query(default=5, ge=1, le=20)) -> dict[str, Any]:
    if app.state.db is None:
        return {"database": {"status": "disabled"}, "items": []}

    async with app.state.db.acquire() as connection:
        rows = await connection.fetch(
            """
            SELECT id, message_id, dialog_id, participant_index, label, proba,
                   is_bot_probability, model_name, model_version, latency_ms, created_at
            FROM predictions
            ORDER BY created_at DESC
            LIMIT $1
            """,
            limit,
        )

    return {
        "database": {"status": "ready"},
        "items": [
            {
                "id": str(row["id"]),
                "message_id": str(row["message_id"]) if row["message_id"] else None,
                "dialog_id": str(row["dialog_id"]) if row["dialog_id"] else None,
                "participant_index": row["participant_index"],
                "label": row["label"],
                "proba": row["proba"],
                "is_bot_probability": row["is_bot_probability"],
                "model_name": row["model_name"],
                "model_version": row["model_version"],
                "latency_ms": row["latency_ms"],
                "created_at": row["created_at"].isoformat(),
            }
            for row in rows
        ],
    }
