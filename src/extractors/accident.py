from dataclasses import asdict
import html
import json
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
import unicodedata

from bs4 import BeautifulSoup
import polars as pl

from config import (
    DEBUG, FILTERED_DATA_DIR, EXTRACT_SOURCES, EXTRACT_OUTPUT_DIR, EXTRACT_SCHEMA,
    AccidentExtraction, PROVINCE_ALIASES, VEHICLE_PATTERNS, INCIDENT_PATTERNS,
    NUMBER_WORDS, NUMBER_PATTERN, CASUALTY_PATTERNS, SINGULAR_SUBJECT,
    ADMIN_NAME_PATTERN, ROAD_PATTERN, NEGATION_PATTERN,
    VEHICLE_SPECIFIC_PATTERN, CASUALTY_UNIT, APPROXIMATE_PATTERN,
    NON_SCENE_PATTERN, LOCATION_CONTEXT_PATTERN, ROAD_PREFIX_PATTERN, ADMIN_PREFIXES,
    FACT_NEGATION_PATTERN, HYPOTHETICAL_PATTERN, UPDATE_PATTERN, MULTI_EVENT_PATTERN, CasualtyMention,
    SCENE_PATTERN, SUBJECT_ALIASES, DISJOINT_GROUP_PATTERN, VICTIM_AGE_PATTERN,
    NEAR_MISS_PATTERN, DISJOINT_ROLE_PAIRS,
    ArticleLocation, ARTICLE_LOCATION_SCHEMA, VNEXPRESS_EXTRACT_VERSION,
)
from .vnexpress import fetch_vnexpress_locations


def clean_text(value: str | None) -> str:
    if value is not None and not isinstance(value, str):
        raise ValueError("title and description must be strings or null")
    text = BeautifulSoup(html.unescape(value or ""), "html.parser").get_text(" ", strip=True)
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip()


def _protect_admin_abbreviations(text: str) -> str:
    return re.sub(r"\b(TP|P|Q)\.\s+", r"\1  ", text, flags=re.I)


def clause_prefix(text: str, position: int) -> str:
    return re.split(r"[,;!?\n]|\.(?:\s|$)|\b(?:nhưng|tuy nhiên|song)\b",
                    _protect_admin_abbreviations(text[:position]), flags=re.I)[-1]


def is_non_scene(text: str, position: int) -> bool:
    sentence = re.split(r"[;!?]|\.(?:\s|$)", _protect_admin_abbreviations(text[:position]))[-1]
    # A residence/hospital location can continue after a comma into its province.
    context = re.split(SCENE_PATTERN, sentence, flags=re.I)[-1].replace(",", " ")
    return bool(re.search(NON_SCENE_PATTERN, context, re.I))


def extract_locations(text: str, result: AccidentExtraction) -> None:
    candidates = {}
    for province, aliases in PROVINCE_ALIASES.items():
        for alias in aliases:
            for match in re.finditer(r"(?<!\w)" + re.escape(alias) + r"(?!\w)", text, flags=re.I):
                if not alias.casefold().startswith("tp") and re.search(r"\bTP\.\s*$", text[:match.start()], re.I):
                    continue  # The complete TP. alias handles this location and its road context.
                if re.search(r"\b(?:công an|cảnh sát|đội CSGT)\s+(?:TP\.?\s*)?$", text[:match.start()], re.I):
                    continue
                if re.search(r"\bhướng\s+[^,;.!?]{0,55}[-–]\s*(?:TP\.?\s*)?$", text[:match.start()], re.I):
                    continue
                prefix = clause_prefix(text, match.start())
                if is_non_scene(text, match.start()):
                    continue
                # Exclude a province used as a road's name or endpoint; allow '... tại Hà Nội'.
                road = re.search(ROAD_PREFIX_PATTERN, prefix, flags=re.I)
                in_route = re.search(r"(?:cao tốc|quốc lộ|đường|đại lộ)\b", prefix, flags=re.I)
                explicit = re.search(LOCATION_CONTEXT_PATTERN, prefix, flags=re.I)
                title_start = match.start() == 0 and bool(re.match(r"\s*(?::|[-–])", text[match.end():]))
                alias_city = bool(re.match(r"tp\.?|tphcm", alias, flags=re.I))
                recent = text[max(0, match.start() - 130):match.start()]
                scene_nearby = re.search(
                    r"xảy ra|va chạm|tai nạn|đoạn qua|đoạn thuộc địa phận|trên (?:đường|cao tốc)|qua địa bàn|khi đến|sụp hố|trượt ngã",
                    recent, re.I)
                local_admin = re.search(r"(?:xã|phường|thị trấn|địa phận)\s+[^,()]{1,50}[^)]*$", recent, re.I)
                parenthetical_scene = bool(re.search(r"\(\s*$", recent) and (scene_nearby or local_admin))
                trailing_scene = bool(re.search(r",\s*$", recent) and (scene_nearby or local_admin))
                body_dateline = bool(match.start() == 0 and re.search(
                    r"\b(?:va chạm|tai nạn|tông|đâm|gãy|lật|rơi xuống)\b", text[:180], re.I))
                if road or (in_route and not explicit and not (parenthetical_scene or trailing_scene or body_dateline)):
                    continue
                if explicit or title_start or alias_city or parenthetical_scene or trailing_scene or body_dateline:
                    candidates[province] = match.group()
    if len(candidates) == 1:
        result.province = next(iter(candidates))
        result.evidence["province"] = list(candidates.values())
    elif candidates:
        result.review_reasons.append("ambiguous_province")
    for field, prefix in ADMIN_PREFIXES.items():
        matches = []
        for match in re.finditer(r"(?<!\w)(?i:" + prefix + r")\s+(" + ADMIN_NAME_PATTERN + r")(?!\w)", text):
            before = clause_prefix(text, match.start())
            if is_non_scene(text, match.start()):
                continue
            if field == "ward" and re.search(r"\bthị\s+$", before, flags=re.I):
                continue
            tokens = match.group(1).split()
            name_tokens = []
            for token in tokens:
                if not token[0].isupper() and not token.isdigit():
                    break
                name_tokens.append(token)
            if name_tokens:
                name = " ".join(name_tokens)
                matches.append((name, match.group()[:match.group().index(match.group(1))] + name))
        names = {name for name, _ in matches}
        if len(names) == 1:
            setattr(result, field, next(iter(names)))
            result.evidence[field] = [evidence for _, evidence in matches]
        elif names:
            result.review_reasons.append(f"ambiguous_{field}")


def parse_number(value: str) -> int | None:
    value = value.casefold().strip()
    if re.fullmatch(r"\d+", value):
        return int(value)
    if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", value):
        return int(value.replace(".", "").replace(",", ""))
    tokens = value.split()
    if len(tokens) == 1:
        return NUMBER_WORDS.get(tokens[0])
    hundreds = 0
    if len(tokens) >= 2 and tokens[1] == "trăm" and tokens[0] in NUMBER_WORDS:
        hundreds = NUMBER_WORDS[tokens[0]] * 100
        tokens = tokens[2:]
        if not tokens:
            return hundreds
        if tokens[0] in ("linh", "lẻ"):
            tokens = tokens[1:]
            return hundreds + NUMBER_WORDS[tokens[0]] if len(tokens) == 1 and tokens[0] in NUMBER_WORDS else None
    if tokens and tokens[0] == "mười":
        rest = tokens[1:]
        if not rest or (len(rest) == 1 and rest[0] in NUMBER_WORDS and NUMBER_WORDS[rest[0]] < 10):
            return hundreds + 10 + (NUMBER_WORDS[rest[0]] if rest else 0)
    if len(tokens) in (2, 3) and tokens[0] in NUMBER_WORDS and 2 <= NUMBER_WORDS[tokens[0]] <= 9 and tokens[1] == "mươi":
        if len(tokens) == 2 or (tokens[2] in NUMBER_WORDS and NUMBER_WORDS[tokens[2]] < 10):
            return hundreds + NUMBER_WORDS[tokens[0]] * 10 + (NUMBER_WORDS[tokens[2]] if len(tokens) == 3 else 0)
    return None


def is_negated(text: str, start: int, end: int) -> bool:
    before = clause_prefix(text, start)
    sentence_before = re.split(r"[;!?]|\.(?:\s|$)", text[:start])[-1]
    if re.search(HYPOTHETICAL_PATTERN, sentence_before, flags=re.I):
        return True
    before = re.sub(r"suýt (?:chết|tử vong)", " ", before, flags=re.I)
    return bool(re.search(FACT_NEGATION_PATTERN, before, flags=re.I))


def casualty_mentions(text: str, outcome: str) -> list[CasualtyMention]:
    mentions = []
    travel = r"(?:(?:đi|điều khiển) xe (?:mô tô|máy|đạp điện|đạp)|đi bộ|trên xe)\s+"
    pattern = rf"\b(?P<number>{NUMBER_PATTERN})\s+(?:(?P<subject>{CASUALTY_UNIT})\s+)?(?:khác\s+)?(?:{VICTIM_AGE_PATTERN})?(?:{travel})?(?:(?:đã|bị|đều|cũng|được xác định)\s+)*(?:{outcome})\b"
    for match in re.finditer(pattern, text, flags=re.I):
        before = clause_prefix(text, match.start())
        if re.search(APPROXIMATE_PATTERN, before, flags=re.I) or is_negated(text, match.start(), match.end()):
            continue
        number = parse_number(match.group("number"))
        if number is not None:
            mentions.append(CasualtyMention(number, match.group(), match.start(), match.end(),
                total=bool(re.search(r"(?:tổng(?: cộng)?|số (?:người|nạn nhân)[^,;]*|tăng lên|lên tới)\s*$", before, re.I)),
                incremental=bool(re.search(r"thêm\s*$", before, re.I))))
    # Outcome-first phrasing: 'làm chết 2 người', 'bị thương 3 người'.
    reverse = rf"(?:{outcome})\s+(?:lên\s+)?(?P<number>{NUMBER_PATTERN})(?:\s+(?:{CASUALTY_UNIT}))?\b"
    for match in re.finditer(reverse, text, flags=re.I):
        if any(match.start() < m.end and match.end() > m.start for m in mentions):
            continue
        if is_negated(text, match.start(), match.end()):
            continue
        number = parse_number(match.group("number"))
        if number is not None:
            before = clause_prefix(text, match.start())
            if re.search(APPROXIMATE_PATTERN, before, re.I):
                continue
            mentions.append(CasualtyMention(number, match.group(), match.start(), match.end(),
                total=bool(re.search(r"(?:tổng|số người|số nạn nhân)", before, re.I))))
    for match in re.finditer(rf"\b(?P<subject>{SINGULAR_SUBJECT})\s+(?:(?:đã|bị|cũng)\s+)*(?:{outcome})\b", text, flags=re.I):
        if any(match.start() < m.end and match.end() > m.start for m in mentions):
            continue
        before = clause_prefix(text, match.start())
        if re.search(rf"(?:{NUMBER_PATTERN}|các|những|nhiều|cả)\s*$", before, re.I) or is_negated(text, match.start(), match.end()):
            continue
        subject = match.group("subject").casefold()
        mentions.append(CasualtyMention(1, match.group(), match.start(), match.end(), subject=SUBJECT_ALIASES.get(subject, subject)))
    for match in re.finditer(rf"không (?:có )?(?:ai|người(?: nào)?)\s+(?:bị\s+)?(?:{outcome})", text, flags=re.I):
        mentions.append(CasualtyMention(0, match.group(), match.start(), match.end()))
    for match in re.finditer(r"không (?:có|ghi nhận) thương vong", text, flags=re.I):
        mentions.append(CasualtyMention(0, match.group(), match.start(), match.end()))
    # Explicit singular noun phrases missed by the original role vocabulary.
    singular = rf"(?:một\s+)?(?:{SINGULAR_SUBJECT}|cô gái|bé gái|bé trai|người lái xe|nữ tài xế|nam tài xế|phụ nữ)"
    bridge = rf"(?:\s+(?:{VICTIM_AGE_PATTERN}))?(?:\s*(?:{travel}))?(?:\s+(?:bị (?:ô tô|xe tải|xe máy|xe đầu kéo|xe buýt|xe khách) (?:tông|cán|đâm)(?: trúng)?|chạy ngang qua đường cao tốc))?"
    for match in re.finditer(rf"\b{singular}{bridge}\s+(?:đã\s+|bị\s+)?(?:{outcome})\b", text, re.I):
        if any(match.start() < m.end and match.end() > m.start for m in mentions):
            continue
        before = clause_prefix(text, match.start())
        if re.search(rf"(?:{NUMBER_PATTERN}|các|những|nhiều|cả)\s*$", before, re.I) or is_negated(text, match.start(), match.end()):
            continue
        mentions.append(CasualtyMention(1, match.group(), match.start(), match.end(), subject="singular_person"))
    return mentions


def resolve_mentions(mentions: list[CasualtyMention], text: str) -> tuple[int | None, bool]:
    if not mentions:
        return None, False
    totals = {m.count for m in mentions if m.total}
    if len(totals) == 1:
        total = next(iter(totals))
        return (total, False) if all(m.count <= total for m in mentions) else (None, True)
    if any(m.incremental for m in mentions):
        return None, True
    # Distinct explicit roles may be added; repeated mentions of the same role cannot.
    if all(m.subject for m in mentions):
        roles = [m.subject for m in mentions]
        if len(roles) == 2 and frozenset(roles) in DISJOINT_ROLE_PAIRS:
            return sum(m.count for m in mentions), False
        return (1, False) if len(mentions) == 1 else (None, True)
    if len(mentions) == 2 and all(not m.subject for m in mentions) and re.search(DISJOINT_GROUP_PATTERN, text, re.I):
        return sum(m.count for m in mentions), False
    if len(mentions) == 1:
        return mentions[0].count, False
    # Multiple separate numeric groups are ambiguous even when their counts agree.
    return None, True


def extract_casualties(headline: str, lead: str, result: AccidentExtraction) -> None:
    for field, outcome in CASUALTY_PATTERNS.items():
        head = casualty_mentions(headline, outcome)
        body = casualty_mentions(lead, outcome)
        head_value, head_ambiguous = resolve_mentions(head, headline)
        body_value, body_ambiguous = resolve_mentions(body, lead)
        counts = {v for v in (head_value, body_value) if v is not None}
        value = next(iter(counts)) if len(counts) == 1 else None
        ambiguous = head_ambiguous or body_ambiguous or len(counts) > 1
        # Updates without an explicit final total must not reuse a stale headline count.
        if re.search(UPDATE_PATTERN, lead, re.I) and re.search(outcome, lead, re.I):
            totals = {m.count for m in body if m.total}
            if len(totals) == 1:
                value, ambiguous = next(iter(totals)), False
            else:
                ambiguous = True
        if ambiguous:
            value = None
            result.review_reasons.append(f"conflicting_{field}")
        setattr(result, field, value)
        if head or body:
            result.evidence[field] = list(dict.fromkeys(m.evidence for m in head + body))


def article_paragraphs(content: str | None) -> list[str]:
    """Keep paragraph boundaries and discard explicit related-story trailers."""
    if content is not None and not isinstance(content, str):
        raise ValueError("content must be a string or null")
    soup = BeautifulSoup(html.unescape(content or ""), "html.parser")
    for tag in soup.find_all(["script", "style", "aside", "nav"]):
        tag.decompose()
    paragraphs = []
    for raw in soup.get_text("\n", strip=True).splitlines():
        paragraph = clean_text(raw)
        if re.match(r"^(?:TTO\s*[-–]|Đọc thêm\b|Xem thêm\b|Tin liên quan\b|Bài liên quan\b)", paragraph, re.I):
            break
        if paragraph and paragraph not in paragraphs:
            paragraphs.append(paragraph)
    return paragraphs


def supplement_body(result: AccidentExtraction, content: str) -> None:
    paragraphs = article_paragraphs(content)
    # Related-story text without an explicit marker cannot safely be assigned to
    # the current event. Conflicts remain null rather than selecting a maximum.
    parts = [extract_accident(p) for p in paragraphs]
    multi = any("multiple_events_in_article" in p.review_reasons for p in parts)
    if multi:
        result.review_reasons.append("multiple_events_in_article")
    for field in ("province", "district", "ward", "fatalities", "injuries"):
        location = field in ("province", "district", "ward")
        eligible = [(p, raw) for p, raw in zip(parts, paragraphs)
                    if not location or re.search(
                        r"xảy ra|đoạn (?:qua|thuộc)|qua địa bàn|địa phận|khu vực trên thuộc|khi đến|hiện trường|tông|đâm|lật|gãy", raw, re.I)]
        candidates = {getattr(p, field) for p, raw in eligible if getattr(p, field) is not None
                      and (location or getattr(p, field) != 0 or re.search(
                          r"không (?:có|ghi nhận) thương vong|không (?:có )?(?:ai|người nào)\b", raw, re.I))}
        existing = getattr(result, field)
        if existing is not None:
            candidates.add(existing)
        blocked = any(f"conflicting_{field}" in p.review_reasons or
                      f"ambiguous_{field}" in p.review_reasons for p in [result] + [p for p, _ in eligible])
        if len(candidates) > 1 or blocked:
            setattr(result, field, None)
            result.review_reasons.append(f"conflicting_{field}")
        elif candidates:
            setattr(result, field, next(iter(candidates)))
        for p, raw in eligible:
            if field in p.evidence:
                result.evidence.setdefault(field, []).extend(p.evidence[field])
                result.evidence.setdefault(f"{field}_body_context", []).append(raw)
    # Do not interpret traffic diversions, police vehicles or treatment as
    # vehicles involved in the crash. Only add body facts in incident clauses.
    for p, raw in zip(parts, paragraphs):
        if re.search(r"điều tiết|phân luồng|chốt chặn|cứu hộ|cứu nạn", raw, re.I):
            continue
        if not p.incident_types and not re.search(r"liên quan đến các phương tiện gồm", raw, re.I):
            continue
        for field in ("vehicles", "incident_types"):
            setattr(result, field, list(dict.fromkeys(getattr(result, field) + getattr(p, field))))
            result.evidence.setdefault(field, []).extend(p.evidence.get(field, []))
    if "multiple_events_in_article" in result.review_reasons:
        result.fatalities = result.injuries = None
        result.province = None
        result.evidence.pop("province", None)
    for field in ("province", "district", "fatalities", "injuries", "vehicles"):
        if getattr(result, field) is not None and getattr(result, field) != []:
            result.review_reasons = [r for r in result.review_reasons if r != f"missing_{field}"]
        elif f"missing_{field}" not in result.review_reasons:
            result.review_reasons.append(f"missing_{field}")
    if result.incident_types:
        result.review_reasons = [r for r in result.review_reasons if r != "missing_incident_details"]
    result.review_reasons = list(dict.fromkeys(result.review_reasons))
    result.evidence = {k: list(dict.fromkeys(v)) for k, v in result.evidence.items()}


def resolve_scene_province(result: AccidentExtraction, headline: str, lead: str,
                           content: str | None) -> None:
    """Prefer a single explicit incident location over incidental body mentions."""
    if result.province is not None or "multiple_events_in_article" in result.review_reasons:
        return
    title_location = AccidentExtraction()
    lead_location = AccidentExtraction()
    extract_locations(headline, title_location)
    extract_locations(lead, lead_location)
    head_candidates = {p for p in (title_location.province, lead_location.province) if p}
    if len(head_candidates) > 1:
        return
    preferred = next(iter(head_candidates), None)
    if preferred is None and content:
        for paragraph in article_paragraphs(content)[:8]:
            if not re.search(r"xảy ra|đoạn qua|qua địa bàn|địa phận|khi đến|trên (?:đường|cao tốc)|tai nạn|va chạm|tông|đâm|lật|gãy", paragraph, re.I):
                continue
            candidate = AccidentExtraction()
            extract_locations(paragraph, candidate)
            if candidate.province:
                preferred = candidate.province
                break
    if preferred:
        result.province = preferred
        result.evidence.setdefault("province_scene_resolution", []).append(preferred)
        result.review_reasons = [reason for reason in result.review_reasons
                                 if reason not in ("missing_province", "conflicting_province", "ambiguous_province")]


def extract_accident(title: str | None, description: str | None = None,
                     content: str | None = None) -> AccidentExtraction:
    headline, lead = clean_text(title), clean_text(description)
    text = f"{headline}. {lead}"
    result = AccidentExtraction()
    extract_locations(text, result)
    for field, patterns in (("vehicles", VEHICLE_PATTERNS), ("incident_types", INCIDENT_PATTERNS)):
        values, evidence = [], []
        for label, pattern in patterns.items():
            matches = list(re.finditer(r"\b(?:" + pattern + r")\b", text, flags=re.I))
            accepted = []
            for match in matches:
                if field == "incident_types" and is_negated(text, match.start(), match.end()):
                    result.review_reasons.append("negated_incident_mention")
                    continue
                if field == "vehicles":
                    suffix = text[match.end():]
                    if label == "ô tô" and re.match(VEHICLE_SPECIFIC_PATTERN, suffix, flags=re.I):
                        continue
                    if label in ("xe máy", "xe đạp") and re.match(r"\s+điện\b", suffix, re.I):
                        continue
                accepted.append(match.group())
            if accepted:
                values.append(label)
                evidence.extend(accepted)
        if field == "incident_types" and "tong_duoi" in values:
            values = [v for v in values if v != "va_cham"]
        setattr(result, field, values)
        if evidence:
            result.evidence[field] = evidence
    extract_casualties(headline, lead, result)
    if re.match(r"\s*(?:nếu|giả sử|giả định)\b", headline, re.I) or (re.search(NEAR_MISS_PATTERN, headline, re.I) and not lead):
        result.fatalities = result.injuries = None
        result.incident_types = []
        result.review_reasons.append("negation_or_hypothetical_context")
    if re.search(MULTI_EVENT_PATTERN, text, re.I) or re.search(
            r"tin (?:tức )?tai nạn giao thông.*(?:hôm nay|mới nhất)|điểm tin.*tai nạn|^bản tin (?:TNGT|tai nạn)|^(?:toàn cảnh|xem nhanh).*\|",
            headline, re.I):
        result.fatalities = result.injuries = None
        result.province = None
        result.evidence.pop("province", None)
        result.review_reasons.append("multiple_events_in_article")
    if result.injuries is not None and re.search(r"(?:ban đầu|trước đó).*bị thương.*(?:sau đó|tử vong|không qua khỏi)", lead, re.I):
        result.injuries = None
        result.review_reasons.append("injury_status_updated")
    if not result.incident_types:
        result.review_reasons.append("missing_incident_details")
    for field in ("province", "district", "fatalities", "injuries"):
        if getattr(result, field) is None:
            result.review_reasons.append(f"missing_{field}")
    if not result.vehicles:
        result.review_reasons.append("missing_vehicles")
    result.review_reasons = list(dict.fromkeys(result.review_reasons))
    if content:
        supplement_body(result, content)
    resolve_scene_province(result, headline, lead, content)
    if "multiple_events_in_article" in result.review_reasons:
        result.province = None
        if "missing_province" not in result.review_reasons:
            result.review_reasons.append("missing_province")
    return result


def apply_article_location(result: AccidentExtraction, location: ArticleLocation) -> None:
    result.extraction_version = VNEXPRESS_EXTRACT_VERSION
    if "multiple_events_in_article" in result.review_reasons:
        return
    if location.status == "ok" and location.province in PROVINCE_ALIASES:
        result.evidence["province_dateline"] = [location.text or location.province]
        result.evidence["province_dateline_url"] = [location.url] if location.url else []
        if "ambiguous_province" in result.review_reasons or (
                result.province is not None and result.province != location.province):
            result.province = None
            result.review_reasons.append("conflicting_article_province")
            if "missing_province" not in result.review_reasons:
                result.review_reasons.append("missing_province")
        else:
            result.province = location.province
            result.review_reasons = [reason for reason in result.review_reasons if reason != "missing_province"]
    elif result.province is None:
        result.review_reasons.append(f"article_location_{location.status}")
    result.review_reasons = list(dict.fromkeys(result.review_reasons))


def extract_frame(frame: pl.DataFrame, article_locations: list[ArticleLocation] | None = None) -> pl.DataFrame:
    if "title" not in frame.columns:
        raise ValueError("Extraction input must contain title")
    if article_locations is not None and len(article_locations) != frame.height:
        raise ValueError("article_locations must have one entry per input row")
    rows = []
    for index, row in enumerate(frame.iter_rows(named=True)):
        extraction = extract_accident(row["title"], row.get("description"), row.get("content"))
        if "content" in row and not clean_text(row.get("content")):
            extraction.review_reasons.append("missing_body")
        if row.get("accident_label") == "uncertain":
            extraction.review_reasons.append("upstream_scope_uncertain")
        if article_locations is not None:
            apply_article_location(extraction, article_locations[index])
        result = asdict(extraction)
        result["evidence_json"] = json.dumps(result.pop("evidence"), ensure_ascii=False)
        rows.append(result)
    extracted = pl.DataFrame(rows, schema=EXTRACT_SCHEMA)
    output = frame.with_columns(extracted.get_columns())
    if article_locations is not None:
        metadata = pl.DataFrame([
            {"article_location_text": item.text, "article_location_status": item.status,
             "article_location_url": item.url} for item in article_locations
        ], schema=ARTICLE_LOCATION_SCHEMA)
        output = output.with_columns(metadata.get_columns())
    return output


def extract_filtered_files() -> None:
    inputs = {source: Path(FILTERED_DATA_DIR, source, "accident.parquet") for source in EXTRACT_SOURCES}
    for path in inputs.values():
        if not path.is_file():
            raise FileNotFoundError(f"Missing filtered input: {path}. Run filters first.")
    output_dir = Path(EXTRACT_OUTPUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)
    for source, path in inputs.items():
        frame = pl.read_parquet(path)
        locations = fetch_vnexpress_locations(frame) if source == "vnexpress" else None
        result = extract_frame(frame, article_locations=locations)
        with NamedTemporaryFile(dir=output_dir, suffix=".parquet", delete=False) as temporary:
            temporary_path = Path(temporary.name)
        try:
            result.write_parquet(temporary_path)
            temporary_path.replace(output_dir / f"{source}.parquet")
        finally:
            temporary_path.unlink(missing_ok=True)
        if DEBUG:
            print(f"[Extract] source={source}, articles={result.height}")
