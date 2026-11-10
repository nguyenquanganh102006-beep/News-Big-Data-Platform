import hashlib
from datetime import datetime
from pathlib import Path
import re

from .rss_vnexpress import rss_vnexpress_preprocessor
from .rss_vietnamplus import rss_vietnamplus_preprocessor
from .rss_tuoitre import rss_tuoitre_preprocessor
from .rss_generic import preprocess_rss_source
from config import DATA_DIR, DATA_ARTIFACTS_DIR, RSS_SOURCES


def bronze_snapshots(crawled_date: str | None = None):
    if crawled_date is None:
        prefix = None
    else:
        date_format = "%Y-%m-%d" if len(crawled_date) == 10 else "%Y-%m-%d %H:%M:%S"
        parsed = datetime.strptime(crawled_date, date_format)
        if parsed.strftime(date_format) != crawled_date:
            raise ValueError("crawled_date must be YYYY-MM-DD or YYYY-MM-DD hh:mm:ss")
        prefix = parsed.strftime("%Y%m%d" if len(crawled_date) == 10 else "%Y%m%d_%H%M%S")

    bases = [Path(DATA_DIR), *(Path(path) for path in sorted((Path(DATA_ARTIFACTS_DIR) / "diagnostics").glob("*/data")))]
    discovered = {}
    for base in bases:
        for source in RSS_SOURCES:
            for path in (base / "bronze" / source).glob("*.parquet"):
                if not re.fullmatch(r"\d{8}_\d{6}(?:_\d{6})?\.parquet", path.name):
                    continue
                if prefix and not path.stem.startswith(prefix):
                    continue
                identity = (source, path.name)
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                if identity in discovered and discovered[identity][1] != digest:
                    raise ValueError(f"Conflicting Bronze snapshots for {source}: {path.name}")
                discovered[identity] = (path, digest)
    return {source: [path for (name, _), (path, _) in sorted(discovered.items()) if name == source]
            for source in RSS_SOURCES}


def run_preprocessors(crawled_date: str | None = None):
    specialized = {
        "vnexpress": rss_vnexpress_preprocessor,
        "vietnamplus": rss_vietnamplus_preprocessor,
        "tuoitre": rss_tuoitre_preprocessor,
    }
    snapshots = bronze_snapshots(crawled_date)
    for source, paths in snapshots.items():
        if not paths:
            raise FileNotFoundError(f"No Bronze snapshot found for {source}")
        for path in paths:
            if source in specialized:
                specialized[source](save_file=True, bronze_path=path)
            else:
                preprocess_rss_source(source, save_file=True, bronze_path=path)
    


if __name__ == "__main__":
    run_preprocessors()
