import polars as pl
from config import DEBUG, RSS_SOURCES
from .utils import (
    check_valid_characters, 
    extract_anchor_tag_href,
    remove_anchor_tag,
    convert_string_to_datetime_utc,
    convert_datetime_utc_to_iso_format,
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
    # _check_col_guid(df)



def _check_col_title(df: pl.DataFrame) -> None:
    print(df['title'].str.len_chars().min())
    print(df['title'].str.len_chars().max())
    
    for idx, row in enumerate(df['title']):
        if check_valid_characters(row):
            continue
        print(row)



def _check_col_description(df: pl.DataFrame) -> None:
    link_counts = []
    description_links = []
        
    for idx, row in enumerate(df['description']):
        description_links.append(extract_anchor_tag_href(row))
        link_counts.append(str(row).count("href"))
        
        if check_valid_characters(row):
            continue
        
        print(row)
    
    link_count_column = pl.Series("link_count", link_counts)
    df.insert_column(
        index=df.get_column_index("link")+1, 
        column=link_count_column
    )
    
    description_link_column = pl.Series("description_link", description_links)
    df.insert_column(
        index=df.get_column_index("link")+1, 
        column=description_link_column
    )
    
    print(df.count())
    print(df["link_count"].sum())
    print((df["link"] == df["description_link"]).count())
    
    print(df[["link", "description_link", "link_count"]].head())
    print(df.columns)
    
    print(df["description"].str.len_chars().min())
    print(df["description"].str.len_chars().max())



def _check_col_pub_date(df: pl.DataFrame) -> None:
    utc_pub_dates = []
    iso_pub_dates = []
    
    for idx, row in enumerate(df["pub_date"]):
        if isinstance(row, str):
            utc_dt = convert_string_to_datetime_utc(row)
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
    
    for idx, row in enumerate(df["link"]):
        if not str(row).startswith("https://vnexpress.net/"):
            print(row)
            continue
        
        if not str(row).endswith(".html"):
            print(row)
            continue



def _check_col_guid(df: pl.DataFrame) -> None:
    # print(df['guid'].head())
    
    uniques = []
    for idx, row in enumerate(df['guid']):
        if row in uniques:
            print(f"Duplicated guid: {row}")
        uniques.append(row)
    


def _process_col_description(df: pl.DataFrame) -> pl.DataFrame:
    for idx, row in enumerate(df['description']):
        cleaned_text = remove_anchor_tag(row)
        if cleaned_text == "":
            if DEBUG:
                print(f"[Warning] Row {idx} failed to remove <a> tag")
            continue
        df[idx, "description"] = cleaned_text
    
    return df



def _process_col_pub_date(df: pl.DataFrame) -> pl.DataFrame:
    df = df.with_columns(
        pl.col("pub_date").map_elements(
            function=convert_string_to_datetime_utc,
            return_dtype=pl.Datetime(time_unit="us", time_zone="UTC")
        )
    )
    
    return df



def rss_vnexpress_preprocessor(save_file=True) -> pl.DataFrame:
    raw_path = RSS_SOURCES["vnexpress"]["bronze_save_path"]
    save_path = RSS_SOURCES["vnexpress"]["silver_save_path"]
    
    if not str(raw_path).endswith(".parquet"):
        if DEBUG:
            print(f"[ERROR] File '{raw_path}' is not .parquet file")
        return
    
    df = pl.read_parquet(raw_path)
    
    df = _process_col_description(df)
    df = _process_col_pub_date(df)
    
    if DEBUG:
        _check(df)
    
    if save_file:
        df.write_parquet(save_path)
    
    return df
    