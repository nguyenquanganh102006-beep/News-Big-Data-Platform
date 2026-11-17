"""Shared, read-only matching contract for incremental, streaming and batch callers."""
from dataclasses import asdict

from config import MatchConfig, MATCH_WEIGHTS, MATCH_VERSION
from .adapter import fingerprint
from .matching import decide_match


class MatchingService:
    def __init__(self, config=None, *, past_only=False):
        self.config = config or MatchConfig()
        self.past_only = past_only
        self.config_values = {**asdict(self.config), "weights": MATCH_WEIGHTS,
                              "match_version": MATCH_VERSION}
        if past_only:
            self.config_values["past_only"] = True
        self.config_id = fingerprint(self.config_values)

    def decide(self, article, repository, articles, model):
        candidates = [] if article["reasons"] else repository.find_candidates(
            article, self.config, articles)
        if self.past_only:
            candidates = [c for c in candidates
                          if c["anchor_published_at"] <= article["published_at"]]
        decision = decide_match(article, candidates, model, self.config)
        return {**decision, "config_fingerprint": self.config_id,
                "model_fingerprint": model.fingerprint, "match_version": MATCH_VERSION}
