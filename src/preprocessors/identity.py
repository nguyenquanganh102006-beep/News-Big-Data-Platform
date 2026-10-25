import hashlib
from urllib.parse import unquote_plus, urlsplit, urlunsplit

import polars as pl

from config.dedup import TRACKING_QUERY_PARAMS


def normalize_article_url(url: str | None) -> str | None:
    """Normalize conservatively, preserving article-identifying query data."""
    if not isinstance(url, str):
        return None
    url = url.strip()
    if not url or any(character.isspace() for character in url):
        return None
    try:
        parts = urlsplit(url)
        if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
            return None
        if parts.username is not None or parts.password is not None:
            return None
        # Access port to reject malformed port values.
        parts.port
    except ValueError:
        return None

    # Preserve original encoding, values, order and repeated business parameters.
    query = "&".join(
        parameter for parameter in parts.query.split("&")
        if unquote_plus(parameter.split("=", 1)[0]).lower()
        not in TRACKING_QUERY_PARAMS
    )
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, query, ""))


def make_article_key(source: str, normalized_url: str | None) -> str | None:
    if normalized_url is None:
        return None
    return hashlib.sha256(f"{source}\n{normalized_url}".encode("utf-8")).hexdigest()


def add_article_identity(df: pl.DataFrame, source: str) -> pl.DataFrame:
    normalized = [normalize_article_url(url) for url in df["link"].to_list()]
    return df.with_columns(
        pl.lit(source).alias("source"),
        pl.Series("normalized_url", normalized, dtype=pl.String),
        pl.Series("article_key", [make_article_key(source, url) for url in normalized], dtype=pl.String),
    )
