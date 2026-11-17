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


def _classify_v3(title: str | None, description: str | None = None) -> Decision:
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
    crash = r"va chạm|va quẹt|va quệt|đụng|húc|(?<!bê )tông|đâm (?:vào|trúng|nhau|liên hoàn|trực diện|sầm)|đối đầu|cán (?:người|tử vong|qua|chết)|lao (?:vào|trúng|thẳng vào)|lật (?:xe|ngửa)|ngã xe|té xe|mất lái|ủi văng"
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


# Rules are general linguistic patterns; audited article identities are never
# consulted by the classifier. Full body is a bounded fallback after topic checks.
ROAD_VEHICLE = r"xe (?:máy|mô tô|môtô|đạp|khách|buýt|bus|tải|ben|bồn|con|đầu kéo|container|bán tải|giường nằm|cứu thương|cứu hỏa|cứu hoả|điện|hoa|hơi|van)|ô\s*tô|ôtô|mô tô|môtô|taxi|suv|sedan|pickup|crossover|container|rơ.moóc|máy cày|người đi bộ"
ROAD_CONTEXT = r"cao tốc|quốc lộ|tỉnh lộ|đường tỉnh|đường bộ|giao thông|trên đường|xuống đường|ngang đường|mặt đường|giữa đường|bên đường|ven đường|người đi đường|trên cầu|qua cầu|giao lộ|ngã tư|ngã ba|đường ngang|đang (?:chạy|lưu thông|di chuyển)|đi xe máy|trạm xăng|cây xăng|đèo|vỉa hè|lòng đường"
IMPACT = (r"va chạm|va quẹt|va quệt|đụng|húc|(?<!bê )tông|đấu đầu|đối đầu|"
          r"đâm (?:vào|trúng|nhau|liên hoàn|trực diện|sầm|vỡ|mạnh|đầu|nát|dồn toa)|"
          r"cán (?:người|tử vong|qua|chết|trúng)|cuốn.{0,40}gầm|hất (?:văng|ngã)|quật (?:văng|ngã)|xô ngã|"
          r"lao (?:vào|trúng|thẳng vào|xuống|lên)|rơi xuống (?:vực|sông|kênh|mương|ruộng|hố|hồ|suối)|lăn xuống|"
          r"(?:sụp|sụt|lọt) (?:hố|ổ gà)|(?:sụt|sụp) xuống hố|vùi lấp|chôn vùi|nuốt chửng|trượt ngã|té ngã|lật|lật ngửa|ngửa bụng|ngã xe|té xe|cuốn ngã|ngã (?:xuống|ra) đường|mất lái|mất phanh|ủi văng|"
          r"văng.{0,20}(?:đường|vỉa hè)|vò nát|bẹp dúm|phơi bụng|nghiêng đổ|"
          r"vướng.{0,40}dây.{0,30}(?:đường|xe)|cuốn trôi")
FIRE = r"bốc cháy|bốc lửa|cháy rụi|thiêu rụi|lửa bao trùm|cháy (?:xe|ô tô|ôtô)|xe.{0,45}cháy"
OUTCOME = r"tử vong|thiệt mạng|thương vong|bị thương|nguy kịch|chết|mắc kẹt|biến dạng|hư hỏng"
ROUNDUP = r"bản tin tngt|tin tức tai nạn|tai nạn giao thông\s+\d+|toàn cảnh.*\||xem nhanh.*\|"


def actual_text(text):
    # Remove only the hypothetical/avoided impact; preserve a real impact elsewhere.
    text = re.sub(r"không có (?:xe máy|ô tô|ôtô|phương tiện)[^,.;!?]{0,45}(?:vùi lấp|chôn vùi|rơi xuống hố)[^,.;!?]*", "", text)
    text = re.sub(r"suýt\s+(?:(?:bị|gặp|xảy ra|gây|dẫn đến)\s+)?(?:(?:xe|ô tô|ôtô|nước|lũ|tàu)[^.;!?]{0,40}?)?(?:ra\s+)?(?:va chạm|tông|đâm|lật|tai nạn|cuốn)[^.;!?]*", "", text)
    text = re.sub(r"(?:để|nhằm) (?:né|tránh).{0,20}(?:va chạm|tai nạn)", "", text)
    text = re.sub(r"(?:né|tránh) (?:va chạm|tai nạn)(?: trong gang tấc)?", "", text)
    return re.sub(r"bê tông|lật đổ|lật tẩy|nhánh (?:đường )?đâm vào[^,.;]*", "", text)


def primary_report(headline, evidence):
    text = headline + ". " + evidence
    vehicle = has(ROAD_VEHICLE, text) or has(r"\bxe\b|cabin|tài xế", text)
    road = has(ROAD_CONTEXT, text)
    actual = actual_text(text)
    if road and has(r"(?:người|người đi xe máy|người đi đường).{0,45}(?:trượt ngã|té ngã)", actual) and not has(r"nguy cơ|có thể|nếu|phòng tránh", actual):
        return "reported_road_falls"
    if vehicle and has(IMPACT, actual):
        if not has(r"có thể|tiềm ẩn|nguy cơ|nếu|chỉ cần|giả định|phòng tránh", actual):
            return "actual_road_impact"
    if has(r"tai nạn giao thông|tngt|tai nạn trên.{0,30}(?:cao tốc|quốc lộ|tỉnh lộ)", actual):
        if has(OUTCOME, actual) and not has(r"nguy cơ|tiềm ẩn|giả định|phòng tránh|có thể", actual):
            return "reported_road_accident_with_outcome"
    if vehicle and has(FIRE, actual) and road:
        return "road_vehicle_fire"
    if vehicle and road and has(r"đứt dây chằng|hàng(?: hóa)? rơi", actual):
        return "cargo_spill_on_road"
    if vehicle and has(r"(?:cây|đá|vữa|mái tôn|xà gồ|vật nặng|biển quảng cáo)(?!\w).{0,65}(?:đổ|rơi|đè|trúng)", actual) and road:
        return "object_struck_road_vehicle"
    return None


def classify_accident(title: str | None, description: str | None = None,
                      content: str | None = None) -> Decision:
    """Recall-oriented road incident filter; excludes follow-up-only articles."""
    headline = normalize(title)
    lead = description_lead(description)
    text = headline + " " + lead
    def result(label, reason, evidence=None):
        return Decision(label, reason, evidence or headline)
    if not headline:
        return result("uncertain", "missing_title")
    roundup = has(ROUNDUP, headline)
    body_opening = normalize(content)[:2200]
    # A bulletin's discrete news item is primary reporting, unlike an old crash
    # cited as background in a policy or advice article.
    if re.search(r"^(?:bản tin|chuyển động|xem nhanh|toàn cảnh)", body_opening):
        bulletin_text = BeautifulSoup(html.unescape(content or ""), "html.parser").get_text("\n", strip=True)[:5000]
        for raw_sentence in re.split(r"\n|[.!?](?:\s|$)", bulletin_text):
            sentence = normalize(raw_sentence)
            if (has(ROAD_VEHICLE, sentence) and has(OUTCOME, sentence)
                    and not has(r"khởi tố|truy tố|xét xử|thống kê|khuyến cáo|nguy cơ|trước đây|năm ngoái", sentence)
                    and primary_report("", sentence)):
                return result("accident", "specific_road_incident_in_bulletin", sentence)

    if has(r"nghi vấn.{0,35}(?:lao|tông|đâm).{0,30}(?:đối thủ|nhóm người)", headline):
        return result("uncertain", "possible_intentional_violence")
    if has(r"chống lệnh.{0,30}lao xe|nạn nhân bị thương.{0,65}đã tử vong", headline):
        return result("not_accident", "violence_or_medical_followup")
    if (has(r"siêu thị|cửa hàng", headline)
            and has(r"nổi giận|cố ý|dùng chính chiếc xe", body_opening)
            and has(r"phá cửa|phá hoại tài sản", body_opening)):
        return result("not_accident", "intentional_property_damage")
    if (has(r"hàng rơi|đứt dây chằng", headline)
            and has(r"không xảy ra tai nạn", body_opening)):
        return result("not_accident", "cargo_spill_without_accident")

    # Investigation announcements may still be the first factual crash report.
    # Procedural/prosecution updates keep their exclusions below.
    investigation_title = bool(re.search(
        r"^(?:[^:]{1,40}:\s*)?điều tra\b", headline))
    detailed_crash_report = (
        investigation_title and has(r"tai nạn|va chạm", headline)
        and has(r"khoảng|vào hồi|lúc", body_opening)
        and has(ROAD_VEHICLE, body_opening) and has(IMPACT, actual_text(body_opening))
        and has(OUTCOME, body_opening)
        and not has(r"khởi tố|truy tố|xét xử|phục hồi điều tra", body_opening[:400]))
    fresh_search_report = (
        has(r"truy tìm", headline) and has(r"vừa xảy ra", body_opening[:400])
        and has(OUTCOME, body_opening)
        and primary_report("", body_opening) is not None
        and not has(r"khởi tố|truy tố|xét xử", body_opening[:400]))
    incident_first_search_report = (
        has(r"truy tìm", headline)
        and re.search(r"^(?:[^:]{1,40}:\s*)?(?:" + ROAD_VEHICLE + r")\b", headline)
        and primary_report(headline, lead) is not None
        and not has(r"khởi tố|truy tố|xét xử|tài xế khai|lời khai|xử phạt|bị phạt", headline))
    current_scene_report = (
        has(r"(?:tối|sáng|trưa|chiều|ngày) \d{1,2}[/.-]\d{1,2}", body_opening[:400])
        and has(r"khám nghiệm|hiện trường", body_opening[:400])
        and has(r"khoảng|lúc", body_opening)
        and primary_report("", body_opening) is not None)

    # A past accident in the body does not change the main topic of the article.
    legal = (r"khởi tố|truy tố|xét xử|tuyên án|án treo|tạm giữ|tạm giam|lãnh.{0,30}tù|"
             r"giữ nguyên hình phạt|truy tìm|truy vết|tìm nhân chứng|tìm thấy tài xế|"
             r"đã xác định danh tính|xác định danh tính|danh tính.{0,25}(?:nạn nhân|người tử vong)|"
             r"thăm hỏi|thăm, động viên|hỗ trợ.{0,25}(?:triệu|gia đình)|"
             r"phục hồi điều tra|công an làm việc|bị phạt và bồi thường|trách nhiệm pháp lý|"
             r"vấn đề pháp lý|tài xế khai gì|tài xế khai dùng|tài xế.{0,35}dương tính|"
             r"trích xuất dữ liệu|còn hạn đăng kiểm|rà soát|siết an toàn|đánh giá toàn diện")
    legal += r"|xử phạt|bị phạt|bắt.{0,15}nghi phạm|xác minh dấu hiệu gây rối|dương tính với ma túy|tìm thấy thi thể|tìm kiếm tài xế|mở rộng phạm vi tìm kiếm|vận chuyển thi thể|thêm.{0,20}(?:hành khách|nạn nhân) tử vong"
    if not roundup and (has(legal, headline) or re.search(r"^(?:[^:]{1,40}:\s*)?(?:điều tra|xử lý|cứu hộ)\b", headline)) and not (detailed_crash_report or fresh_search_report or incident_first_search_report):
        if investigation_title and not body_opening and has(ROAD_VEHICLE, text) and has(IMPACT, text) and has(OUTCOME, text):
            return result("uncertain", "investigation_title_needs_full_body")
        return result("not_accident", "followup_excluded")
    if not roundup and has(r"khởi tố|truy tố|tạm giữ|tạm giam|tuyên án", lead[:180]):
        return result("not_accident", "followup_excluded")
    if has(r"nỗi đau|ngã rẽ cuộc đời|dự định dang dở|ước mơ dang dở|dang dở ước mơ|giấc mơ dang dở|nương nhờ|tìm lại bước đi|sức khỏe.{0,35}nạn nhân|bị liệt.{0,30}vụ lật|thân nhân|tiếng khóc|định mệnh.{0,20}gia đình|xót xa.{0,15}chú rể", headline) and not current_scene_report:
        return result("not_accident", "human_interest_followup")
    if has(r"đau thương.{0,20}gia đình|tiếng khóc|tang lễ", lead) and not has(r"tông|đâm|va chạm|cán|lật|lao vào", headline):
        return result("uncertain", "bereavement_or_incident_report")
    if has(r"cứu sống|cứu chữa|phẫu thuật|bệnh viện|mổ cấp cứu|ưu tiên mổ", headline) and not has(r"tại chỗ|hiện trường|cắt cabin", headline):
        return result("not_accident", "medical_followup")
    if has(r"bịa đặt|tin giả|sai sự thật|không xảy ra|dựng hiện trường giả", text):
        return result("not_accident", "unverified_or_fake_incident")
    if has(r"tai nạn cũ như tin mới|đăng lại vụ tai nạn|xới.*tai nạn cũ", text):
        return result("not_accident", "recycled_incident_warning")
    if has(r"đập vỡ kính|hất nước|dùng gậy|dùng dao|bóp mũi|đánh người|đánh hai vợ chồng|cướp giật|giết người", headline):
        return result("not_accident", "violence_not_traffic_accident")
    if has(r"xe chiến đấu|xe tăng|chiến trường|tấn công.{0,25}(?:tên lửa|quân sự)", text):
        return result("not_accident", "outside_road_scope")
    if has(r"máy bay|trực thăng", headline):
        for sentence in re.split(r"[.!?](?:\s|$)", body_opening)[:6]:
            if (has(r"xe tải|xe đầu kéo|ô tô|ôtô|xe máy", sentence)
                    and has(r"cao tốc|quốc lộ|đường bộ", sentence)
                    and has(r"máy bay|chuyến bay|phi cơ|trực thăng", sentence)
                    and has(r"va trúng|va chạm|đâm|rơi trúng", sentence)
                    and not has(r"suýt|trước đây|năm ngoái|nguy cơ|có thể", sentence)):
                return result("accident", "aircraft_struck_public_road_vehicle", sentence)
    if has(r"máy bay|trực thăng|tiêm kích|hàng không", headline) and has(r"rơi|đâm|va chạm|lật|tai nạn|thiệt mạng", text):
        return result("not_accident", "outside_road_scope")
    road_vehicle = has(ROAD_VEHICLE, text)
    # A vessel hitting a shared bridge can directly injure road users. Inspect
    # the opening account before rejecting a watercraft-only headline.
    if has(r"sà lan|tàu|thuyền", headline):
        for sentence in re.split(r"[.!?](?:\s|$)", body_opening)[:6]:
            if (has(r"xe máy|ô tô|ôtô|xe tải|người đi bộ", sentence)
                    and has(r"trên cầu|đường bộ|mặt đường", sentence)
                    and has(r"bị đổ|bị lật|rơi xuống|va chạm|tông|đâm|đè", sentence)
                    and has(OUTCOME, sentence)
                    and not has(r"trước đây|năm ngoái|nguy cơ|có thể", sentence)):
                return result("accident", "water_incident_struck_road_users", sentence)
    if not roundup and has(r"sà lan|tàu thủy|tàu thuỷ|tàu cá|đường thủy|đường thuỷ", text) and not has(r"xe máy|xe tải|xe buýt|xe khách|xe đầu kéo|ô tô|ôtô|mô tô|taxi", text):
        return result("not_accident", "outside_road_scope")
    if has(r"tàu|thuyền|sà lan|ca nô|cano|xuồng|đường sắt|đường thủy|đường thuỷ", headline) and not road_vehicle and not (roundup and has(r"tai nạn giao thông|tngt", lead)):
        if has(r"đâm|tông|lật|chìm|trật bánh|va chạm|tai nạn|thiệt mạng", text):
            return result("not_accident", "outside_road_scope")
    if has(r"tai nạn lao động|tai nạn điện|điện giật|pháo nổ|nhảy cầu|leo núi|xích đu|ngạt khí", text):
        return result("not_accident", "nontraffic_event")
    if has(r"xe lu|xe nâng|xe cuốc|xe múc|máy xúc", headline) and has(r"công trường|thi công|công nhân|nhà máy", text) and not has(r"xe máy|xe đạp|ô tô|ôtô|người đi đường", headline):
        return result("not_accident", "worksite_excluded")
    if has(r"cháy.{0,35}(?:gara|xưởng|nhà máy|bãi (?:giữ|đậu|đỗ)|cửa hàng xe)|(?:gara|xưởng|nhà máy|bãi giữ).{0,35}cháy", headline):
        return result("not_accident", "nontraffic_fire")

    if not roundup and not detailed_crash_report and (has(r"thống kê|kéo giảm|giảm.{0,30}(?:tiêu chí|tai nạn)|(?:tai nạn|tngt).{0,25}giảm|liên tục xảy ra tai nạn|ngày.{0,20}nghỉ tết|trong.{0,20}ngày nghỉ|toàn quốc xảy ra|nửa đầu năm|kiểm soát tngt", headline)
                        or re.search(r"\d+\s+vụ tai nạn|\d+ người tử vong do tai nạn giao thông ngày", headline)):
        return result("not_accident", "aggregate_statistics")
    if has(r"diễn tập|giả định|thử nghiệm|thử va chạm|thử nghiệm chống chấn thương", text):
        return result("not_accident", "simulation_or_safety_test")
    if has(r"giải mã nút|biểu tượng xe|sắp có xe|concept|thiết kế dạng|mẫu xe.{0,25}công nghệ|ra mắt|doanh số|phân khúc|trình làng|an toàn như ô tô|triệu hồi|thiết kế cửa|hợp tác chiến lược", text):
        if not (has(r"bị lật|lật \d+ vòng|tông|đâm vào|va chạm.{0,25}(?:tử vong|bị thương)", headline) and has(ROAD_CONTEXT, headline)):
            return result("not_accident", "vehicle_product_or_technology")
    if has(r"hiểm họa|hiểm hoạ|hiến kế|nguy cơ|phòng tránh|kinh nghiệm|tài xế cần tránh|an toàn cho trẻ|quyền ưu tiên|đúng luật|có mặc nhiên|liệu có an toàn|mức phạt|sẽ được hỗ trợ|điểm đen|tai nạn rình rập|cảnh báo nguy hiểm", headline) or re.search(r"có được|có nên|có quyền|được lấn|được vượt|được (?:đè|cắt) vạch|phải làm gì|phạt (?:đến|tới)|có bị phạt|phân biệt|thế nào\?", headline):
        return result("not_accident", "advice_or_hypothetical")
    if has(r"sau (?:vụ|sự cố).*?(?:dự kiến|xây|sửa)|dự kiến.*sau sự cố", headline):
        return result("not_accident", "followup_excluded")
    if (has(r"suýt|né tai nạn|né tránh trong gang tấc", text)
            and not has(IMPACT, actual_text(text))
            and not primary_report("", body_opening)):
        return result("not_accident", "near_miss")

    if not roundup and has(r"yêu cầu|đề nghị|khuyến cáo|tuyên truyền|thủ tướng|chuẩn hóa|chuẩn hoá|chuyển đổi|hợp tác|khắc phục hậu quả|vi phạm nồng độ cồn|lời khai|chiếm dụng|quy chuẩn|trạm sạc|đoạt áo|thắng kịch tính|giải xe đạp|xử lý.{0,20}(?:loạt|vi phạm|xe tự chế)|bỏ quên.{0,30}nhiều tháng|(?:quốc lộ|nền đường|hạ tầng).{0,25}(?:hư hỏng|xói lở)", headline):
        return result("not_accident", "non_event_main_topic")

    reason = primary_report(headline, lead)
    if reason:
        return result("accident", reason, text)
    old = _classify_v3(title, description)
    if old.label == "accident":
        return old
    # Do not let historical examples in an infrastructure/policy article become events.
    topical = r"khởi công|thông xe|dự án|thi công|đầu tư|quy định|tập huấn|tuyên truyền|hạ tầng|đề xuất|bảo hiểm|giải phóng mặt bằng|học bổng|lì xì|chính sách|khuyến cáo|thông tư|xây cầu|sửa chữa|biển báo|vạch khoảng cách|đường chính"
    if has(topical, headline) and not roundup:
        return result("not_accident", "non_event_main_topic")
    body = normalize(content)[:1800]
    body_reason = "actual_incident_in_opening_body"
    if not body:
        soup = BeautifulSoup(html.unescape(description or ""), "html.parser")
        for tag in soup(["script", "style", "ul", "ol", "aside", "nav"]):
            tag.decompose()
        paragraph = soup.find("p")
        body = normalize(str(paragraph if paragraph is not None else soup))[:1000]
        body = ". ".join(re.split(r"[.!?](?:\s|$)", body)[:2])
        body_reason = "actual_incident_in_rss_description"
    # Full RSS lead can contain related text; body is used only for a road-focused title.
    roundup_body_allowed = not roundup or has(r"tai nạn|tngt|lật|ngửa bụng|va chạm|tông|đâm", headline)
    if body and roundup_body_allowed and (road_vehicle or has(r"tai nạn|tngt|gặp nạn|ngã tư|giao lộ|hố tử thần|sụt lún|sạt lở", headline)):
        first_sentences = ". ".join(re.split(r"[.!?](?:\s|$)", body)[:8])
        if not has(r"trước đây|năm ngoái|giả định|nguy cơ|có thể", first_sentences):
            for sentence in re.split(r"[.!?](?:\s|$)", first_sentences):
                if not has(ROAD_VEHICLE + r"|tài xế|phương tiện|cabin|chiếc xe|xe này", sentence):
                    continue
                reason = primary_report(headline, sentence)
                if reason:
                    return result("accident", body_reason, sentence)
    if has(r"tai nạn|tngt|gặp nạn", headline) and not has(r"giao thông|cao tốc|quốc lộ|tỉnh lộ", text) and not road_vehicle:
        return result("uncertain", "road_context_missing")
    return old
