# YouAreBot Microservice Architecture

This repository is the quick-start bot refactored into a small local
microservice architecture.

## Services

`docker-compose.yaml` starts four services:

1. `mlflow` - MLflow tracking server and artifact store.
2. `classifier` - internal FastAPI service for `POST /predict`.
3. `llm` - internal OpenAI-compatible llama.cpp service for
   `POST /v1/chat/completions`.
4. `orchestrator` - public FastAPI gateway.

The orchestrator is the only public API for the homework. It does not load or
run any model. It only forwards requests:

```text
POST /predict     -> http://classifier:8000/predict
POST /get_message -> http://llm:11434/v1/chat/completions
```

Inside Docker Compose, services communicate by service name, not by
`localhost`.

## Architecture

```text
client
  |
  v
orchestrator:8000
  |---- POST /predict ----> classifier:8000
  |                            |
  |                            v
  |                         MLflow artifact volume
  |
  |---- POST /get_message -> llm:11434
                               |
                               v
                         llama.cpp chat completions
```

## MLflow Artifact

The classifier loads its champion artifact from:

```text
mlflow/artifacts/champion_classifier.json
```

The MLflow service serves the tracking UI on:

```text
http://127.0.0.1:5001
```

For this architecture homework, the classifier artifact is intentionally small
so the full project remains easy to clone and run locally.

## Run

```bash
docker compose up --build
```

The first build downloads a small Qwen GGUF model into the LLM image. This can
take a few minutes.

Public orchestrator URL:

```text
http://127.0.0.1:6872
```

## Test `/predict`

```bash
curl -X POST http://127.0.0.1:6872/predict \
  -H 'Content-Type: application/json' \
  -d '{
    "text": "As an AI language model, here are the steps.",
    "dialog_id": "11111111-1111-4111-8111-111111111111",
    "id": "22222222-2222-4222-8222-222222222222",
    "participant_index": 1
  }'
```

Expected: JSON with `is_bot_probability` in the range `[0, 1]`.

## Test `/get_message`

```bash
curl -X POST http://127.0.0.1:6872/get_message \
  -H 'Content-Type: application/json' \
  -d '{
    "dialog_id": "11111111-1111-4111-8111-111111111111",
    "last_msg_text": "Say hello in one short sentence.",
    "last_message_id": "33333333-3333-4333-8333-333333333333"
  }'
```

Expected: JSON with `new_msg_text` containing an LLM-generated answer.

## Notes

- No secrets, tokens, or API keys are required.
- The public gateway is `orchestrator`; the classifier and LLM are internal
  services.
- The LLM service uses internal port `11434`.
- Local MLflow run history under `mlflow/mlruns/` is ignored.
