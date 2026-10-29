from .rss_vnexpress import rss_vnexpress_preprocessor
from .rss_vietnamplus import rss_vietnamplus_preprocessor
from .rss_tuoitre import rss_tuoitre_preprocessor

from .utils import (
    normalize_vietnamese,
    check_valid_characters,
    extract_anchor_tag_href,
    remove_anchor_tag,
    convert_string_to_datetime_utc,
    convert_datetime_utc_to_iso_format,
    normalize_double_quotes,
    extract_paragraph_tag_innertext,
    capitalize_name,
)


__all__ = [
    "rss_vnexpress_preprocessor", 
    "rss_vietnamplus_preprocessor", 
    "rss_tuoitre_preprocessor",
    
    "normalize_vietnamese", "check_valid_characters", "extract_anchor_tag_href", 
    "remove_anchor_tag", "convert_string_to_datetime_utc", "convert_datetime_utc_to_iso_format", 
    "normalize_double_quotes", "extract_paragraph_tag_innertext", "capitalize_name",
]

from .utils import dedup_normalize_article_url, dedup_make_article_key, dedup_add_article_identity, dedup_batch, dedup_new_articles_only, dedup_update_silver_history

__all__ += ['dedup_normalize_article_url', 'dedup_make_article_key', 'dedup_add_article_identity', 'dedup_batch', 'dedup_new_articles_only', 'dedup_update_silver_history']
