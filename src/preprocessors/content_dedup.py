"""Mark near-duplicate articles with TF-IDF cosine similarity.

Original Silver rows are preserved. Downstream filtering consumes only the
canonical rows, while the deduplicated Silver output retains the audit markers.
"""
from collections import deque
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import html
import json
import math
from pathlib import Path
from tempfile import NamedTemporaryFile
import unicodedata

from bs4 import BeautifulSoup
import polars as pl
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from config import (
    DEDUPLICATED_DATA_DIR, DUPLICATE_ALGORITHM_VERSION,
    DUPLICATE_SIMILARITY_THRESHOLD, DUPLICATE_WINDOW_HOURS, FILTER_SOURCES,
    RSS_SOURCES,
)
from .utils import dedup_add_article_identity


RESULT_COLUMNS = {
    "is_duplicate": pl.Boolean,
    "duplicate_of_article_key": pl.String,
    "duplicate_similarity": pl.Float64,
    "duplicate_algorithm": pl.String,
}


def _plain(value):
    if not isinstance(value, str) or not value.strip():
        return ""
    text = BeautifulSoup(html.unescape(value), "html.parser").get_text(" ", strip=True)
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


def _utc(value):
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        text = value.strip()
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            try:
                parsed = parsedate_to_datetime(text)
            except (TypeError, ValueError, OverflowError):
                return None
    else:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    try:
        return parsed.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        return None


def detect_duplicate_articles(frame: pl.DataFrame, *, threshold=DUPLICATE_SIMILARITY_THRESHOLD,
                              window_hours=DUPLICATE_WINDOW_HOURS) -> pl.DataFrame:
    """Return every row with duplicate markers; choose earliest publication as canonical.

    Similarity uses the combined title and description. Only prior canonical
    articles published within the inclusive time window can suppress a row.
    Stable source/key ordering resolves identical publication timestamps.
    """
    if not isinstance(threshold, (int, float)) or isinstance(threshold, bool) or not 0 <= threshold <= 1:
        raise ValueError("threshold must be between 0 and 1")
    if (not isinstance(window_hours, (int, float)) or isinstance(window_hours, bool)
            or not math.isfinite(window_hours) or window_hours <= 0):
        raise ValueError("window_hours must be finite and positive")
    required = {"article_key", "source", "title", "description", "pub_date"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Duplicate input missing columns: {', '.join(sorted(missing))}")

    clean = frame.drop([column for column in RESULT_COLUMNS if column in frame.columns])
    count = clean.height
    if count == 0:
        return clean.with_columns([
            pl.Series(name, [], dtype=dtype) for name, dtype in RESULT_COLUMNS.items()
        ])

    titles = clean["title"].to_list()
    descriptions = clean["description"].to_list()
    documents = [(_plain(title) + " " + _plain(description)).strip()
                 for title, description in zip(titles, descriptions)]
    dates = [_utc(value) for value in clean["pub_date"].to_list()]
    keys = clean["article_key"].to_list()
    sources = clean["source"].to_list()

    vectors = None
    if any(documents):
        vectorizer = TfidfVectorizer(
            analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True,
        )
        try:
            vectors = vectorizer.fit_transform(documents)
        except ValueError as error:
            if "empty vocabulary" not in str(error):
                raise

    order = sorted(range(count), key=lambda i: (
        dates[i] is None,
        dates[i] or datetime.max.replace(tzinfo=timezone.utc),
        str(sources[i] or ""), str(keys[i] or ""), i,
    ))
    is_duplicate = [False] * count
    duplicate_of = [None] * count
    similarities = [None] * count
    active = deque()
    window = timedelta(hours=window_hours)

    for index in order:
        published = dates[index]
        if published is None or not documents[index] or keys[index] is None or vectors is None:
            continue
        while active and published - dates[active[0]] > window:
            active.popleft()
        candidates = list(active)
        if candidates:
            scores = cosine_similarity(vectors[index], vectors[candidates]).ravel()
            best_position = max(range(len(scores)), key=lambda position: float(scores[position]))
            score = float(scores[best_position])
            if score >= threshold:
                canonical_index = candidates[best_position]
                is_duplicate[index] = True
                duplicate_of[index] = keys[canonical_index]
                similarities[index] = score
                continue
        active.append(index)

    return clean.with_columns([
        pl.Series("is_duplicate", is_duplicate, dtype=pl.Boolean),
        pl.Series("duplicate_of_article_key", duplicate_of, dtype=pl.String),
        pl.Series("duplicate_similarity", similarities, dtype=pl.Float64),
        pl.lit(DUPLICATE_ALGORITHM_VERSION).alias("duplicate_algorithm"),
    ])


def _write_parquet_atomic(frame, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=path.parent, suffix=".parquet", delete=False) as temporary:
        staged = Path(temporary.name)
    try:
        frame.write_parquet(staged)
        staged.replace(path)
    finally:
        staged.unlink(missing_ok=True)


def _write_json_atomic(value, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                            suffix=".json", delete=False) as temporary:
        staged = Path(temporary.name)
        json.dump(value, temporary, ensure_ascii=False, indent=2)
    try:
        staged.replace(path)
    finally:
        staged.unlink(missing_ok=True)


def run_content_dedup():
    """Rebuild content-duplicate annotations from all accumulated source Silver."""
    frames = []
    for source in FILTER_SOURCES:
        path = Path(RSS_SOURCES[source]["silver_save_path"])
        if not path.is_file():
            raise FileNotFoundError(f"Missing Silver input for content dedup: {path}")
        frame = pl.read_parquet(path)
        if "source" not in frame.columns:
            frame = dedup_add_article_identity(frame, source)
        elif frame.filter(pl.col("source") != source).height:
            raise ValueError(f"Unexpected source rows in {path}")
        elif "article_key" not in frame.columns:
            frame = dedup_add_article_identity(frame, source)
        frames.append(frame)

    combined = pl.concat(frames, how="diagonal_relaxed")
    tagged = detect_duplicate_articles(combined)
    output_dir = Path(DEDUPLICATED_DATA_DIR)
    per_source = {}
    for source in FILTER_SOURCES:
        part = tagged.filter(pl.col("source") == source)
        _write_parquet_atomic(part, output_dir / f"{source}.parquet")
        per_source[source] = {
            "input": part.height,
            "duplicates": part.filter(pl.col("is_duplicate")).height,
            "retained": part.filter(~pl.col("is_duplicate")).height,
        }
    duplicates = tagged.filter(pl.col("is_duplicate"))
    _write_parquet_atomic(duplicates, output_dir / "duplicates.parquet")
    result = {
        "algorithm": DUPLICATE_ALGORITHM_VERSION,
        "threshold": DUPLICATE_SIMILARITY_THRESHOLD,
        "window_hours": DUPLICATE_WINDOW_HOURS,
        "input": tagged.height,
        "duplicates": duplicates.height,
        "retained": tagged.height - duplicates.height,
        "sources": per_source,
    }
    _write_json_atomic(result, output_dir / "manifest.json")
    return result


if __name__ == "__main__":
    print(json.dumps(run_content_dedup(), ensure_ascii=False, indent=2))
