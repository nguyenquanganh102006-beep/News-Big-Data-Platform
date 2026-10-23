import os
from .rss_crawler import crawl_rss
from config import DEBUG, RSS_SOURCES


def run_crawlers() -> None:
    for name, source in RSS_SOURCES.items():
        df = crawl_rss(
            rss_url=source["url"],
            meta_keys=source["meta_keys"],
            entry_keys=source["entry_keys"],
            Model=source["schema"],
            save_path=source["bronze_save_path"]
        )
        
        if DEBUG:
            print(f"[Info] Saved {name} df at: {source["bronze_save_path"]}")
            print(f"[Info] {name}_df.head():")
            print(df.head())
    


if __name__ == "__main__":
    # TODO: Run `os.makedirs(DATA_BRONZE_DIR)` (base path of the crawlers' output) in the main flow later
    run_crawlers()
