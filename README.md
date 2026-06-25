# Zero-shot Bot Detector

A FastAPI service for the HumanOrBot project. Its `/predict` endpoint uses the
pretrained `typeform/distilbert-base-uncased-mnli` model for zero-shot bot
classification. The model compares the NLI hypotheses “This speaker is a
human” and “This speaker is a bot” and returns the normalized bot score.

## Overview

The service keeps a short, bounded participant history per dialogue so each
prediction can use the speaker's messages seen so far. The `/get_message`
endpoint sends the latest user message to the local LLM service and returns the
generated reply.

On first startup, Transformers downloads the pretrained model from Hugging
Face. To use an existing local copy, set `MODEL_PATH`; to prohibit network
access, also set `MODEL_LOCAL_FILES_ONLY=1`.

## Local evaluation

The supplied `ytest.csv` contains IDs, not labels. Evaluation therefore uses a
stable 25% dialog-level holdout from the labelled training set:

```bash
.venv/bin/python scripts/evaluate_zero_shot.py \
  --data-dir /path/to/you-are-bot-2
```

Metrics are written to `results/zero_shot_metrics.json`, and full test
predictions to `results/zero_shot_submission.csv`.

## Running the Service

## Docker Compose LLM Bot

The compose setup runs three services:

1. `llm` - llama.cpp server with a GGUF chat model
2. `fastapi` - backend API on port `6872`
3. `streamlit` - chat UI on port `8502`

This workspace is configured to use `models/qwen-model.gguf`.

```bash
docker compose up --build
```

Then open:

```text
http://localhost:8502
```

The FastAPI endpoint can be checked directly:

```bash
curl -X POST http://127.0.0.1:6872/get_message \
  -H 'Content-Type: application/json' \
  -d '{"dialog_id":"11111111-1111-4111-8111-111111111111","last_msg_text":"Say hello in one short sentence.","last_message_id":"22222222-2222-4222-8222-222222222222"}'
```

Expected result: `new_msg_text` contains an LLM-generated answer.

Go to the project directory:

### On Linux/macOS

```bash
chmod +x run_all_linux.sh
```

```bash
./run_all_linux.sh
```

### On Windows

Install Python 3.12 first, then run:

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\run_all_windows.ps1
```

If Windows fails around `pydantic-core`, check that `py -3.12 --version` works and remove any copied virtualenv:

```powershell
Remove-Item -Recurse -Force .venv
```

#### These scripts will:
1. Install Poetry (if needed)
2. Install project dependencies
3. Set up an SSH tunnel to the remote host
4. Start the FastAPI application on port 6872
