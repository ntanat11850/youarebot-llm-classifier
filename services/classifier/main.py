from __future__ import annotations

import json
import os
from collections import OrderedDict
from pathlib import Path
from threading import Lock
from time import perf_counter
from uuid import UUID, uuid4

from fastapi import FastAPI, Response
from pydantic import BaseModel, Field, UUID4, StrictStr


DEFAULT_MODEL_PATH = "/mlflow-artifacts/champion_classifier.json"


class IncomingMessage(BaseModel):
    text: StrictStr
    dialog_id: UUID4
    id: UUID4
    participant_index: int


class Prediction(BaseModel):
    id: UUID4
    message_id: UUID4
    dialog_id: UUID4
    participant_index: int
    is_bot_probability: float


class ScoreRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5_000)


class ScoreResponse(BaseModel):
    label: str
    proba: float = Field(ge=0.0, le=1.0)
    is_bot_probability: float = Field(ge=0.0, le=1.0)
    model_name: str
    model_version: str


class DialogHistory:
    def __init__(self, max_participants: int = 2_000, max_chars: int = 4_000) -> None:
        self.max_participants = max_participants
        self.max_chars = max_chars
        self._items: OrderedDict[tuple[str, int], str] = OrderedDict()
        self._lock = Lock()

    def append(self, dialog_id: UUID, participant_index: int, text: str) -> str:
        key = (str(dialog_id), participant_index)
        with self._lock:
            previous = self._items.pop(key, "")
            combined = f"{previous}\n{text}".strip()[-self.max_chars :]
            self._items[key] = combined
            while len(self._items) > self.max_participants:
                self._items.popitem(last=False)
            return combined


class ChampionClassifier:
    """Small artifact-backed text classifier used for service-boundary homework."""

    def __init__(self, artifact_path: str | Path) -> None:
        self.artifact_path = Path(artifact_path)
        with self.artifact_path.open() as file:
            artifact = json.load(file)

        self.model_name = artifact["model_name"]
        self.version = artifact["version"]
        self.bot_markers = [item.lower() for item in artifact["bot_markers"]]
        self.human_markers = [item.lower() for item in artifact["human_markers"]]
        self.base_probability = float(artifact.get("base_probability", 0.45))
        self.marker_weight = float(artifact.get("marker_weight", 0.08))

    def predict(self, text: str) -> float:
        normalized = f" {text.lower()} "
        bot_hits = sum(1 for marker in self.bot_markers if marker in normalized)
        human_hits = sum(1 for marker in self.human_markers if marker in normalized)
        probability = self.base_probability + self.marker_weight * (bot_hits - human_hits)
        return max(0.0, min(1.0, probability))


model_path = os.getenv("CHAMPION_MODEL_PATH", DEFAULT_MODEL_PATH)
classifier = ChampionClassifier(model_path)
dialog_history = DialogHistory()
app = FastAPI(title="Classifier Service")


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "model_name": classifier.model_name,
        "model_version": classifier.version,
        "artifact_path": str(classifier.artifact_path),
    }


@app.get("/ready")
def ready() -> dict[str, str]:
    return {
        "status": "ready",
        "model_name": classifier.model_name,
        "model_version": classifier.version,
    }


@app.post("/score", response_model=ScoreResponse)
def score(request: ScoreRequest) -> ScoreResponse:
    probability = classifier.predict(request.text)
    return ScoreResponse(
        label="bot" if probability >= 0.5 else "human",
        proba=probability,
        is_bot_probability=probability,
        model_name=classifier.model_name,
        model_version=classifier.version,
    )


@app.post("/predict", response_model=Prediction)
def predict(msg: IncomingMessage) -> Prediction:
    started_at = perf_counter()
    history = dialog_history.append(msg.dialog_id, msg.participant_index, msg.text)
    probability = classifier.predict(history)
    elapsed_ms = (perf_counter() - started_at) * 1000
    print(
        "predicted",
        {
            "dialog_id": str(msg.dialog_id),
            "message_id": str(msg.id),
            "participant_index": msg.participant_index,
            "latency_ms": round(elapsed_ms, 2),
            "probability": round(probability, 6),
        },
    )
    return Prediction(
        id=uuid4(),
        message_id=msg.id,
        dialog_id=msg.dialog_id,
        participant_index=msg.participant_index,
        is_bot_probability=probability,
    )


@app.get("/metrics")
def metrics() -> Response:
    return Response("# classifier metrics are not enabled in this lightweight build\n", media_type="text/plain")
