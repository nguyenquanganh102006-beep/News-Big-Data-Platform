"""Shared event matching options: embeddings on unless explicitly disabled."""

from config import DEFAULT_SEMANTIC_MODEL, MatchConfig


def add_matching_arguments(parser):
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--semantic-model", default=DEFAULT_SEMANTIC_MODEL,
                      help=f"FastEmbed sentence model (default: {DEFAULT_SEMANTIC_MODEL})")
    mode.add_argument("--no-embedding", action="store_true",
                      help="Explicitly use incident evidence and TF-IDF without embeddings")
    parser.add_argument("--model-cache", help="Embedding model cache directory")


def matching_config(args):
    return MatchConfig(semantic_model=None if args.no_embedding else args.semantic_model,
                       semantic_cache_dir=args.model_cache)
