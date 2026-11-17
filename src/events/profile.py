"""Evidence extracted from a report; missing facts remain unknown.

These rules describe the incident, not its publisher. They never consult URL,
source, event labels, or a gazetteer mapping places to guessed provinces.
"""

from datetime import date, timedelta, timezone
from functools import lru_cache
import html
import re
import unicodedata

from bs4 import BeautifulSoup


VN_TIME = timezone(timedelta(hours=7))
PROFILE_VERSION = "incident-profile-v1"
NAME = r"[A-ZÀ-ỸĐ][\wÀ-ỹĐđ]*(?:[-–][\wÀ-ỹĐđ]+)?"
PLACE_NAME = rf"{NAME}(?:\s+(?:{NAME}|\d+)){{0,6}}"
PLACE_PATTERNS = {
    "road": rf"(?i:\bđường|\bđại lộ|\bquốc lộ|\bcao tốc)\s+({PLACE_NAME}|\d+[A-Z]?)",
    "tunnel": rf"(?i:\bhầm chui|\bhầm)\s+({PLACE_NAME})",
    "bridge": rf"(?i:\bcầu)\s+({PLACE_NAME})",
    "ward": rf"(?i:\bphường|\bxã|\bthị trấn)\s+({PLACE_NAME}|\d+)",
}
ROLE_PATTERNS = {
    "pedestrian": r"đi bộ|băng qua (?:đường|cao tốc)",
    "pregnant_woman": r"thai phụ|(?:phụ nữ|người phụ nữ|nạn nhân|chị[^,.]{0,15}) (?:mang bầu|mang thai)",
    "student": r"nữ sinh|nam sinh|học sinh",
    "learner_driver": r"học viên|tập lái",
}
SCENE_PATTERNS = {"coastal_road": r"đường ven biển", "underpass": r"hầm chui",
                  "rail_crossing": r"lối đi tự mở|đường ngang|đường sắt"}


def clean(value):
    return " ".join(unicodedata.normalize("NFC", BeautifulSoup(
        html.unescape(value or ""), "html.parser").get_text(" ", strip=True)).split())


def token(value):
    return " ".join(unicodedata.normalize("NFC", value or "").casefold().split())


@lru_cache(maxsize=8192)
def text_profile(text, published_iso):
    places = {}
    for kind, pattern in PLACE_PATTERNS.items():
        found = set()
        for match in re.finditer(pattern, text):
            prefix = text[:match.start()]
            # 'quận Cầu Giấy' is an administrative name, not 'cầu Giấy'.
            if re.search(r"(?:quận|huyện|phường|xã|thị trấn)\s*$", prefix, re.I):
                continue
            context = re.split(r"[.!?;]|va chạm|xảy ra|hiện trường", prefix, flags=re.I)[-1]
            if re.search(r"(?:quê|trú|bệnh viện|điều trị|cấp cứu)[^.!?;]*$", context, re.I):
                continue
            found.add(token(match.group(1)))
        places[kind] = sorted(found)
    lowered = token(text)
    roles = sorted(name for name, pattern in ROLE_PATTERNS.items() if re.search(pattern, lowered))
    scenes = sorted(name for name, pattern in SCENE_PATTERNS.items() if re.search(pattern, lowered))
    # A plate or vehicle model is stronger than a generic vehicle class.
    identifiers = sorted(set(re.findall(r"\b(?:VF\s?\d{1,2}|\d{2}[A-Z]\d?[- ]\d{3,5}(?:\.\d{2})?)\b", text)))
    dates = set()
    if published_iso:
        from datetime import datetime
        reference = datetime.fromisoformat(published_iso).astimezone(VN_TIME).date()
        for match in re.finditer(
            r"(?:\bngày|\bsáng|\btrưa|\bchiều|\btối|\bđêm|\brạng sáng)\s+"
            r"(\d{1,2})[/-](\d{1,2})(?:[/-](\d{4}))?", lowered):
            day, month, year = match.groups()
            possibilities = []
            for y in ([int(year)] if year else [reference.year - 1, reference.year, reference.year + 1]):
                try:
                    candidate = date(y, int(month), int(day))
                except ValueError:
                    continue
                if candidate <= reference + timedelta(days=1):
                    possibilities.append(candidate)
            if possibilities:
                dates.add(min(possibilities, key=lambda d: abs((d - reference).days)).isoformat())
    specific = bool(re.search(r"va chạm|tông|đâm|(?:vụ|sau) tai nạn|tai nạn (?:giao thông )?liên hoàn", lowered))
    return {"places": places, "roles": roles, "scenes": scenes,
            "identifiers": [token(v).replace(" ", "") for v in identifiers],
            "incident_dates": sorted(dates), "specific_incident": specific}


def incident_profile(article):
    text = clean(article.get("text") or f"{article.get('title', '')}. {article.get('description', '')}")
    stamp = article.get("published_at")
    return text_profile(text, stamp.isoformat() if stamp else "")


def compare_profiles(left, right):
    a, b = incident_profile(left), incident_profile(right)
    conflicts, shared_places = [], []
    for field in ("province", "district", "ward"):
        x, y = token(left.get(field)), token(right.get(field))
        if x and y and x != y:
            conflicts.append(f"conflicting_{field}")
    for kind in PLACE_PATTERNS:
        x, y = set(a["places"][kind]), set(b["places"][kind])
        if x & y:
            shared_places.extend(f"{kind}:{place}" for place in sorted(x & y))
        # Multiple mentions may be route endpoints or background incidents.
        # A single incompatible named scene on each side is a reliable veto.
        elif len(x) == len(y) == 1:
            conflicts.append(f"conflicting_{kind}")
    x, y = set(a["incident_dates"]), set(b["incident_dates"])
    if len(x) == len(y) == 1 and not x & y:
        conflicts.append("conflicting_incident_date")
    roles = sorted(set(a["roles"]) & set(b["roles"]))
    scenes = sorted(set(a["scenes"]) & set(b["scenes"]))
    identifiers = sorted(set(a["identifiers"]) & set(b["identifiers"]))
    same_province = bool(left.get("province") and left.get("province") == right.get("province"))
    delta = abs((left["published_at"] - right["published_at"]).total_seconds()) / 3600
    same_day = left["published_at"].astimezone(VN_TIME).date() == right["published_at"].astimezone(VN_TIME).date()
    dates_agree = bool(x & y)
    vehicles = bool(set(left.get("vehicles", [])) & set(right.get("vehicles", [])))
    # Require corroboration from a different family of attributes. Same topic,
    # province, date and generic vehicle class alone do not identify an event.
    named_identity = bool(shared_places and vehicles and (dates_agree or same_day))
    identifier_identity = bool(identifiers and (roles or shared_places) and same_province and delta <= 24)
    context_identity = bool(roles and scenes and vehicles and same_province and (dates_agree or same_day) and delta <= 12)
    strength = 1.0 if named_identity or identifier_identity else (0.85 if context_identity else None)
    return {"conflicts": sorted(set(conflicts)), "shared_places": shared_places,
            "shared_roles": roles, "shared_scenes": scenes, "shared_identifiers": identifiers,
            "same_incident_date": dates_agree, "same_publication_day": same_day,
            "identity": strength, "delta_hours": delta,
            "left_profile": a, "right_profile": b}
