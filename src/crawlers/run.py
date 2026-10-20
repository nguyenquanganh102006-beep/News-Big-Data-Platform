import os
from .rss_crawler import crawl_rss
from config import DEBUG, RSS_SOURCES, DATA_BRONZE_DIR


def run_crawlers(base_save_path: str) -> None:
    for name, source in RSS_SOURCES.items():
        save_path = os.path.join(base_save_path, f"{name}.parquet")
        
        df = crawl_rss(
            rss_url=source["url"],
            meta_keys=source["meta_keys"],
            entry_keys=source["entry_keys"],
            Model=source["schema"],
            save_path=save_path
        )
        
        if DEBUG:
            print(f"[Info] Saved {name} df at: {save_path}")
            print(f"[Info] {name}_df.head():")
            print(df.head())
    


if __name__ == "__main__":
    os.makedirs(DATA_BRONZE_DIR, exist_ok=True)
    run_crawlers(DATA_BRONZE_DIR)
