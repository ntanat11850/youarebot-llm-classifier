"""Zero-shot bot detection backed by a pretrained MNLI model."""

from __future__ import annotations

import os
from collections import OrderedDict
from pathlib import Path
from threading import Lock

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL_PATH = PROJECT_ROOT / "artifacts/typeform-distilbert-base-uncased-mnli"
DEFAULT_MODEL_NAME = "typeform/distilbert-base-uncased-mnli"


class ZeroShotBotDetector:
    """Compare human/bot hypotheses with an MNLI entailment model."""

    labels = ("human", "bot")
    hypothesis_template = "This speaker is a {}."

    def __init__(self, model_path: str | Path | None = None) -> None:
        self._model_name = os.getenv("MODEL_NAME", DEFAULT_MODEL_NAME)
        configured_path = model_path or os.getenv("MODEL_PATH")
        if configured_path:
            source: str | Path = Path(configured_path)
        elif DEFAULT_MODEL_PATH.exists():
            source = DEFAULT_MODEL_PATH
        else:
            source = self._model_name

        if isinstance(source, Path) and not source.exists():
            raise FileNotFoundError(
                f"Configured pretrained model path not found: {source}"
            )

        local_files_only = os.getenv("MODEL_LOCAL_FILES_ONLY", "0") == "1"

        self.tokenizer = AutoTokenizer.from_pretrained(
            source, local_files_only=local_files_only
        )
        self.model = AutoModelForSequenceClassification.from_pretrained(
            source, local_files_only=local_files_only
        )
        self.model.eval()
        self.entailment_id = int(self.model.config.label2id.get("ENTAILMENT", 0))

    @property
    def model_name(self) -> str:
        return self._model_name

    def predict_batch(self, texts: list[str], batch_size: int = 16) -> list[float]:
        probabilities: list[float] = []
        for start in range(0, len(texts), batch_size):
            batch = [str(text or "") for text in texts[start : start + batch_size]]
            premises: list[str] = []
            hypotheses: list[str] = []
            for text in batch:
                for label in self.labels:
                    premises.append(text)
                    hypotheses.append(self.hypothesis_template.format(label))

            encoded = self.tokenizer(
                premises,
                hypotheses,
                padding=True,
                truncation="only_first",
                max_length=256,
                return_tensors="pt",
            )
            with torch.inference_mode():
                logits = self.model(**encoded).logits[:, self.entailment_id]
            scores = logits.reshape(len(batch), len(self.labels)).softmax(dim=1)
            probabilities.extend(float(value) for value in scores[:, 1])
        return probabilities

    def predict(self, text: str) -> float:
        return self.predict_batch([text], batch_size=1)[0]


class DialogHistory:
    """Keep a bounded participant history for service-time predictions."""

    def __init__(self, max_participants: int = 2_000, max_chars: int = 4_000) -> None:
        self.max_participants = max_participants
        self.max_chars = max_chars
        self._items: OrderedDict[tuple[str, int], str] = OrderedDict()
        self._lock = Lock()

    def append(self, dialog_id: str, participant_index: int, text: str) -> str:
        key = (dialog_id, participant_index)
        with self._lock:
            previous = self._items.pop(key, "")
            combined = f"{previous}\n{text}".strip()[-self.max_chars :]
            self._items[key] = combined
            while len(self._items) > self.max_participants:
                self._items.popitem(last=False)
            return combined
