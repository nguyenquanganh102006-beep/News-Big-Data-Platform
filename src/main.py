import argparse
import os

from config import DATA_BRONZE_DIR, DATA_SILVER_DIR, DATA_GOLD_DIR, FILTERED_DATA_DIR
from crawlers import run_crawlers
from preprocessors.run import run_preprocessors
from filters import run_filters
from extractors import run_extractors


def run_pipeline(step: int = 0) -> None:
    if step not in (0, 1, 2, 3, 4):
        raise ValueError("step must be 0, 1, 2, 3 or 4")
    for directory in (DATA_BRONZE_DIR, DATA_SILVER_DIR, DATA_GOLD_DIR, FILTERED_DATA_DIR):
        os.makedirs(directory, exist_ok=True)
    if step in (0, 1):
        run_crawlers()
    if step in (0, 2):
        run_preprocessors()
    if step in (0, 3):
        run_filters()
    if step in (0, 4):
        run_extractors()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RSS -> Bronze -> Silver -> filter -> Gold extraction")
    parser.add_argument("--step", type=int, choices=(0, 1, 2, 3, 4), default=0,
                        help="0: full pipeline, 1: crawlers, 2: preprocessors, 3: filters, 4: extractors")
    run_pipeline(step=parser.parse_args().step)
