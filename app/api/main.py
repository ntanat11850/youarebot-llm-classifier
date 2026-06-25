from contextlib import asynccontextmanager
from functools import lru_cache
from time import perf_counter
from uuid import uuid4

from app.core.logging import app_logger
from app.llm_client import LLMClientError, generate_reply
from app.model_inference import DialogHistory, ZeroShotBotDetector
from app.models import GetMessageRequestModel, GetMessageResponseModel, IncomingMessage, Prediction
from fastapi import FastAPI, HTTPException

@lru_cache(maxsize=1)
def get_detector() -> ZeroShotBotDetector:
    return ZeroShotBotDetector()


dialog_history = DialogHistory()


@asynccontextmanager
async def lifespan(app: FastAPI):
    app_logger.info("Loading zero-shot classifier on startup")
    get_detector()
    yield


app = FastAPI(lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "model_name": get_detector().model_name}


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
    try:
        reply = await generate_reply(body.last_msg_text)
    except LLMClientError as exc:
        app_logger.exception("Failed to generate LLM reply")
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return GetMessageResponseModel(new_msg_text=reply, dialog_id=body.dialog_id)

@app.post("/predict", response_model=Prediction)
def predict(msg: IncomingMessage) -> Prediction:
    """
    Endpoint to save a message and get the probability
    that this message if from bot .

    Returns a `Prediction` object.
    """

    started_at = perf_counter()
    history = dialog_history.append(str(msg.dialog_id), msg.participant_index, msg.text)
    detector = get_detector()
    probability = detector.predict(history)
    elapsed_ms = (perf_counter() - started_at) * 1000
    app_logger.info(
        "Predicted dialog_id=%s message_id=%s participant_index=%s model=%s latency_ms=%.2f probability=%.6f",
        msg.dialog_id,
        msg.id,
        msg.participant_index,
        detector.model_name,
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
