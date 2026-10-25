import argparse

from crawlers.run import run_crawlers
from preprocessors.run import run_preprocessors
from filters.run import run_filters


def run_pipeline(skip_crawl: bool = False) -> None:
    if not skip_crawl:
        run_crawlers()
    run_preprocessors()
    # Read accumulated Silver, not just the new rows returned by preprocessors.
    run_filters()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RSS -> Bronze -> Silver dedup -> accident filter")
    parser.add_argument("--skip-crawl", action="store_true", help="Use latest existing Bronze snapshots")
    run_pipeline(skip_crawl=parser.parse_args().skip_crawl)
