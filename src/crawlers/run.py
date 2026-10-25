from datetime import datetime, timedelta, timezone
from pathlib import Path
from .rss_crawler import crawl_rss
from config import DEBUG, RSS_SOURCES


def run_crawlers() -> None:
    # Use Vietnam time consistently, independently of the host timezone.
    timestamp = datetime.now(timezone(timedelta(hours=7))).strftime("%Y%m%d_%H%M%S")
    for name, source in RSS_SOURCES.items():
        directory = Path(source["bronze_dir"])
        directory.mkdir(parents=True, exist_ok=True)
        df = crawl_rss(
            rss_url=source["url"],
            meta_keys=source["meta_keys"],
            entry_keys=source["entry_keys"],
            Model=source["schema"],
        )

        # Exclusive creation prevents overwriting even for simultaneous runs.
        suffix = 0
        while True:
            filename = timestamp if suffix == 0 else f"{timestamp}_{suffix:06d}"
            save_path = directory / f"{filename}.parquet"
            try:
                output = save_path.open("xb")
            except FileExistsError:
                suffix += 1
                continue
            with output:
                df.write_parquet(output)
            break
        
        if DEBUG:
            print(f"[Info] Saved {name} df at: {save_path}")
            print(f"[Info] {name}_df.head():")
            print(df.head())
    


if __name__ == "__main__":
    run_crawlers()
