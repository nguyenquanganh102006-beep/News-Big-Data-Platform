import html
import re
import unicodedata
from config import Decision

from bs4 import BeautifulSoup

def normalize(text: str | None) -> str:
    text = BeautifulSoup(html.unescape(text or ""), "html.parser").get_text(" ", strip=True)
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text).lower()).strip()


def classify_accident(title: str | None, description: str | None = None) -> Decision:
    """Conservative lexical baseline; no source/URL/sample-label lookup."""
    headline = normalize(title)
    # Plain RSS text can contain related headlines. Limit fallback to the lead.
    lead = re.split(r"[.!?](?:\s|$)", normalize(description), maxsplit=1)[0]
    text = f"{headline} {lead}"

    def result(label, reason, evidence=headline):
        return Decision(label, reason, evidence)

    if not headline:
        return result("uncertain", "missing_title")
    if re.search(r"có được|thế nào\?|phải làm gì|bao nhiêu|phân biệt|đúng luật", headline):
        return result("not_accident", "advice_or_hypothetical")
    if re.search(r"suýt (?:gây|dẫn đến|va chạm|tông|đâm)", text):
        return result("not_accident", "near_miss")
    if re.search(r"điện giật|kiện hàng rơi|trâu húc|con trâu|leo núi|nhảy cầu|chờ thân nhân", text):
        return result("not_accident", "nontraffic_event")
    if re.search(r"(?:lật|chìm) (?:phà|tàu)|tàu chìm|cầu cảng|xe múc.*(?:lật|thi công)", text):
        return result("uncertain", "unresolved_transport_or_worksite_scope")
    if re.search(r"(?:xe.*cháy|cháy.*xe)", headline) and not re.search(r"va chạm|tông|đâm", headline):
        return result("uncertain", "vehicle_fire_scope")
    if re.search(r"kéo giảm|thống kê|\d+ tháng.*tai nạn|tai nạn.*sau (?:một|\d+) tháng", headline):
        return result("not_accident", "aggregate_statistics")

    vehicle = bool(re.search(r"\bxe\b|ô\s*tô|ôtô|taxi|container|cabin|phương tiện", text))
    crash = r"va chạm|tông|đâm (?:vào|trúng|nhau)|cán (?:người|tử vong|qua)|lao (?:vào|trúng)|lật (?:xe|ngửa)|ngã xe"
    if vehicle and re.search(crash, headline):
        return result("accident", "vehicle_and_actual_impact_in_title")
    if re.search(r"(?:vụ|sau) tai nạn|do tngt|gây tai nạn", headline) and re.search(r"giao thông|cao tốc|tỉnh lộ|quốc lộ|xe|tngt", text):
        return result("accident", "specific_crash_or_followup")
    if re.search(r"ùn (?:tắc|ứ)|biển báo|vạch khoảng cách|quy định|cảnh báo|nguy cơ|thi công|xử phạt|bị phạt", headline):
        return result("not_accident", "non_event_main_topic")
    if vehicle and re.search(crash, lead):
        return result("accident", "vehicle_and_actual_impact_in_lead", lead)
    if re.search(r"tai nạn|va chạm|tngt", headline):
        return result("uncertain", "insufficient_event_evidence")
    return result("not_accident", "no_specific_traffic_crash_evidence")
