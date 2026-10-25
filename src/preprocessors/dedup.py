import polars as pl
from pathlib import Path
from tempfile import NamedTemporaryFile

from .identity import add_article_identity


def deduplicate_batch(df: pl.DataFrame) -> pl.DataFrame:
    """Keep the last row per non-null key, preserving surviving row order.

    Null keys cannot identify an article, so every such row is retained.
    """
    key = pl.col("article_key")
    return df.filter(key.is_null() | key.is_last_distinct())


def new_articles_only(batch: pl.DataFrame, history: pl.DataFrame) -> pl.DataFrame:
    """Null keys never match; retain batch order through the anti join."""
    return batch.join(
        history.select("article_key").filter(pl.col("article_key").is_not_null()).unique(),
        on="article_key", how="anti", maintain_order="left",
    )


def update_silver_history(batch: pl.DataFrame, save_path: str, source: str,
                          save_file: bool = True) -> pl.DataFrame:
    """Return new articles; optionally append them to accumulated Silver.

    Run one writer per source at a time. Existing articles keep their saved data.
    """
    input_count = batch.height
    batch = deduplicate_batch(batch)
    batch_duplicates = input_count - batch.height
    path = Path(save_path)
    if path.exists():
        history = pl.read_parquet(path)
        # Also support Silver produced before article keys were introduced.
        history = deduplicate_batch(add_article_identity(history, source))
    else:
        history = batch.head(0)
    new = new_articles_only(batch, history)
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
    print(f"[Silver] source={source}, input={input_count}, "
          f"batch_duplicates={batch_duplicates}, "
          f"history_duplicates={batch.height - new.height}, "
          f"new={new.height}, silver_total={history.height + new.height}, "
          f"status={action}")
    return new
