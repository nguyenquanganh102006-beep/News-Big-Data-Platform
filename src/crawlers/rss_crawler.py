import feedparser
import polars as pl

from config import (
    DEBUG, DEFAULT_STRING, 
    handleMetadateKey, handleColonKey, handleDuplicateKey, handleConvertCamelToSnake,
)


def crawl_rss(
    rss_url: str, 
    meta_keys: list[str], 
    entry_keys: list[str], 
    Model, 
    save_path: str = ""
) -> pl.DataFrame:
    """
    Params:
        rss_url (str): RSS Feed url (.rss)
        meta_keys (list[str]): Keys of the Feed's metadata
        entry_keys (list[str]): Keys to take from each <item> (entry) in the Feed
        Model (BaseModel): Specific schema of the entry
        save_path (str): Don't save if not specified (empty string)
    
    Returns:
        articles (pl.DataFrame): List of article
    """
    
    if DEBUG:
        print(f"[Info] Crawling RSS: {rss_url}")
    
    feed = feedparser.parse(rss_url)

    if DEBUG:
        if feed.bozo:
            print("[Warning] RSS may be invalid")

        print(f"[Info] Title: {feed.feed.get('title', DEFAULT_STRING)}")
        print(f"[Info] Description: {feed.feed.get('description', DEFAULT_STRING)}")
    
    
    # Get metadata
    metadata = {}
    for key in meta_keys:
        cleaned_key = handleConvertCamelToSnake(key)
        cleaned_key = handleColonKey(cleaned_key)
        meta_key = handleMetadateKey(cleaned_key)
        
        if meta_key in metadata.keys():
            meta_key = handleDuplicateKey(meta_key)
        
        metadata[meta_key] = feed.feed.get(key, None)
    
    
    # Get items
    articles = []
    for entry in feed.entries:
        article = { **metadata }
        
        for key in entry_keys:
            cleaned_key = handleConvertCamelToSnake(key)
            cleaned_key = handleColonKey(cleaned_key)
            
            if cleaned_key in article.keys():
                cleaned_key = handleDuplicateKey(cleaned_key)
            
            article[cleaned_key] = entry.get(key, None)
        
        
        # Validate
        articleModel = Model(**article)
        article = articleModel.model_dump()
        
        articles.append(article)
    
    
    if DEBUG:
        print(f"[Info] Crawled {len(articles)} items")
    
    
    df = pl.DataFrame(articles)
    
    if save_path:
        df.write_parquet(save_path)
    
    return df
    
    
    
    