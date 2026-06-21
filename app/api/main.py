import os
from contextlib import asynccontextmanager
from functools import lru_cache
from math import exp
from time import perf_counter
from uuid import uuid4

from app.core.logging import app_logger
from app.models import GetMessageRequestModel, GetMessageResponseModel, IncomingMessage, Prediction
from fastapi import FastAPI

DEFAULT_MODEL_NAME = "hf-internal-testing/tiny-random-distilbert"


def get_model_name() -> str:
    return os.getenv("MODEL_NAME", DEFAULT_MODEL_NAME)


@lru_cache(maxsize=4)
def get_classifier(model_name: str):
    local_files_only = os.getenv("MODEL_LOCAL_FILES_ONLY", "1") != "0"
    if local_files_only:
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

    try:
        from transformers import AutoModelForSequenceClassification, AutoTokenizer, pipeline
    except ImportError:
        app_logger.warning("transformers is not installed; using fallback classifier")
        return None

    try:
        tokenizer = AutoTokenizer.from_pretrained(
            model_name, local_files_only=local_files_only
        )
        model = AutoModelForSequenceClassification.from_pretrained(
            model_name, local_files_only=local_files_only, use_safetensors=False
        )
        return pipeline("text-classification", model=model, tokenizer=tokenizer)
    except Exception as exc:
        app_logger.warning("Could not load MODEL_NAME=%s: %s", model_name, exc)
        return None


def heuristic_probability(text: str) -> float:
    lowered = text.lower()
    bot_markers = (
        "as an ai",
        "language model",
        "structured answer",
        "i can help",
        "i can assist",
        "solve this task",
    )
    score = -1.5
    score += min(len(text) / 240, 1.0)
    score += sum(1.15 for marker in bot_markers if marker in lowered)
    return 1 / (1 + exp(-score))


def probability_from_classifier(text: str, model_name: str) -> float | None:
    classifier = get_classifier(model_name)
    if classifier is None:
        return None

    result = classifier(text, truncation=True)[0]
    label = str(result["label"]).lower()
    score = float(result["score"])

    if "bot" in label or "machine" in label or "ai" in label or label in {"label_1", "positive"}:
        return score
    return 1.0 - score


def is_bot_probability(text: str) -> float:
    model_name = get_model_name()
    probability = probability_from_classifier(text, model_name)
    if probability is not None:
        return probability
    return heuristic_probability(text)


@asynccontextmanager
async def lifespan(app: FastAPI):
    model_name = get_model_name()
    app_logger.info("Loading classifier model on startup: %s", model_name)
    get_classifier(model_name)
    yield


app = FastAPI(lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "model_name": get_model_name()}


@app.post("/get_message", response_model=GetMessageResponseModel)
async def get_message(body: GetMessageRequestModel):
    """
    This functions receives a message from HumanOrNot and returns a response
        Parameters (JSON from POST-request):
            body (GetMessageRequestModel): model with request data
                dialog_id (UUID4): ID of the dialog where the message was sent
                last_msg_text (str): text of the message
                last_message_id (UUID4): ID of this message

        Returns (JSON from response):
            GetMessageResponseModel: model with response data
                new_msg_text (str): Ответ бота
                dialog_id (str): ID диалога
    """

    app_logger.info(
        f"Received message dialog_id: {body.dialog_id}, last_msg_id: {body.last_message_id}"
    )
    return GetMessageResponseModel(
        new_msg_text=body.last_msg_text, dialog_id=body.dialog_id
    )

@app.post("/predict", response_model=Prediction)
def predict(msg: IncomingMessage) -> Prediction:
    """
    Endpoint to save a message and get the probability
    that this message if from bot .

    Returns a `Prediction` object.
    """

    started_at = perf_counter()
    probability = is_bot_probability(msg.text)
    elapsed_ms = (perf_counter() - started_at) * 1000
    app_logger.info(
        "Predicted dialog_id=%s message_id=%s participant_index=%s model=%s latency_ms=%.2f probability=%.6f",
        msg.dialog_id,
        msg.id,
        msg.participant_index,
        get_model_name(),
        elapsed_ms,
        probability,
    )
    prediction_id = uuid4()

    return Prediction(
        id=prediction_id,
        message_id=msg.id,
        dialog_id=msg.dialog_id,
        participant_index=msg.participant_index,
        is_bot_probability=probability,
    )
