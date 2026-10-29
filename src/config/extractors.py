import os
from dataclasses import dataclass, field

import polars as pl

from .main import DATA_GOLD_DIR
from .filters import FILTER_SOURCES

EXTRACT_SOURCES = FILTER_SOURCES
EXTRACT_OUTPUT_DIR = os.path.join(DATA_GOLD_DIR, "accidents")
EXTRACT_VERSION = "rules-v2"
# Text vocabulary includes historical names. No administrative remapping is inferred.
PROVINCE_ALIASES = {
    "Hà Nội": ("Hà Nội",), "Hải Phòng": ("Hải Phòng",),
    "TP Hồ Chí Minh": ("TP HCM", "TP.HCM", "TP Hồ Chí Minh", "Hồ Chí Minh"),
    "Lâm Đồng": ("Lâm Đồng",), "Gia Lai": ("Gia Lai",),
    "Đồng Nai": ("Đồng Nai",), "Đà Nẵng": ("Đà Nẵng",),
    "Cà Mau": ("Cà Mau",), "Quảng Ngãi": ("Quảng Ngãi",),
}
PROVINCE_NAMES = (
    "An Giang", "Bà Rịa - Vũng Tàu", "Bắc Giang", "Bắc Kạn", "Bạc Liêu",
    "Bắc Ninh", "Bến Tre", "Bình Định", "Bình Dương", "Bình Phước", "Bình Thuận",
    "Cao Bằng", "Cần Thơ", "Đắk Lắk", "Đắk Nông", "Điện Biên", "Đồng Tháp",
    "Hà Giang", "Hà Nam", "Hà Tĩnh", "Hải Dương", "Hậu Giang", "Hòa Bình",
    "Hưng Yên", "Khánh Hòa", "Kiên Giang", "Kon Tum", "Lai Châu", "Lạng Sơn",
    "Lào Cai", "Long An", "Nam Định", "Nghệ An", "Ninh Bình", "Ninh Thuận",
    "Phú Thọ", "Phú Yên", "Quảng Bình", "Quảng Nam", "Quảng Ninh", "Quảng Trị",
    "Sóc Trăng", "Sơn La", "Tây Ninh", "Thái Bình", "Thái Nguyên", "Thanh Hóa",
    "Thừa Thiên Huế", "Huế", "Tiền Giang", "Trà Vinh", "Tuyên Quang",
    "Vĩnh Long", "Vĩnh Phúc", "Yên Bái",
)
PROVINCE_ALIASES.update({name: (name,) for name in PROVINCE_NAMES})
PROVINCE_ALIASES["TP Hồ Chí Minh"] += ("TP. HCM", "TPHCM", "TP. Hồ Chí Minh", "Sài Gòn")
PROVINCE_ALIASES["Đắk Lắk"] += ("Đăk Lăk", "Đắk Lăk")
PROVINCE_ALIASES["Hòa Bình"] += ("Hoà Bình",)
PROVINCE_ALIASES["Thanh Hóa"] += ("Thanh Hoá",)
PROVINCE_ALIASES["Khánh Hòa"] += ("Khánh Hoà",)
VEHICLE_PATTERNS = {
    "xe máy điện": r"xe máy điện", "xe máy": r"xe máy|mô tô|môtô|xe gắn máy",
    "xe đạp điện": r"xe đạp điện", "xe đạp": r"xe đạp",
    "xe đầu kéo": r"(?:xe )?đầu kéo", "xe container": r"(?:xe )?container",
    "xe ben": r"(?:xe|ô tô|ôtô) ben", "xe tải": r"(?:xe|ô tô|ôtô) tải",
    "xe buýt": r"xe buýt", "xe khách": r"xe khách", "taxi": r"taxi",
    "ô tô": r"ô tô|ôtô", "tàu hỏa": r"tàu hỏa|tàu hoả|tàu lửa",
    "xe cứu thương": r"(?:xe|ô tô|ôtô) cứu thương", "xe bồn": r"(?:xe|ô tô|ôtô) bồn",
    "xe ba gác": r"xe ba gác|xe ba bánh", "xe công trình": r"xe múc|xe xúc|xe lu|xe cẩu",
}
VEHICLE_SPECIFIC_PATTERN = r"\s+(?:tải|ben|khách|buýt|bồn|đầu kéo|container|cứu thương)\b"
INCIDENT_PATTERNS = {
    "tong_duoi": r"tông đuôi|đâm (?:vào )?đuôi",
    "va_cham": r"va chạm|tông|đâm (?:vào|trúng|nhau)|đấu đầu",
    "can_nguoi": r"cán (?:tử vong|chết|người|qua)|bị xe[^,.!?;]{0,35}cán",
    "lat_xe": r"lật (?:xe|ngửa)|xe[^,.!?;]{0,25}lật|lật nghiêng",
    "mat_lai": r"mất lái", "chay_xe": r"(?:xe[^,.!?;]{0,25})?(?:bốc cháy|cháy rụi)",
    "dam_vat_can": r"(?:đâm|tông|lao) (?:vào|trúng) (?:tường|cột|dải phân cách|lan can|gốc cây)",
    "tu_nga": r"tự ngã|ngã xe", "roi_xuong": r"(?:xe[^,.!?;]{0,25})?(?:lao|rơi) xuống (?:vực|sông|kênh|mương)",
}
NUMBER_WORDS = {"không": 0, "một": 1, "hai": 2, "ba": 3, "bốn": 4,
                "tư": 4, "năm": 5, "sáu": 6, "bảy": 7, "tám": 8, "chín": 9, "mười": 10}
NUMBER_TOKEN = r"không|một|mốt|hai|ba|bốn|tư|năm|lăm|sáu|bảy|tám|chín|mười|mươi|trăm|linh|lẻ"
NUMBER_PATTERN = rf"\d+(?:[.,]\d+)*|(?:{NUMBER_TOKEN})(?:\s+(?:{NUMBER_TOKEN}))*"
NUMBER_WORDS.update({"mốt": 1, "lăm": 5})
CASUALTY_PATTERNS = {"fatalities": r"tử vong|thiệt mạng|chết|tử nạn", "injuries": r"(?:bị )?thương(?!\s+vong)(?: tích)?|chấn thương"}
SINGULAR_SUBJECT = r"(?:nam thanh niên|người phụ nữ|người đàn ông|tài xế|lái xe|phụ xe|học viên|thầy dạy lái)"
CASUALTY_UNIT = rf"người|em|nạn nhân|học sinh|công nhân|hành khách|{SINGULAR_SUBJECT}"
APPROXIMATE_PATTERN = r"(?:hơn|ít nhất|khoảng|gần|trên|dưới|tới|đến|chừng|[-–]|\d\s+đến)\s*$"
NON_SCENE_PATTERN = r"(?:quê(?: quán)?|trú|sinh sống|cư trú|bệnh viện|cấp cứu|điều trị|đưa về|đưa đến)[^,;.!?]*$"
LOCATION_CONTEXT_PATTERN = r"(?:ở|tại|tỉnh|thành phố|tp\.?|địa bàn)\s*$"
ROAD_PREFIX_PATTERN = r"(?:cao tốc|quốc lộ|đường|đại lộ)\s*$"
ADMIN_PREFIXES = {"district": r"quận|huyện|thị xã", "ward": r"phường|xã|thị trấn"}
ADMIN_NAME_PATTERN = r"[^\W\d_]+(?:\s+[^\W\d_]+){0,7}|\d+"
ROAD_PATTERN = r"(?:cao tốc|quốc lộ|đường|đại lộ)\s+[^,;.!?()]+"
NEGATION_PATTERN = r"không|chưa|suýt|giả định|nếu|có thể|nguy cơ"
FACT_NEGATION_PATTERN = r"\b(?:không|chưa|suýt|có thể|nguy cơ)(?:\s+\w+){0,3}\s*$"
HYPOTHETICAL_PATTERN = r"\b(?:nếu|giả sử|giả định)\b"
UPDATE_PATTERN = r"\b(?:thêm|sau đó|sau đấy|sau cấp cứu|không qua khỏi|nâng (?:tổng )?số|tăng lên)\b"
MULTI_EVENT_PATTERN = r"\b(?:hai vụ|2 vụ|nhiều vụ|vụ thứ|vụ khác)\b"
SCENE_PATTERN = r"\b(?:va chạm|xảy ra|tai nạn|hiện trường|cú tông)\b"
SUBJECT_ALIASES = {"lái xe": "tài xế"}
DISJOINT_GROUP_PATTERN = r"người khác|còn lại|cả\s+\d+|tại hiện trường.*tại bệnh viện"
VICTIM_AGE_PATTERN = r"(?:từ\s+)?\d+(?:\s*[-–]\s*\d+)?\s+tuổi\s+"
NEAR_MISS_PATTERN = r"\bsuýt\s+(?:(?:gây|bị)\s+)?(?:va chạm|tông|đâm|cán|lật)\b"
DISJOINT_ROLE_PAIRS = (frozenset(("tài xế", "phụ xe")), frozenset(("học viên", "thầy dạy lái")))


@dataclass
class CasualtyMention:
    count: int
    evidence: str
    start: int
    end: int
    subject: str = ""
    total: bool = False
    incremental: bool = False
EXTRACT_SCHEMA = {
    "province": pl.String, "district": pl.String, "ward": pl.String,
    "vehicles": pl.List(pl.String), "fatalities": pl.Int64, "injuries": pl.Int64,
    "incident_types": pl.List(pl.String), "evidence_json": pl.String,
    "review_reasons": pl.List(pl.String), "extraction_version": pl.String,
}


@dataclass
class AccidentExtraction:
    province: str | None = None
    district: str | None = None
    ward: str | None = None
    vehicles: list[str] = field(default_factory=list)
    fatalities: int | None = None
    injuries: int | None = None
    incident_types: list[str] = field(default_factory=list)
    evidence: dict[str, list[str]] = field(default_factory=dict)
    review_reasons: list[str] = field(default_factory=list)
    extraction_version: str = EXTRACT_VERSION
