from datetime import datetime
from pathlib import Path
import re

from .crawlers import RSS_SOURCES


# Only these known tracking parameters are removed (case-insensitive).
TRACKING_QUERY_PARAMS = frozenset({
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "utm_id", "fbclid", "gclid", "dclid", "msclkid",
})


def latest_bronze_path(source: str, crawled_date: str | None = None) -> Path:
    """Select the latest file, latest file on a date, or exact crawl time."""
    directory = Path(RSS_SOURCES[source]["bronze_dir"])
    pattern = "*.parquet"
    if crawled_date is not None:
        date_format = "%Y-%m-%d" if len(crawled_date) == 10 else "%Y-%m-%d %H:%M:%S"
        parsed = datetime.strptime(crawled_date, date_format)
        if parsed.strftime(date_format) != crawled_date:
            raise ValueError("crawled_date must be YYYY-MM-DD or YYYY-MM-DD hh:mm:ss")
        pattern = (parsed.strftime("%Y%m%d") + "_*.parquet" if len(crawled_date) == 10
                   else parsed.strftime("%Y%m%d_%H%M%S") + "*.parquet")
    files = sorted(path for path in directory.glob(pattern)
                   if re.fullmatch(r"\d{8}_\d{6}(?:_\d{6})?\.parquet", path.name))
    if not files:
        raise FileNotFoundError(f"No Bronze file in {directory} for {crawled_date or 'latest'}. Run the crawler first.")
    # For identical crawl times, choose the last collision suffix.
    return files[-1]
