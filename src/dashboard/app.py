"""Run: python -m streamlit run src/dashboard/app.py"""
import streamlit as st

st.set_page_config(page_title="Theo dõi tai nạn giao thông", page_icon="🚦", layout="wide")
st.markdown("""<style>
.stApp {background:#f6f8fc;color:#14263d}
[data-testid="stSidebar"] {background:#eaf0f8}
[data-testid="stMetric"] {background:white;border:1px solid #e0e6f0;border-radius:14px;padding:18px}
[data-testid="stMetricLabel"] {color:#53677f}
h1,h2,h3 {letter-spacing:-.035em}
.eyebrow {color:#167c80;font-weight:700;letter-spacing:.18em;font-size:12px}
.intro {color:#60718a;font-size:16px;margin-bottom:24px}
</style>""", unsafe_allow_html=True)

LABELS = {"accident": "Tai nạn", "uncertain": "Cần xem xét", "not_accident": "Không phải tai nạn"}
REASONS = {
    "road_context_missing": "Chưa rõ phương tiện có tham gia giao thông đường bộ",
    "outside_road_scope": "Ngoài phạm vi đường bộ",
    "worksite_excluded": "Tai nạn thi công, ngoài giao thông đường bộ",
    "followup_excluded": "Bài chỉ cập nhật xử lý sau vụ việc, không thuộc phạm vi",
    "road_vehicle_fire": "Cháy phương tiện trên đường",
    "object_struck_road_vehicle": "Vật rơi đè phương tiện trên đường",
    "province_missing": "Thiếu tỉnh/thành", "missing_province": "Thiếu tỉnh/thành",
    "missing_incident_details": "Chưa nhận diện được diễn biến tai nạn",
    "ambiguous_province": "Có nhiều địa danh, chưa xác định hiện trường",
    "published_at_missing": "Thiếu ngày đăng", "missing_district": "Thiếu quận/huyện",
    "water_transport_scope": "Sự cố đường thủy cần xác nhận phạm vi",
    "vehicle_fire_scope": "Cháy phương tiện, chưa rõ có va chạm",
    "falling_object_vehicle_scope": "Vật rơi đè xe, chưa rõ trạng thái lưu thông",
    "insufficient_event_evidence": "Chưa đủ bằng chứng về vụ tai nạn",
    "ambiguous_or_insufficient_match": "Chưa chắc bài thuộc sự kiện nào",
}


def reason_text(value):
    text = str(value)
    for code, label in REASONS.items():
        text = text.replace(code, label)
    return text


def table(frame, columns=None, key=None):
    if frame.empty:
        st.info("Chưa có bản ghi phù hợp.")
        return
    if columns:
        frame = frame[[column for column in columns if column in frame]]
    frame = frame.copy()
    for column in ("reasons", "filter_reason"):
        if column in frame:
            frame[column] = frame[column].map(reason_text)
    if "accident_label" in frame:
        frame["accident_label"] = frame["accident_label"].map(LABELS)
    st.dataframe(frame, hide_index=True, width="stretch", key=key,
                 column_config={"url": st.column_config.LinkColumn("Mở bài báo"),
                                "link": st.column_config.LinkColumn("Mở bài báo"),
                                "title": "Tiêu đề", "source": "Nguồn", "pub_date": "Ngày đăng",
                                "accident_label": "Kết quả lọc", "filter_reason": "Lý do",
                                "reasons": "Lý do cần xem xét", "province": "Tỉnh/thành",
                                "district": "Quận/huyện", "article_count": "Số bài",
                                "event_id": "Mã vụ", "ward": "Xã/phường", "location_full": "Địa điểm",
                                "vehicles_involved": "Phương tiện liên quan",
                                "first_published_at": "Ghi nhận đầu tiên trên báo",
                                "last_published_at": "Bài cập nhật gần nhất",
                                "published_at": "Ngày đăng", "fatalities": "Tử vong trong bản tin",
                                "injuries": "Bị thương trong bản tin",
                                "total_fatalities": "Tử vong", "total_injuries": "Bị thương",
                                "is_duplicate": "Bài trùng", "duplicate_of_article_key": "Bản gốc",
                                "duplicate_similarity": st.column_config.NumberColumn(
                                    "Độ tương đồng", format="%.3f")})


def main():
    from dashboard.accidents import render
    render(table)


if __name__ == '__main__':
    main()
