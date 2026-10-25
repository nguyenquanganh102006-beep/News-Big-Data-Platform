from pathlib import Path

from .crawlers import RSS_SOURCES


def latest_bronze_path(source: str) -> Path:
    """Return the latest timestamped snapshot for a source."""
    directory = Path(RSS_SOURCES[source]["bronze_dir"])
    snapshots = sorted(directory.glob("*.parquet"))
    if not snapshots:
        raise FileNotFoundError(
            f"No Bronze snapshots in {directory}. Run the crawler first."
        )
    return snapshots[-1]
