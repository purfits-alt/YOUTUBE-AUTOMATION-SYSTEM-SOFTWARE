"""Text similarity for ideas and scripts (ADR-0029).

Two methods, same scale (cosine, 0–1):

- ``model2vec``: static multilingual embeddings (minishlab/potion-multilingual-128M, MIT), run
  locally on the CPU. The model files are downloaded once by ``tubeforge-admin fetch-models``
  (pinned revision, SHA-256 checked) into ``<data>/models/``. Loaded at half precision, only when
  first needed.
- ``trigram``: character-trigram cosine, no model. Used when the model is not installed (fresh
  installs, CI) so nothing breaks; it catches near-identical wording but not paraphrases.

Thresholds (WORKFLOW_STATE_MACHINE §2, AI_AGENT_ARCHITECTURE A08, AUDIT_AND_POLICY_SPEC):
an idea is a duplicate at ≥ 0.85; a variation of the owner's own video must be ≤ 0.70 similar to
it; a script > 0.85 similar to a recent video is a WARNING, > 0.92 CRITICAL.
"""

from __future__ import annotations

import hashlib
import math
import re
import threading
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import httpx

from tubeforge.config import get_settings

IDEA_DUPLICATE = 0.85
VARIATION_MAX = 0.70
CATALOGUE_WARNING = 0.85
CATALOGUE_CRITICAL = 0.92

MODEL_REPO = "minishlab/potion-multilingual-128M"
MODEL_REVISION = "73908c3438cf03b6a01bcb9611d62b23d0726f08"
MODEL_DIR_NAME = "potion-multilingual-128M"
# file → SHA-256 (None: small text file, checked by size only)
MODEL_FILES: dict[str, tuple[int, str | None]] = {
    "config.json": (271, None),
    "modules.json": (278, None),
    "tokenizer.json": (18_616_131, "19f1909063da3cfe3bd83a782381f040dccea475f4816de11116444a73e1b6a1"),
    "model.safetensors": (512_361_560, "14b5eb39cb4ce5666da8ad1f3dc6be4346e9b2d601c073302fa0a31bf7943397"),
}
DOWNLOAD_HOST = "huggingface.co"
# huggingface.co redirects large files to its CDN; only these hosts, over HTTPS, are followed.
ALLOWED_DOWNLOAD_SUFFIXES = ("huggingface.co", "hf.co")


class Similarity(Protocol):
    method: str

    def pairwise(self, texts: Sequence[str]) -> list[list[float]]: ...

    def against(self, text: str, corpus: Sequence[str]) -> list[float]: ...


# ------------------------------------------------------------------------------------- trigram
def _trigrams(text: str) -> Counter[str]:
    norm = " " + re.sub(r"[^\w]+", " ", text.lower()).strip() + " "
    return Counter(norm[i : i + 3] for i in range(len(norm) - 2))


def trigram_cosine(a: str, b: str) -> float:
    ta, tb = _trigrams(a), _trigrams(b)
    dot = sum(ta[k] * tb[k] for k in ta.keys() & tb.keys())
    na = math.sqrt(sum(v * v for v in ta.values()))
    nb = math.sqrt(sum(v * v for v in tb.values()))
    return 0.0 if not na or not nb else round(dot / (na * nb), 4)


class TrigramSimilarity:
    method = "trigram"

    def pairwise(self, texts: Sequence[str]) -> list[list[float]]:
        return [[trigram_cosine(a, b) for b in texts] for a in texts]

    def against(self, text: str, corpus: Sequence[str]) -> list[float]:
        return [trigram_cosine(text, c) for c in corpus]


# ----------------------------------------------------------------------------------- model2vec
class EmbeddingSimilarity:
    """Cosine of static embeddings. ``encoder`` maps texts to equal-length float vectors."""

    method = "model2vec"

    def __init__(self, encoder: Any) -> None:
        self._encoder = encoder

    def _vectors(self, texts: Sequence[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for row in self._encoder.encode(list(texts)):
            vec = [float(x) for x in row]
            norm = math.sqrt(sum(x * x for x in vec)) or 1.0
            out.append([x / norm for x in vec])
        return out

    @staticmethod
    def _cos(a: list[float], b: list[float]) -> float:
        return round(max(0.0, min(1.0, sum(x * y for x, y in zip(a, b, strict=True)))), 4)

    def pairwise(self, texts: Sequence[str]) -> list[list[float]]:
        vecs = self._vectors(texts)
        return [[self._cos(a, b) for b in vecs] for a in vecs]

    def against(self, text: str, corpus: Sequence[str]) -> list[float]:
        if not corpus:
            return []
        vecs = self._vectors([text, *corpus])
        return [self._cos(vecs[0], v) for v in vecs[1:]]


def model_dir() -> Path:
    return get_settings().resolved_data_dir / "models" / MODEL_DIR_NAME


def model_installed(path: Path | None = None) -> bool:
    path = path or model_dir()
    return all(
        (path / name).is_file() and (path / name).stat().st_size == size
        for name, (size, _) in MODEL_FILES.items()
    )


_lock = threading.Lock()
_cached: Similarity | None = None


def get_similarity() -> Similarity:
    """The model when it is installed and loads; otherwise the trigram fallback (never raises)."""
    global _cached
    with _lock:
        if _cached is None:
            _cached = _load()
        return _cached


def reset_similarity(value: Similarity | None = None) -> None:
    """Tests and ``fetch-models``: forget (or replace) the cached method."""
    global _cached
    with _lock:
        _cached = value


def _load() -> Similarity:
    path = model_dir()
    if not model_installed(path):
        return TrigramSimilarity()
    try:
        from model2vec import StaticModel

        encoder = StaticModel.from_pretrained(path, quantize_to="float16", force_download=False)
    except Exception:
        return TrigramSimilarity()
    return EmbeddingSimilarity(encoder)


# ------------------------------------------------------------------------------------ helpers
@dataclass(frozen=True)
class Nearest:
    score: float
    index: int | None  # position in the corpus, None when the corpus is empty


def nearest(text: str, corpus: Sequence[str], sim: Similarity | None = None) -> Nearest:
    scores = (sim or get_similarity()).against(text, corpus)
    if not scores:
        return Nearest(0.0, None)
    best = max(range(len(scores)), key=lambda i: scores[i])
    return Nearest(scores[best], best)


def too_similar_pairs(
    texts: Sequence[str], limit: float = IDEA_DUPLICATE, sim: Similarity | None = None
) -> list[tuple[int, int, float]]:
    matrix = (sim or get_similarity()).pairwise(texts)
    return [
        (i, j, matrix[i][j])
        for i in range(len(texts))
        for j in range(i + 1, len(texts))
        if matrix[i][j] >= limit
    ]


# ----------------------------------------------------------------------------------- download
def fetch_model(dest: Path | None = None, *, client: httpx.Client | None = None) -> Path:
    """Download the pinned model files and check them. Re-running skips files that are already right."""
    dest = dest or model_dir()
    dest.mkdir(parents=True, exist_ok=True)
    own = client is None
    http = client or httpx.Client(
        timeout=httpx.Timeout(60.0, connect=15.0),
        follow_redirects=True,
        event_hooks={"request": [_check_download_host]},
    )
    try:
        for name, (size, sha) in MODEL_FILES.items():
            target = dest / name
            if target.is_file() and target.stat().st_size == size and (sha is None or _sha256(target) == sha):
                continue
            url = f"https://{DOWNLOAD_HOST}/{MODEL_REPO}/resolve/{MODEL_REVISION}/{name}"
            part = target.with_suffix(target.suffix + ".part")
            digest = hashlib.sha256()
            with http.stream("GET", url) as resp, part.open("wb") as fh:
                resp.raise_for_status()
                for chunk in resp.iter_bytes(1 << 20):
                    digest.update(chunk)
                    fh.write(chunk)
            if part.stat().st_size != size or (sha is not None and digest.hexdigest() != sha):
                part.unlink(missing_ok=True)
                raise ValueError(f"{name}: the download does not match the expected size or checksum.")
            part.replace(target)
    finally:
        if own:
            http.close()
    reset_similarity()
    return dest


def _check_download_host(request: httpx.Request) -> None:
    host = request.url.host.lower()
    if request.url.scheme != "https" or not any(
        host == s or host.endswith("." + s) for s in ALLOWED_DOWNLOAD_SUFFIXES
    ):
        raise ValueError(f"Refusing to download the model from {request.url.scheme}://{host}.")


# Fixed pairs for ``tubeforge-admin similarity-check``: how the installed method scores obvious
# duplicates, paraphrases and unrelated ideas, so the thresholds can be checked on the owner's PC.
SELF_TEST: list[tuple[str, str, str]] = [
    ("same", "How I budget as a student in 2026", "How I budget as a student in 2026"),
    ("reworded", "How I budget as a student in 2026", "My student budget for 2026, explained"),
    (
        "paraphrase",
        "Why your phone battery dies so fast",
        "The real reasons smartphone batteries drain quickly",
    ),
    ("same topic, new angle", "How I budget as a student", "5 budgeting mistakes students make with rent"),
    ("related", "Beginner chess openings", "Famous chess games of the 1970s"),
    ("unrelated", "How I budget as a student", "The history of Roman aqueducts"),
    ("ur paraphrase", "طالب علم کے لیے بجٹ کیسے بنائیں", "طلبہ کے لیے ماہانہ بجٹ بنانے کا طریقہ"),
    (
        "es paraphrase",
        "Cómo ahorrar dinero siendo estudiante",
        "Trucos para ahorrar dinero en la universidad",
    ),
]


def self_test(sim: Similarity | None = None) -> list[tuple[str, float]]:
    method = sim or get_similarity()
    return [(label, method.against(a, [b])[0]) for label, a, b in SELF_TEST]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
