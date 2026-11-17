"""Accident event processing."""

from .retrieval import retrieve_candidates


def run_events(*args, **kwargs):
    # Keep the lightweight 3.1 API usable independently of the database runner.
    from .run import run_events as run
    return run(*args, **kwargs)


__all__ = ["retrieve_candidates", "run_events"]
