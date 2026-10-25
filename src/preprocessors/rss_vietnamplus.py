import polars as pl
from config import DEBUG, RSS_SOURCES
from config.storage import latest_bronze_path
from .identity import add_article_identity
from .dedup import update_silver_history
from .utils import (
    check_valid_characters, 
    normalize_double_quotes,
    extract_anchor_tag_href,
    remove_anchor_tag,
    extract_paragraph_tag_innertext,
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
    # _check_col_atom_link(df)
    # _check_col_updated(df)
    



def _check_col_title(df: pl.DataFrame) -> None:
    print(df['title'].str.len_chars().min())
    print(df['title'].str.len_chars().max())
    
    for idx, row in enumerate(df['title']):
        if check_valid_characters(row):
            continue
        
        if check_valid_characters(normalize_double_quotes(row)):
            if DEBUG:
                print(f"[Info] Normalized {normalize_double_quotes(row)}")
            continue
        
        print(row)
        print(normalize_double_quotes(row))




def _check_col_description(df: pl.DataFrame) -> None:
    # print(df['description'].head())
    # print(df[0, 'description'])
    # print(df[1, 'description'])
    
    # test_desc = df[0, "description"]
    
    # cnt = str(test_desc).count("<a")
    # print(cnt)
    
    description_texts = []
    description_links = []
    
    for idx, row in enumerate(df["description"]):
        text = remove_anchor_tag(row)
        related_links = []
        
        for _ in range(3):
            link = extract_anchor_tag_href(text)
            text = remove_anchor_tag(text)
            related_links.append(link)
        
        joined_links = ";".join(related_links)
        description_links.append(joined_links)

        desc_text = extract_paragraph_tag_innertext(text)
        description_texts.append(desc_text)
        
    
    description_texts_col = pl.Series("description", description_texts)
    description_links_col = pl.Series("description_links", description_links)
    df = df.with_columns(description_texts_col, description_links_col)
    
    print(df.count())
    
    print(df[["link", "description", "description_links"]].head())
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
        if not str(row).startswith("https://www.vietnamplus.vn/"):
            print(row)
            continue
        
        if not str(row).endswith(".vnp"):
            print(row)
            continue



def _check_col_guid(df: pl.DataFrame) -> None:
    # print(df['guid'].head())
    
    uniques = []
    for idx, row in enumerate(df['guid']):
        if row in uniques:
            print(f"Duplicated guid: {row}")
        uniques.append(row)



def _check_col_atom_link(df: pl.DataFrame) -> None:
    print(df['atom_link'].head())



def _check_col_updated(df: pl.DataFrame) -> None:
    print(df["updated"].head())

    df = df.with_columns(
        pl.col("updated").map_elements(
            function=convert_string_to_datetime_utc,
            return_dtype=pl.Datetime(time_unit="us", time_zone="UTC")
        )
    )
    
    mask = df["pub_date"] < df["updated"]
    print(mask.sum())

    # print(df[["pub_date", "updated"]].head())
    


def _process_col_title(df: pl.DataFrame) -> pl.DataFrame:
    df.with_columns(
        pl.col("title").map_elements(
            function=normalize_double_quotes,
            return_dtype=str
        )
    )
    
    return df



def _process_col_description(df: pl.DataFrame) -> pl.DataFrame:
    description_texts = []
    description_links = []
    
    for idx, row in enumerate(df["description"]):
        text = remove_anchor_tag(row)
        related_links = []
        
        for _ in range(3):
            link = extract_anchor_tag_href(text)
            text = remove_anchor_tag(text)
            related_links.append(link)
        
        joined_links = ";".join(related_links)
        description_links.append(joined_links)

        desc_text = extract_paragraph_tag_innertext(text)
        description_texts.append(desc_text)
        
    description_texts_col = pl.Series("description", description_texts)
    description_links_col = pl.Series("description_links", description_links)
    df = df.with_columns(description_texts_col, description_links_col)
    
    return df



def _process_col_pub_date(df: pl.DataFrame) -> pl.DataFrame:
    df = df.with_columns(
        pl.col("pub_date").map_elements(
            function=convert_string_to_datetime_utc,
            return_dtype=pl.Datetime(time_unit="us", time_zone="UTC")
        )
    )
    
    return df



def _process_col_atom_link(df: pl.DataFrame) -> pl.DataFrame:
    df = df.drop("atom_link")
    return df



def _process_col_updated(df: pl.DataFrame) -> pl.DataFrame:
    df = df.with_columns(
        pl.col("updated").map_elements(
            function=convert_string_to_datetime_utc,
            return_dtype=pl.Datetime(time_unit="us", time_zone="UTC")
        )
    )
    
    return df



def rss_vietnamplus_preprocessor(save_file=True) -> pl.DataFrame:
    raw_path = latest_bronze_path("vietnamplus")
    save_path = RSS_SOURCES["vietnamplus"]["silver_save_path"]
    
    if not str(raw_path).endswith(".parquet"):
        if DEBUG:
            print(f"[ERROR] File '{raw_path}' is not .parquet file")
        return
    
    df = pl.read_parquet(raw_path)
    
    df = _process_col_title(df)
    df = _process_col_description(df)
    df = _process_col_pub_date(df)
    df = _process_col_atom_link(df)
    df = _process_col_updated(df)
    
    if DEBUG:
        _check(df)
    
    df = add_article_identity(df, "vietnamplus")

    return update_silver_history(df, save_path, "vietnamplus", save_file=save_file)
    