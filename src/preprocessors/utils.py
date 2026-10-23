from datetime import datetime, timezone, timedelta
import unicodedata
import re

from config import DEBUG

def normalize_vietnamese(text: str) -> str:
    text = unicodedata.normalize("NFD", text.lower())
    text = re.sub(r"[\u0300-\u036f]", "", text)
    return text.replace("đ", "d")


def check_valid_characters(text: str) -> bool:
    text = normalize_vietnamese(text)
    allowed_chars = [
        ' ', '.', ',', '-', ':', 
        '\'', '%', '\"', '/', ';',
        '?', '(', ')',
    ]
    
    for c in text:
        if c in allowed_chars \
            or (c >= 'a' and c <= 'z') \
            or (c >= 'A' and c <= 'Z') \
            or (c >= '0' and c <= '9'): 
                continue
        
        if DEBUG:
            print(f"[Warning] Invalid char: {c}")
        
        return False
    return True


def extract_anchor_tag_href(text: str) -> str:
    target_text = "<a href=\""
    innertext_start_idx = text.find(target_text)
    if innertext_start_idx == -1:
        return ""

    innertext_start_idx += len(target_text)
    innertext_end_idx = text.find("\"", innertext_start_idx)
    if innertext_end_idx == -1:
        return ""
    
    innertext_link = text[innertext_start_idx:innertext_end_idx]
    return innertext_link


def remove_anchor_tag(text: str) -> str:
    start_text = "<a"
    start_idx = text.find(start_text)
    if start_idx == -1:
        if DEBUG:
            print("[Error] '<a' not found")
        return ""
    
    end_text = "</a>"
    end_idx = text.find(end_text)
    if end_idx == -1:
        if DEBUG:
            print("[Error] '</a>' not found")
        return ""
    
    cleaned_text = text[:start_idx] + text[end_idx+len(end_text):]
    return cleaned_text


def convert_string_to_datetime_utc(
    dt_str: str,
    format: str = "%a, %d %b %Y %H:%M:%S %z",
    utc_hours: int = 0
) -> datetime:
    tz = timezone(timedelta(hours=utc_hours))
    dt_utc = datetime.strptime(dt_str, format).replace(tzinfo=tz).astimezone(timezone.utc)
    return dt_utc


def convert_datetime_utc_to_iso_format(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds").replace("+00:00", "Z")

def normalize_double_quotes(text: str) -> str:
    text = text.replace('“', '"')
    text = text.replace('”', '"')
    return text


def extract_paragraph_tag_innertext(text: str) -> str:
    start_text = "<p>"
    innertext_start_idx = text.find(start_text)
    if innertext_start_idx == -1:
        return ""

    innertext_start_idx += len(start_text)

    end_text = "</p>" 
    innertext_end_idx = text.find(end_text, innertext_start_idx)
    if innertext_end_idx == -1:
        return ""
    
    innertext = text[innertext_start_idx:innertext_end_idx]
    return innertext


def capitalize_name(text: str) -> str:
    name_splits = text.split()
    name_upper_splits = [split.capitalize() for split in name_splits]
    name = " ".join(name_upper_splits)
    
    for idx in range(len(name)):
        if name[idx] == '.' and idx+1 < len(name):
            name = name[:idx+1] + name[idx+1].upper() + name[idx+2:]
    
    return name

