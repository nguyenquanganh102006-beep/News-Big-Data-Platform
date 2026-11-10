import html
import re
import unicodedata
from config import Decision

from bs4 import BeautifulSoup

def normalize(text: str | None) -> str:
    text = BeautifulSoup(html.unescape(text or ""), "html.parser").get_text(" ", strip=True)
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text).lower()).strip()


def description_lead(description):
    soup = BeautifulSoup(html.unescape(description or ""), "html.parser")
    for tag in soup(["script", "style", "ul", "ol", "aside", "nav"]):
        tag.decompose()
    paragraph = soup.find("p")
    text = normalize(str(paragraph if paragraph is not None else soup))
    text = re.sub(r"\b(tp|ql|q|p)\.\s*", r"\1 ", text)
    return re.split(r"[.!?](?:\s|$)", text, maxsplit=1)[0]


def has(pattern, text):
    return re.search(r"(?<!\w)(?:" + pattern + r")(?!\w)", text) is not None


def classify_accident(title: str | None, description: str | None = None) -> Decision:
    """Conservative lexical baseline; no source/URL/sample-label lookup."""
    headline = normalize(title)
    # Plain RSS text can contain related headlines. Limit fallback to the lead.
    lead = description_lead(description)
    text = f"{headline} {lead}"

    def result(label, reason, evidence=headline):
        return Decision(label, reason, evidence)

    if not headline:
        return result("uncertain", "missing_title")
    # User-confirmed scope: road incidents only, exclude follow-up-only stories.
    if has(r"khởi tố|truy tố|xét xử|tuyên án|rà soát|khắc phục|cứu hộ|cứu nạn", headline) or re.search(
            r"^(?:[^:]{1,40}:\s*)?(?:điều tra|giải cứu|xử lý|xây cầu|sửa chữa)\b", headline):
        return result("not_accident", "followup_excluded")
    if has(r"sau (?:vụ|sự cố).*?(?:dự kiến|xây|sửa)|dự kiến.*sau sự cố", headline):
        return result("not_accident", "followup_excluded")
    if has(r"máy bay|trực thăng", headline) and has(r"rơi|cháy|va chạm|tai nạn", text):
        return result("not_accident", "outside_road_scope")
    if re.search(r"có được|thế nào\?|phải làm gì|bao nhiêu|phân biệt|đúng luật|có mặc nhiên|quyền ưu tiên|liệu có an toàn", headline):
        return result("not_accident", "advice_or_hypothetical")
    near_pattern = r"suýt\s+(?:(?:gây|dẫn đến)\s+)?(?:ra\s+)?(?:va chạm|tông|đâm|tai nạn)[^.!?;]*"
    actual = re.sub(near_pattern, "", text)
    if actual != text and not has(r"va chạm|tông|đâm vào|lật xe", actual):
        return result("not_accident", "near_miss")
    if re.search(r"điện giật|kiện hàng rơi|trâu húc|con trâu|leo núi|nhảy cầu|chờ thân nhân", text):
        return result("not_accident", "nontraffic_event")
    watercraft = has(r"tàu|thuyền|sà lan|phà|ca nô|cano|xuồng", headline)
    crossing = has(r"xe máy|ô tô|ôtô|xe tải|xe đạp", headline) and has(r"đâm|tông|va chạm", headline)
    if watercraft and has(r"va chạm|đâm|chìm|lật|mắc cạn|trôi dạt|cháy", text) and not crossing:
        return result("not_accident", "outside_road_scope")
    if re.search(r"xe múc.*(?:lật|thi công)|(?:máy xúc|xe cuốc|xe nâng).*(?:đang thi công|khi thi công|tháo dỡ|trong nhà máy)", text):
        return result("not_accident", "worksite_excluded")
    if has(r"cháy gara|cháy.*xưởng sửa chữa|cháy.*nhà máy", headline):
        return result("not_accident", "nontraffic_fire")
    if re.search(r"kéo giảm|thống kê|diễn tập|giả định|\d+ tháng.*tai nạn|tai nạn.*sau (?:một|\d+) tháng", headline):
        return result("not_accident", "aggregate_statistics")
    if has(r"nguy cơ|có thể|phòng tránh|nếu|chỉ cần", headline):
        return result("not_accident", "hypothetical_or_prevention")

    vehicle = has(r"xe|ô\s*tô|ôtô|taxi|container|cabin|phương tiện|máy cày|rơ.moóc|mô tô|môtô", text)
    road = has(r"trên đường|cao tốc|quốc lộ|tỉnh lộ|đang lưu thông|đang di chuyển|qua cầu|ven đường|bên đường|lòng đường|đường phố", text)
    if vehicle and has(r"cháy|bốc cháy|thiêu rụi", headline):
        return result("accident" if road else "uncertain",
                      "road_vehicle_fire" if road else "road_context_missing")
    crash = r"va chạm|va quẹt|đụng|húc|(?<!bê )tông|đâm (?:vào|trúng|nhau|liên hoàn|trực diện|sầm)|đối đầu|cán (?:người|tử vong|qua|chết)|lao (?:vào|trúng|thẳng vào)|lật (?:xe|ngửa)|ngã xe|té xe|mất lái|ủi văng"
    departure = r"(?:lao|rơi|văng|lăn) xuống (?:ruộng|kênh|sông|vực|mương|hồ|suối)"
    if vehicle and (has(crash, headline) or has(departure, headline)):
        return result("accident", "vehicle_and_actual_impact_in_title")
    if has(r"(?:vụ|sau|gây|bị|gặp) tai nạn|do tngt|tai nạn (?:giữa|liên hoàn|đối đầu)", headline) and (vehicle or has(r"giao thông|cao tốc|tỉnh lộ|quốc lộ|tngt", text)):
        return result("accident", "specific_crash_or_followup")
    if has(r"tai nạn", headline) and vehicle and has(r"tử vong|thiệt mạng|thương vong|bị thương|nguy kịch", text):
        return result("accident", "specific_accident_with_vehicle_and_outcome")
    if has(r"sau sự cố", headline) and vehicle and has(r"sập cầu|rơi xuống|va chạm", lead):
        return result("accident", "specific_crash_followup")
    if re.search(r"ùn (?:tắc|ứ)|biển báo|vạch khoảng cách|quy định|cảnh báo|nguy cơ|thi công|xử phạt|bị phạt|dự kiến thông xe|đường chính", headline):
        return result("not_accident", "non_event_main_topic")
    impact_lead = re.sub(r"bê tông|nhánh (?:đường )?đâm vào[^,.;]*", "", lead)
    if vehicle and (has(crash, impact_lead) or has(departure, impact_lead)):
        if not has(r"có thể|tiềm ẩn|nguy cơ|nếu|chỉ cần|nhằm|hạn chế tai nạn", impact_lead):
            return result("accident", "vehicle_and_actual_impact_in_lead", lead)
    if vehicle and has(r"(?:cây|đá|vật nặng|biển quảng cáo).*(?:đổ|rơi|đè).*?(?:ô tô|ôtô|xe)", text):
        return result("accident" if road else "uncertain",
                      "object_struck_road_vehicle" if road else "road_context_missing")
    if re.search(r"tai nạn|va chạm|tngt", headline):
        return result("uncertain", "insufficient_event_evidence")
    return result("not_accident", "no_specific_traffic_crash_evidence")
