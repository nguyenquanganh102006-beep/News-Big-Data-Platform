from pathlib import Path
from tempfile import NamedTemporaryFile

import polars as pl

from config import DEBUG, RSS_SOURCES, FILTERED_DATA_DIR, FILTER_SOURCES, FILTER_LABELS
from .accident import classify_accident


def filter_frame(df: pl.DataFrame) -> pl.DataFrame:
    if "title" not in df.columns:
        raise ValueError("Silver input must contain a title column")
    descriptions = df["description"].to_list() if "description" in df.columns else [None] * df.height
    decisions = [classify_accident(title, description)
                 for title, description in zip(df["title"].to_list(), descriptions)]
    return df.with_columns([
        pl.Series(column, [getattr(d, field) for d in decisions], dtype=pl.String)
        for column, field in (("accident_label", "label"), ("filter_reason", "reason"),
                              ("filter_evidence", "evidence"), ("filter_version", "version"))
    ])


def write_parquet_atomic(df: pl.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=path.parent, suffix=".parquet", delete=False) as tmp:
        temporary = Path(tmp.name)
    try:
        df.write_parquet(temporary)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def filter_silver_file(input_path: Path, output_dir: Path) -> dict[str, int]:
    classified = filter_frame(pl.read_parquet(input_path))
    partitions = {label: classified.filter(pl.col("accident_label") == label)
                  for label in FILTER_LABELS}
    write_parquet_atomic(classified, output_dir / "classified.parquet")
    for label, frame in partitions.items():
        write_parquet_atomic(frame, output_dir / f"{label}.parquet")
    return {"input": classified.height, **{label: df.height for label, df in partitions.items()}}


def run_filters() -> None:
    # Validate all required inputs before replacing any output.
    for source in FILTER_SOURCES:
        path = Path(RSS_SOURCES[source]["silver_save_path"])
        if not path.is_file():
            raise FileNotFoundError(f"Missing Silver: {path}. Run preprocessors first.")
    for source in FILTER_SOURCES:
        counts = filter_silver_file(Path(RSS_SOURCES[source]["silver_save_path"]),
                                    Path(FILTERED_DATA_DIR) / source)
        if DEBUG:
            print(f"[Filter] source={source}, " + ", ".join(f"{key}={value}" for key, value in counts.items()))


if __name__ == "__main__":
    run_filters()
