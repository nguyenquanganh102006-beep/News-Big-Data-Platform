"""Lexical and multilingual sentence representations for a whole run."""

import hashlib
from importlib.metadata import version
from pathlib import Path
from collections import OrderedDict
import sklearn
from sklearn.feature_extraction.text import TfidfVectorizer
from config import DEFAULT_SEMANTIC_MODEL

from .adapter import fingerprint
from .profile import clean, PROFILE_VERSION


_ENCODERS = {}
_DENSE_CACHE = OrderedDict()
_DENSE_CACHE_LIMIT = 20000


def split_for_encoder(text, token_count, limit=120):
    """Split below the encoder's truncation boundary, preserving all words.

    The configured symmetric MiniLM model truncates at 128 tokens. Testing
    below that boundary also detects overflow when token_count itself caps
    its answer at the model limit.
    """
    if token_count(text) <= limit:
        return [text]
    words = text.split()
    if len(words) > 1:
        midpoint = len(words) // 2
        parts = [" ".join(words[:midpoint]), " ".join(words[midpoint:])]
    elif len(text) > 1:
        midpoint = len(text) // 2
        parts = [text[:midpoint], text[midpoint:]]
    else:
        raise ValueError("Encoder cannot represent a single character within its token limit")
    return [chunk for part in parts for chunk in split_for_encoder(part, token_count, limit)]


class TextModel:
    def __init__(self, texts, semantic_model=DEFAULT_SEMANTIC_MODEL, cache_dir=None):
        corpus = sorted(set(clean(text) for text in texts if text and text.strip()))
        self.vectorizer = TfidfVectorizer(
            analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True,
        )
        metadata = {"corpus": corpus, "sklearn": sklearn.__version__, "profile": PROFILE_VERSION,
                    "analyzer": "char_wb", "ngrams": [3, 5], "sublinear_tf": True,
                    "semantic_model": semantic_model}
        self.available = False
        if corpus:
            try:
                self.vectorizer.fit(corpus)
                self.available = True
            except ValueError as error:
                if "empty vocabulary" not in str(error):
                    raise
        self._cache = {}
        self._dense = {}
        if semantic_model and corpus:
            try:
                from fastembed import TextEmbedding
                import numpy as np
            except ImportError as error:
                raise RuntimeError("Embedding dependency missing; run python -m pip install -e . "
                                   "or explicitly select --no-embedding") from error
            path = str(Path(cache_dir or "data/models/fastembed").resolve())
            key = semantic_model, path
            if key not in _ENCODERS:
                _ENCODERS[key] = TextEmbedding(model_name=semantic_model, cache_dir=path, threads=2)
            encoder = _ENCODERS[key]
            cache_keys = {text: (semantic_model, path, text) for text in corpus}
            chunks = {}
            for text in corpus:
                cached = _DENSE_CACHE.get(cache_keys[text])
                if cached is not None:
                    _DENSE_CACHE.move_to_end(cache_keys[text])
                    self._dense[text] = cached
                else:
                    chunks[text] = split_for_encoder(text, encoder.token_count)
            flat = [chunk for text in corpus if text in chunks for chunk in chunks[text]]
            vectors = iter(encoder.embed(flat, batch_size=16)) if flat else iter(())
            for text in corpus:
                if text not in chunks:
                    continue
                rows = [np.asarray(next(vectors), dtype=np.float32) for _ in chunks[text]]
                weights = [encoder.token_count(chunk) for chunk in chunks[text]]
                vector = np.average(rows, axis=0, weights=weights).astype(np.float32)
                if vector.ndim != 1 or not np.isfinite(vector).all() or not np.linalg.norm(vector):
                    raise ValueError("Semantic encoder produced an invalid embedding")
                vector = vector / np.linalg.norm(vector)
                self._dense[text] = vector
                _DENSE_CACHE[cache_keys[text]] = vector
                _DENSE_CACHE.move_to_end(cache_keys[text])
                while len(_DENSE_CACHE) > _DENSE_CACHE_LIMIT:
                    _DENSE_CACHE.popitem(last=False)
            metadata.update(fastembed=version("fastembed"), chunking="token-120-weighted-mean-v1",
                            embeddings_sha256=hashlib.sha256(b"".join(
                                self._dense[text].tobytes() for text in corpus)).hexdigest())
        self.fingerprint = fingerprint(metadata)

    def similarity(self, left: str, right: str) -> float | None:
        left, right = clean(left), clean(right)
        if not self.available or not left.strip() or not right.strip():
            return None
        for text in (left, right):
            if text not in self._cache:
                self._cache[text] = self.vectorizer.transform([text])
        a, b = self._cache[left], self._cache[right]
        if not a.nnz or not b.nnz:
            return None
        return max(0.0, min(1.0, float(a.multiply(b).sum())))

    def semantic_similarity(self, left, right):
        left, right = self._dense.get(clean(left)), self._dense.get(clean(right))
        if left is None or right is None:
            return None
        return max(0.0, min(1.0, float(left @ right)))
