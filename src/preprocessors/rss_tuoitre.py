import polars as pl
from config import DEBUG, RSS_SOURCES
from config import latest_bronze_path
from .utils import dedup_add_article_identity
from .utils import dedup_update_silver_history
from .utils import (
    check_valid_characters, 
    convert_string_to_datetime_utc,
    convert_datetime_utc_to_iso_format,
    capitalize_name,
)


def _check(df: pl.DataFrame):
    """"""
    # print(df.head())
    # print(df.describe())
    print(df.columns)
    
    # _check_col_title(df)
    # _check_col_description(df)
    # _check_col_pub_date(df)
    # _check_col_link(df)
    # _check_col_author(df)
    



def _check_col_title(df: pl.DataFrame) -> None:
    print(df['title'].str.len_chars().min())
    print(df['title'].str.len_chars().max())
    
    for idx, row in enumerate(df['title']):
        if check_valid_characters(row):
            continue
        
        print(row)



def _check_col_description(df: pl.DataFrame) -> None:
    print(df['description'].head())
    
    # print(df["description"].str.len_chars().min())
    # print(df["description"].str.len_chars().max())

    for idx, row in enumerate(df['description']):
        if check_valid_characters(row):
            continue
        
        print(row)



def _check_col_pub_date(df: pl.DataFrame) -> None:
    print(df['pub_date'].head())
    
    # print(repr(df[0, 'pub_date']))
    
    utc_pub_dates = []
    iso_pub_dates = []
    
    for idx, row in enumerate(df["pub_date"]):
        if isinstance(row, str):
            utc_dt = convert_string_to_datetime_utc(
                row, 
                format=""
                )
        else:
            utc_dt = row
        utc_pub_dates.append(utc_dt)
        
        iso_dt = convert_datetime_utc_to_iso_format(utc_dt)
        iso_pub_dates.append(iso_dt)

    pub_date_col = pl.Series("pub_date", utc_pub_dates)
    pub_date_iso_col = pl.Series("pub_date_iso", iso_pub_dates)
    
    df = df.with_columns(pub_date_col, pub_date_iso_col)
    
    print(df[["pub_date", "pub_date_iso"]].head())
    print(df["pub_date"].map_elements(lambda x: convert_datetime_utc_to_iso_format(x)).head())

    print(df["pub_date_iso"].dt.min())
    print(df["pub_date_iso"].dt.max())



def _check_col_link(df: pl.DataFrame) -> None:
    # print(df["link"].head())
    # print(df[0, "link"])
    # return
    
    for idx, row in enumerate(df["link"]):
        if not str(row).startswith("https://tuoitre.vn/"):
            print(row)
            continue
        
        if not str(row).endswith(".htm"):
            print(row)
            continue



def _check_col_author(df: pl.DataFrame) -> None:
    # print(df['author'].head(10))
    # print(repr(df[0, 'author']))
    # print(df["author"].unique())
    
    cnt = 0
    for row in df['author']:
        # if check_valid_characters(row):
        #     continue
        
        end_idx = str(row).find('\u2b50')
        if end_idx != -1:
            row = row[:end_idx]
        
        text = capitalize_name(row)
        print(text)
        
        cnt += 1
        
    print(cnt)
    


def _process_col_pub_date(df: pl.DataFrame) -> pl.DataFrame:
    format = "%m/%d/%Y %I:%M:%S %p"
    df = df.with_columns(
        pl.col("pub_date").map_elements(
            function=lambda x: convert_string_to_datetime_utc(x, format, 7),
            return_dtype=pl.Datetime(time_unit="us", time_zone="UTC")
        )
    )
    
    return df



def _process_col_author(df: pl.DataFrame) -> pl.DataFrame:
    authors = []
    verifieds = []
    
    for row in df['author']:
        end_idx = str(row).find('\u2b50')
        if end_idx != -1:
            row = row[:end_idx]
            verifieds.append(True)
        else:
            verifieds.append(False)
        
        text = capitalize_name(row)
        authors.append(text)

    author_col = pl.Series("author", authors)
    verified_col = pl.Series("verified", verifieds)
    df = df.with_columns(author_col, verified_col)

    return df



def rss_tuoitre_preprocessor(save_file=True, crawled_date: str | None = None) -> pl.DataFrame:
    raw_path = latest_bronze_path("tuoitre", crawled_date)
    save_path = RSS_SOURCES["tuoitre"]["silver_save_path"]
    
    if not str(raw_path).endswith(".parquet"):
        if DEBUG:
            print(f"[ERROR] File '{raw_path}' is not .parquet file")
        return
    
    df = pl.read_parquet(raw_path)
    
    df = _process_col_pub_date(df)
    df = _process_col_author(df)
    
    if DEBUG:
        _check(df)
    
    df = dedup_add_article_identity(df, "tuoitre")

    return dedup_update_silver_history(df, save_path, "tuoitre", save_file=save_file)
    