from .rss_crawler import crawl_rss_sources


def run_crawlers() -> None:
    crawl_rss_sources()


if __name__ == "__main__":
    # TODO: Run `os.makedirs(DATA_BRONZE_DIR)` (base path of the crawlers' output) in the main flow later
    run_crawlers()
