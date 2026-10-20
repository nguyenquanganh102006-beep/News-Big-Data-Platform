import re
from .schemas import (
    RssVnexpressBronzeModel,
    RssVietnamplusBronzeModel,
    RssTuoitreBronzeModel,
    RssDantriBronzeModel,
    RssThanhnienBronzeModel,
    RssBaoxaydungBronzeModel,
    RssTienphongBronzeModel,
)

FEEDPARSER_MAP_FIELDS = {
    "pubDate": "published",
}

RSS_SOURCES = {
    "vnexpress": {
        "url": "https://vnexpress.net/rss/thoi-su.rss",
        "meta_keys": ["title", "description", "pubDate", "generator", "link"],
        "entry_keys": ["title", "description", "pubDate", "link", "guid"],
        "schema": RssVnexpressBronzeModel,
    },
    "vietnamplus": {
        "url": "https://www.vietnamplus.vn/rss/xahoi/giaothong-358.rss",
        "meta_keys": ["title", "copyright", "link", "lastBuildDate", "pubDate", "description", "language", "docs", "managingEditor", "webMaster", "ttl", "atom:link"],
        "entry_keys": ["title", "description", "pubDate", "updated", "link", "atom:link", "guid"],
        "schema": RssVietnamplusBronzeModel,
    },
    "tuoitre": {
        "url": "https://tuoitre.vn/thoi-su.rss",
        "meta_keys": ["title", "description", "link", "language", "copyright", "lastBuildDate", "docs", "generator", "ttl"],
        "entry_keys": ["title", "description", "pubDate", "link", "author"],
        "schema": RssTuoitreBronzeModel,
    },
    "dantri": {
        "url": "https://dantri.com.vn/rss/thoi-su.rss",
        "meta_keys": ["title", "atom:link", "link", "description", "lastBuildDate", "pubDate", "language", "copyright", "sy:updatePeriod", "sy:updateFrequency", "ttl"],
        "entry_keys": ["title", "description", "pubDate", "link", "guid", "dc:creator", "category"],
        "schema": RssDantriBronzeModel,
    },
    "thanhnien": {
        "url": "https://thanhnien.vn/rss/xe/xe-giao-thong.rss",
        "meta_keys": ["title", "link", "description", "atom:link", "copyright", "generator", "pubDate", "language", "lastBuildDate", "atom:link", "ttl"],
        "entry_keys": ["title", "description", "pubDate", "link", "guid"],
        "schema": RssThanhnienBronzeModel,
    },
    "baoxaydung": {
        "url": "https://baoxaydung.vn/rss/an-toan-giao-thong/giao-thong-24h.rss",
        "meta_keys": ["title", "link", "description", "atom:link", "copyright", "generator", "pubDate", "language", "lastBuildDate", "atom:link", "ttl"],
        "entry_keys": ["title", "description", "pubDate", "link", "guid"],
        "schema": RssBaoxaydungBronzeModel,
    },
    "tienphong": {
        "url": "https://tienphong.vn/rss/nstd-giao-thong-do-thi-244.rss",
        "meta_keys": ["title", "copyright", "link", "lastBuildDate", "pubDate", "description", "language", "docs", "managingEditor", "webMaster", "ttl", "atom:link"],
        "entry_keys": ["title", "description", "pubDate", "updated", "link", "atom:link", "guid"],
        "schema": RssTienphongBronzeModel,
    },
}

HTML_SOURCES = {
    "vnexpress": {
        "url": "https://vnexpress.net/tag/tai-nan-giao-thong-1621979",
    },
    "vietnamplus": {
        "url": "https://www.vietnamplus.vn/tag/tai-nan-giao-thong-tag2648.vnp",
    },
    "dantri": {
        "url": "https://dantri.com.vn/tim-kiem/tai%2Bn%E1%BA%A1n%2Bgiao%2Bth%C3%B4ng.htm",
    },
    
}


def handleMetadateKey(key: str) -> str:
    """
    e.g. key -> meta_key
    """
    return "meta_" + key


def handleColonKey(key: str) -> str:
    """
    e.g. atom:link -> atom_link
    """
    return "_".join(key.split(":"))


def handleDuplicateKey(key: str) -> str:
    """
    e.g. key -> key_2, key_1 -> key_2, key_9 -> key_10
    """
    
    if key[-1].isdigit():
        idx = int(key[-1]) + 1
        if idx == 10:
            idx = 0
            key = handleDuplicateKey(key[:-1])
        idx = str(idx)
    else:
        idx = "_2"
    return key + idx


def handleConvertCamelToSnake(key: str) -> str:
    """
    e.g. pubDate -> pub_date
    """
    return re.sub(r'([A-Z])', r'_\1', key).lower().lstrip('_')



