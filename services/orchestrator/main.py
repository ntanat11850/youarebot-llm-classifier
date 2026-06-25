from __future__ import annotations

import os
from typing import Any

import requests
from fastapi import FastAPI, HTTPException
from pydantic import UUID4, BaseModel, StrictStr


CLASSIFIER_URL = os.getenv("CLASSIFIER_URL", "http://classifier:8000")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://llm:11434")
LLM_MODEL = os.getenv("LLM_MODEL", "local-model")
REQUEST_TIMEOUT_SECONDS = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "120"))


class GetMessageRequestModel(BaseModel):
    dialog_id: UUID4
    last_msg_text: StrictStr
    last_message_id: UUID4 | None


class GetMessageResponseModel(BaseModel):
    new_msg_text: StrictStr
    dialog_id: UUID4


app = FastAPI(title="Public Orchestrator")


def forward_json(method: str, url: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        response = requests.request(
            method,
            url,
            json=payload,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Internal service error: {exc}") from exc


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "classifier_url": CLASSIFIER_URL,
        "llm_base_url": LLM_BASE_URL,
    }


@app.post("/predict")
def predict(payload: dict[str, Any]) -> dict[str, Any]:
    return forward_json("POST", f"{CLASSIFIER_URL}/predict", payload)


@app.post("/get_message", response_model=GetMessageResponseModel)
def get_message(body: GetMessageRequestModel) -> GetMessageResponseModel:
    llm_payload = {
        "model": LLM_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "You are a concise, helpful chat bot. Answer naturally and keep replies brief.",
            },
            {"role": "user", "content": body.last_msg_text},
        ],
        "temperature": 0.7,
        "max_tokens": 256,
    }
    response = forward_json(
        "POST",
        f"{LLM_BASE_URL.rstrip('/')}/v1/chat/completions",
        llm_payload,
    )
    try:
        reply = str(response["choices"][0]["message"]["content"]).strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise HTTPException(status_code=502, detail=f"Unexpected LLM response: {response}") from exc

    if not reply:
        raise HTTPException(status_code=502, detail="LLM returned an empty response")
    return GetMessageResponseModel(new_msg_text=reply, dialog_id=body.dialog_id)
