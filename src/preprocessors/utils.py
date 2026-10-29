from datetime import datetime, timezone, timedelta
import unicodedata
import re

import hashlib
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.parse import unquote_plus, urlsplit, urlunsplit

import polars as pl

from config import DEBUG, TRACKING_QUERY_PARAMS

def normalize_vietnamese(text: str) -> str:
    text = unicodedata.normalize("NFD", text.lower())
    text = re.sub(r"[\u0300-\u036f]", "", text)
    return text.replace("đ", "d")


def check_valid_characters(text: str) -> bool:
    text = normalize_vietnamese(text)
    allowed_chars = [
        ' ', '.', ',', '-', ':', 
        '\'', '%', '\"', '/', ';',
        '?', '(', ')',
    ]
    
    for c in text:
        if c in allowed_chars \
            or (c >= 'a' and c <= 'z') \
            or (c >= 'A' and c <= 'Z') \
            or (c >= '0' and c <= '9'): 
                continue
        
        if DEBUG:
            print(f"[Warning] Invalid char: {c}")
        
        return False
    return True


def extract_anchor_tag_href(text: str) -> str:
    target_text = "<a href=\""
    innertext_start_idx = text.find(target_text)
    if innertext_start_idx == -1:
        return ""

    innertext_start_idx += len(target_text)
    innertext_end_idx = text.find("\"", innertext_start_idx)
    if innertext_end_idx == -1:
        return ""
    
    innertext_link = text[innertext_start_idx:innertext_end_idx]
    return innertext_link


def remove_anchor_tag(text: str) -> str:
    start_text = "<a"
    start_idx = text.find(start_text)
    if start_idx == -1:
        if DEBUG:
            print("[Error] '<a' not found")
        return ""
    
    end_text = "</a>"
    end_idx = text.find(end_text)
    if end_idx == -1:
        if DEBUG:
            print("[Error] '</a>' not found")
        return ""
    
    cleaned_text = text[:start_idx] + text[end_idx+len(end_text):]
    return cleaned_text


def convert_string_to_datetime_utc(
    dt_str: str,
    format: str = "%a, %d %b %Y %H:%M:%S %z",
    utc_hours: int = 0
) -> datetime:
    tz = timezone(timedelta(hours=utc_hours))
    dt_utc = datetime.strptime(dt_str, format).replace(tzinfo=tz).astimezone(timezone.utc)
    return dt_utc


def convert_datetime_utc_to_iso_format(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds").replace("+00:00", "Z")

def normalize_double_quotes(text: str) -> str:
    text = text.replace('“', '"')
    text = text.replace('”', '"')
    return text


def extract_paragraph_tag_innertext(text: str) -> str:
    start_text = "<p>"
    innertext_start_idx = text.find(start_text)
    if innertext_start_idx == -1:
        return ""

    innertext_start_idx += len(start_text)

    end_text = "</p>" 
    innertext_end_idx = text.find(end_text, innertext_start_idx)
    if innertext_end_idx == -1:
        return ""
    
    innertext = text[innertext_start_idx:innertext_end_idx]
    return innertext


def capitalize_name(text: str) -> str:
    name_splits = text.split()
    name_upper_splits = [split.capitalize() for split in name_splits]
    name = " ".join(name_upper_splits)
    
    for idx in range(len(name)):
        if name[idx] == '.' and idx+1 < len(name):
            name = name[:idx+1] + name[idx+1].upper() + name[idx+2:]
    
    return name





def dedup_normalize_article_url(url: str | None) -> str | None:
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


def dedup_make_article_key(source: str, normalized_url: str | None) -> str | None:
    if normalized_url is None:
        return None
    return hashlib.sha256(f"{source}\n{normalized_url}".encode("utf-8")).hexdigest()


def dedup_add_article_identity(df: pl.DataFrame, source: str) -> pl.DataFrame:
    normalized = [dedup_normalize_article_url(url) for url in df["link"].to_list()]
    return df.with_columns(
        pl.lit(source).alias("source"),
        pl.Series("normalized_url", normalized, dtype=pl.String),
        pl.Series("article_key", [dedup_make_article_key(source, url) for url in normalized], dtype=pl.String),
    )



def dedup_batch(df: pl.DataFrame) -> pl.DataFrame:
    """Keep the last row per non-null key, preserving surviving row order.

    Null keys cannot identify an article, so every such row is retained.
    """
    key = pl.col("article_key")
    return df.filter(key.is_null() | key.is_last_distinct())


def dedup_new_articles_only(batch: pl.DataFrame, history: pl.DataFrame) -> pl.DataFrame:
    """Null keys never match; retain batch order through the anti join."""
    return batch.join(
        history.select("article_key").filter(pl.col("article_key").is_not_null()).unique(),
        on="article_key", how="anti", maintain_order="left",
    )


def dedup_update_silver_history(batch: pl.DataFrame, save_path: str, source: str,
                          save_file: bool = True) -> pl.DataFrame:
    """Return new articles; optionally append them to accumulated Silver.

    Run one writer per source at a time. Existing articles keep their saved data.
    """
    input_count = batch.height
    batch = dedup_batch(batch)
    batch_duplicates = input_count - batch.height
    path = Path(save_path)
    if path.exists():
        history = pl.read_parquet(path)
        # Also support Silver produced before article keys were introduced.
        history = dedup_batch(dedup_add_article_identity(history, source))
    else:
        history = batch.head(0)
    new = dedup_new_articles_only(batch, history)
    if save_file:
        accumulated = pl.concat([history, new], how="diagonal_relaxed")
        path.parent.mkdir(parents=True, exist_ok=True)
        # Replace only after a complete write, preserving history on failure.
        with NamedTemporaryFile(dir=path.parent, suffix=".parquet", delete=False) as tmp:
            temporary = Path(tmp.name)
        try:
            accumulated.write_parquet(temporary)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
    action = "saved" if save_file else "dry_run"
    if DEBUG:
        print(f"[Silver] source={source}, input={input_count}, "
          f"batch_duplicates={batch_duplicates}, "
          f"history_duplicates={batch.height - new.height}, "
          f"new={new.height}, silver_total={history.height + new.height}, "
          f"status={action}")
    return new
