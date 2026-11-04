"""A shared TF-IDF space for all comparisons in one run."""

import sklearn
from sklearn.feature_extraction.text import TfidfVectorizer

from .adapter import fingerprint


class TextModel:
    def __init__(self, texts):
        corpus = sorted(set(text for text in texts if text and text.strip()))
        self.vectorizer = TfidfVectorizer(
            analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True,
        )
        self.fingerprint = fingerprint({"corpus": corpus, "sklearn": sklearn.__version__,
                                        "analyzer": "char_wb", "ngrams": [3, 5], "sublinear_tf": True})
        self.available = False
        if corpus:
            try:
                self.vectorizer.fit(corpus)
                self.available = True
            except ValueError as error:
                if "empty vocabulary" not in str(error):
                    raise
        self._cache = {}

    def similarity(self, left: str, right: str) -> float | None:
        if not self.available or not left.strip() or not right.strip():
            return None
        for text in (left, right):
            if text not in self._cache:
                self._cache[text] = self.vectorizer.transform([text])
        a, b = self._cache[left], self._cache[right]
        if not a.nnz or not b.nnz:
            return None
        return max(0.0, min(1.0, float(a.multiply(b).sum())))
