import argparse
import os

from config import DATA_BRONZE_DIR, DATA_SILVER_DIR, FILTERED_DATA_DIR, EXTRACT_OUTPUT_DIR, MatchConfig
from crawlers import run_crawlers
from preprocessors.run import run_preprocessors
from filters import run_filters
from extractors import run_extractors
from events import run_events


def run_pipeline(step: int = 0, event_config=None) -> None:
    if step not in (0, 1, 2, 3, 4, 5):
        raise ValueError("step must be 0, 1, 2, 3, 4 or 5")
    for directory in (DATA_BRONZE_DIR, DATA_SILVER_DIR, FILTERED_DATA_DIR, EXTRACT_OUTPUT_DIR):
        os.makedirs(directory, exist_ok=True)
    if step in (0, 1):
        run_crawlers()
    if step in (0, 2):
        run_preprocessors()
    if step in (0, 3):
        run_filters()
    if step in (0, 4):
        run_extractors()
    if step in (0, 5):
        if event_config is None:
            run_events()
        else:
            run_events(config=event_config)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RSS -> Bronze -> Silver articles -> Gold event database")
    parser.add_argument("--step", type=int, choices=(0, 1, 2, 3, 4, 5), default=0,
                        help="0: full pipeline, 1: crawlers, 2: preprocessors, 3: filters, 4: extract to Silver, 5: Silver to Gold events")
    parser.add_argument("--semantic-model", help="Optional FastEmbed multilingual sentence model for event matching")
    parser.add_argument("--model-cache", help="Embedding model cache directory")
    args = parser.parse_args()
    config = (MatchConfig(semantic_model=args.semantic_model, semantic_cache_dir=args.model_cache)
              if args.semantic_model or args.model_cache else None)
    run_pipeline(step=args.step, event_config=config)
