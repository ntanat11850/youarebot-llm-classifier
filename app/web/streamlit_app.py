import os
import sys
from pathlib import Path
from uuid import uuid4

import requests
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.models import GetMessageRequestModel

default_echo_bot_url = os.getenv("FASTAPI_URL", "http://localhost:6872")
st.set_page_config(initial_sidebar_state="collapsed")

st.markdown("# LLM bot classifier")
st.sidebar.markdown("# LLM bot classifier")

if "dialog_id" not in st.session_state:
    st.session_state.dialog_id = str(uuid4())


def reset_chat() -> None:
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": "Type something",
            "probability": None,
            "message_id": str(uuid4()),
        }
    ]
    st.session_state.turns = []
    st.session_state.dialog_id = str(uuid4())


def classify_message(
    bot_url: str,
    text: str,
    message_id: str,
    participant_index: int,
) -> float | None:
    response = requests.post(
        f"{bot_url}/predict",
        json={
            "text": text,
            "dialog_id": st.session_state.dialog_id,
            "id": message_id,
            "participant_index": participant_index,
        },
        timeout=30,
    )
    response.raise_for_status()
    return float(response.json()["is_bot_probability"])


def probability_label(probability: float | None) -> str:
    if probability is None:
        return "bot probability: unavailable"
    return f"bot probability: {probability:.1%}"


def running_metrics() -> dict[str, float | int]:
    classified = [
        msg["probability"]
        for msg in st.session_state.messages
        if msg.get("probability") is not None
    ]
    deltas = [turn["delta"] for turn in st.session_state.turns]
    turn_probabilities = [turn["mean_probability"] for turn in st.session_state.turns]

    return {
        "classified_messages": len(classified),
        "turns": len(st.session_state.turns),
        "average_probability": sum(classified) / len(classified) if classified else 0.0,
        "average_turn_probability": (
            sum(turn_probabilities) / len(turn_probabilities) if turn_probabilities else 0.0
        ),
        "average_echo_delta": sum(deltas) / len(deltas) if deltas else 0.0,
    }


if "messages" not in st.session_state or "turns" not in st.session_state:
    reset_chat()

with st.sidebar:
    if st.button("Reset"):
        reset_chat()

    echo_bot_url = st.text_input(
        "Bot URL", key="echo_bot_url", value=default_echo_bot_url, disabled=True
    )

    dialog_id = st.text_input("Dialog id", key="dialog_id", disabled=True)

for msg in st.session_state["messages"]:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])
        if msg.get("probability") is not None:
            st.caption(probability_label(msg["probability"]))

metrics = running_metrics()
cols = st.columns(4)
cols[0].metric("Classified", metrics["classified_messages"])
cols[1].metric("Turns", metrics["turns"])
cols[2].metric("Avg bot prob.", f"{metrics['average_probability']:.1%}")
cols[3].metric("Echo delta", f"{metrics['average_echo_delta']:.1%}")

if message := st.chat_input():
    user_message_id = str(uuid4())
    user_probability = None
    try:
        user_probability = classify_message(echo_bot_url, message, user_message_id, 0)
    except requests.RequestException as exc:
        st.error(f"Could not classify user message: {exc}")

    user_msg = {
        "role": "user",
        "content": message,
        "message_id": user_message_id,
        "probability": user_probability,
    }
    st.session_state["messages"].append(user_msg)

    try:
        response = requests.post(
            echo_bot_url + "/get_message",
            json=GetMessageRequestModel(
                dialog_id=dialog_id, last_msg_text=message, last_message_id=uuid4()
            ).model_dump(),
            timeout=30,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        st.error(f"Could not get bot message: {exc}")
        st.rerun()

    json_response = response.json()

    response = f"{json_response['new_msg_text']}"
    assistant_message_id = str(uuid4())
    assistant_probability = None
    try:
        assistant_probability = classify_message(
            echo_bot_url, response, assistant_message_id, 1
        )
    except requests.RequestException as exc:
        st.error(f"Could not classify bot message: {exc}")

    if user_probability is not None and assistant_probability is not None:
        st.session_state.turns.append(
            {
                "user_message_id": user_message_id,
                "assistant_message_id": assistant_message_id,
                "mean_probability": (user_probability + assistant_probability) / 2,
                "delta": abs(user_probability - assistant_probability),
            }
        )

    assistant_msg = {
        "role": "assistant",
        "content": response,
        "message_id": assistant_message_id,
        "probability": assistant_probability,
    }
    st.session_state["messages"].append(assistant_msg)

    st.rerun()
