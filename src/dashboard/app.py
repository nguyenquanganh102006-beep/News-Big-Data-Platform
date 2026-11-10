"""Run: python -m streamlit run src/dashboard/app.py"""
import pandas as pd
import streamlit as st

from config import DATA_DIR
from dashboard.data import discover_datasets, discover_databases, load_articles, read_database, filter_articles
from dashboard.statistics import article_periods, source_statistics, local_times, event_periods

st.set_page_config(page_title="News Observatory · Tai nạn giao thông", page_icon="📰", layout="wide")
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
                                "total_fatalities": "Tử vong", "total_injuries": "Bị thương",
                                "is_duplicate": "Bài trùng", "duplicate_of_article_key": "Bản gốc",
                                "duplicate_similarity": st.column_config.NumberColumn(
                                    "Độ tương đồng", format="%.3f")})


def main():
    datasets = discover_datasets(DATA_DIR)
    with st.sidebar:
        st.markdown("### 📰 News Observatory")
        st.caption("Nền tảng dữ liệu tai nạn giao thông")
        names = list(datasets)
        selected = names[0]
        st.caption("Một bộ dữ liệu hiện hành · toàn bộ lịch sử")
        root = datasets[selected]
        if st.button("Làm mới dữ liệu", width="stretch"):
            try:
                from dashboard.publish import publish
                with st.spinner("Cập nhật toàn bộ lịch sử…"):
                    publish(DATA_DIR)
                st.rerun()
            except Exception as error:
                st.error(f"Chưa cập nhật được; giữ bản hiện hành: {error}")
        st.caption("Không tự crawl. Làm mới để tổng hợp lịch sử mới nhất, không sửa dữ liệu gốc.")
    articles, errors = load_articles(root)
    for error in errors:
        st.warning(f"Không đọc được dữ liệu bài báo: {error}")
    with st.sidebar:
        sources = st.multiselect("Nguồn báo", sorted(articles["source"].dropna().unique()) if not articles.empty else [])
        labels = st.multiselect("Kết quả lọc", list(LABELS), format_func=LABELS.get)
        show_duplicates = st.checkbox("Bao gồm bài trùng trong tra cứu", value=False)
        query = st.text_input("Tìm tiêu đề hoặc mô tả", placeholder="Ví dụ: Lâm Đồng, xe máy…")
        use_dates = st.checkbox("Lọc ngày đăng bài")
        dates = None
        if use_dates and not articles.empty and "pub_date" in articles:
            times = pd.to_datetime(articles["pub_date"], errors="coerce", utc=True).dropna()
            if not times.empty:
                local = times.dt.tz_convert("Asia/Ho_Chi_Minh").dt.date
                dates = st.date_input("Khoảng ngày (giờ Việt Nam)", value=(local.min(), local.max()))
        st.divider()
        st.caption("Mặc định hiển thị bài gốc trên toàn bộ ngày. Bật lọc ngày chỉ khi cần thu hẹp.")

    duplicate_count = (int(articles["is_duplicate"].fillna(False).astype(bool).sum())
                       if not articles.empty and "is_duplicate" in articles else 0)
    if not show_duplicates and duplicate_count:
        articles = articles[~articles["is_duplicate"].fillna(False).astype(bool)].copy()

    st.markdown('<div class="eyebrow">NEWS INTELLIGENCE / VIETNAM</div>', unsafe_allow_html=True)
    st.title("Theo dõi tin tức. Hiểu từng sự kiện.")
    st.markdown('<div class="intro">Từ bài báo đến sự kiện tai nạn — theo dõi kết quả xử lý và những thông tin cần kiểm tra.</div>', unsafe_allow_html=True)
    if (root / "articles.parquet").exists():
        st.caption("Danh sách và kho sự kiện bao gồm cả 7 nguồn RSS; số vụ là kết quả ghép bài đã qua trích xuất.")
    if duplicate_count:
        st.caption(f"Đã đánh dấu {duplicate_count:,} bài trùng theo nội dung; chúng được ẩn khỏi thống kê và tra cứu mặc định. Bật tùy chọn bên trái để xem và kiểm tra bản gốc.")
    filtered = filter_articles(articles, sources, labels, query, dates)
    # Headline metrics cover every publication date. Source, label, and text
    # filters still apply; the optional date range only affects detailed views.
    metric_articles = filter_articles(articles, sources, labels, query)

    def show_article_metrics(heading, frame):
        st.subheader(heading)
        counts = frame["accident_label"].value_counts() if "accident_label" in frame else pd.Series(dtype=int)
        cols = st.columns(4)
        values = [len(frame), int(counts.get("accident", 0)), int(counts.get("uncertain", 0)),
                  frame["source"].nunique() if "source" in frame else 0]
        for col, label, value in zip(cols, ["Bài báo", "Bài tai nạn", "Bài cần xem xét", "Nguồn báo"], values):
            col.metric(label, f"{value:,}")

    show_article_metrics("Toàn bộ thời gian", metric_articles)
    today_date = pd.Timestamp.now(tz="Asia/Ho_Chi_Minh").date()
    article_dates = local_times(metric_articles).dt.date
    today_articles = metric_articles.loc[article_dates.eq(today_date)]
    show_article_metrics(f"Hôm nay · {today_date:%d/%m/%Y}", today_articles)
    st.caption("Các chỉ số đếm bài báo, không phải số vụ tai nạn. Hai hàng áp dụng bộ lọc nguồn, kết quả và từ khóa; hàng tổng hợp luôn tính trên mọi ngày, hàng hôm nay theo giờ Việt Nam.")
    overview, stats_tab, news, events_tab, reviews_tab = st.tabs(["Tổng quan", "Thống kê thời gian", "Bài báo", "Sự kiện", "Chờ review"])

    with stats_tab:
        st.subheader("Nhịp tin tức theo thời gian")
        st.caption("Áp dụng bộ lọc bài báo ở thanh bên. Ngày/giờ tính theo Việt Nam và thời gian đăng bài.")
        period = st.selectbox("Gộp thời gian", ["Ngày", "Tuần", "Tháng"])
        frequency = {"Ngày": "D", "Tuần": "W-MON", "Tháng": "MS"}[period]
        summary = article_periods(filtered, frequency, dates)
        if summary.empty:
            st.info("Không có bài với ngày đăng hợp lệ trong lựa chọn hiện tại.")
        else:
            a, b, c = st.columns(3)
            valid_days = local_times(filtered).dropna().dt.date.nunique()
            a.metric("Ngày có bài đăng", valid_days)
            daily_summary = article_periods(filtered, "D", dates)
            b.metric("Trung bình bài / ngày trong khoảng", f"{daily_summary['Tổng bài'].mean():.1f}")
            total = int(summary["Tổng bài"].sum())
            c.metric("Tỷ lệ bài tai nạn", f"{100*summary['Tai nạn'].sum()/total:.1f}%" if total else "—")
            st.line_chart(summary[["Tổng bài", "Tai nạn", "Cần xem xét"]], color=["#7a91b0", "#168b88", "#efb44c"])
            st.caption("Ngày trống giữa hai ngày có bài được hiển thị 0; đây là 0 bài trong snapshot, không phải xác nhận ngoài thực tế không có tai nạn. Tuần bắt đầu thứ Hai.")
            with st.expander("Tỷ lệ bài tai nạn theo kỳ", expanded=False):
                st.line_chart(summary[["Tỷ lệ tai nạn (%)"]], color="#168b88")
            st.dataframe(summary.reset_index(), hide_index=True, width="stretch")
            st.download_button("Tải thống kê thời gian CSV", summary.to_csv().encode("utf-8-sig"), "news_time_statistics.csv", "text/csv")
        st.subheader("So sánh các nguồn báo")
        by_source = source_statistics(filtered)
        if not by_source.empty:
            st.dataframe(by_source.reset_index(), hide_index=True, width="stretch")
            dated = filtered.copy()
            dated["Ngày"] = local_times(dated).dt.tz_localize(None).dt.normalize()
            dated = dated.dropna(subset=["Ngày"])
            if not dated.empty:
                st.subheader("Lượng bài từng nguồn theo ngày")
                source_daily = pd.crosstab(dated["Ngày"], dated["source"])
                source_daily = source_daily.reindex(daily_summary.index, fill_value=0)
                st.area_chart(source_daily)
        left, right = st.columns(2)
        times = local_times(filtered).dropna()
        with left:
            st.subheader("Giờ đăng bài")
            if not times.empty:
                hours = times.dt.hour.value_counts().reindex(range(24), fill_value=0).rename("Bài báo")
                hours.index.name = "Giờ Việt Nam"
                st.bar_chart(hours, color="#168b88")
        with right:
            st.subheader("Thứ trong tuần")
            if not times.empty:
                weekdays = times.dt.dayofweek.value_counts().reindex(range(7), fill_value=0)
                weekdays.index = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"]
                st.bar_chart(weekdays.rename("Bài báo"), color="#7a91b0", sort=False)
        invalid = int(local_times(filtered).isna().sum())
        if invalid:
            st.caption(f"{invalid} bài thiếu ngày hợp lệ không được đưa vào thống kê thời gian.")

    with overview:
        left, right = st.columns([1.3, 1])
        with left:
            st.subheader("Kết quả lọc theo nguồn")
            if not filtered.empty and "accident_label" in filtered:
                chart = pd.crosstab(filtered["source"], filtered["accident_label"]).rename(columns=LABELS)
                st.bar_chart(chart, color=["#168b88", "#a8bbd0", "#efb44c"][:len(chart.columns)])
            else:
                st.info("Chưa có dữ liệu lọc. Chạy bước 3 để tạo classified.parquet.")
        with right:
            st.subheader("Bài báo theo ngày đăng")
            if not filtered.empty and "pub_date" in filtered:
                times = pd.to_datetime(filtered["pub_date"], errors="coerce", utc=True).dt.tz_convert("Asia/Ho_Chi_Minh")
                daily = times.dt.date.value_counts().sort_index().rename("Bài báo")
                st.line_chart(daily, color="#168b88")
            else:
                st.info("Chưa có dữ liệu thời gian.")
        st.subheader("Bài tai nạn mới nhất")
        recent = filtered[filtered["accident_label"] == "accident"] if "accident_label" in filtered else filtered
        if "pub_date" in recent:
            recent = recent.sort_values("pub_date", ascending=False)
        table(recent.head(10), ["title", "source", "pub_date", "link", "filter_reason"], "recent")

    with news:
        st.subheader("Tra cứu bài báo")
        st.caption(f"{len(filtered):,} / {len(articles):,} bài · bộ lọc ở thanh bên áp dụng cho bài báo")
        article_columns = ["title", "source", "accident_label", "pub_date", "filter_reason", "link", "filter_version"]
        if show_duplicates:
            article_columns.extend(["is_duplicate", "duplicate_of_article_key", "duplicate_similarity"])
        table(filtered, article_columns, "articles")
        st.download_button("Tải danh sách CSV", filtered.to_csv(index=False).encode("utf-8-sig"),
                           file_name="news_articles.csv", mime="text/csv")
        if not filtered.empty:
            index = st.selectbox("Xem nội dung một bài", range(len(filtered)),
                                 format_func=lambda i: str(filtered.iloc[i].get("title", i)))
            row = filtered.iloc[index]
            st.write(str(row.get("title", "")))
            st.text(str(row.get("description", "Chưa có mô tả")))
            st.caption(f"{row.get('source', '')} · {row.get('filter_reason', '')}")

    databases = discover_databases(root)
    with st.sidebar:
        db_name = st.selectbox("Kho sự kiện", list(databases)) if databases else None
        st.caption("Bộ lọc bài báo không thay đổi số liệu kho sự kiện. Chọn kho riêng cho canonical hoặc streaming.")
    snapshot = None
    if db_name:
        try:
            snapshot = read_database(databases[db_name])
        except Exception as error:
            with events_tab:
                st.warning(f"Chưa đọc được kho sự kiện: {error}")
            with reviews_tab:
                st.warning("Kho chưa đọc được. Nếu consumer đang ghi, dừng writer rồi làm mới dashboard.")

    with events_tab:
        st.subheader("Sự kiện tai nạn")
        if snapshot is None:
            st.info("Chưa có kho sự kiện đọc được trong bộ dữ liệu này.")
        else:
            st.caption(f"{snapshot['kind']} · {db_name} · số liệu của toàn kho đang chọn")
            ev = snapshot["events"]
            a, b, c = st.columns(3)
            a.metric("Sự kiện", len(ev))
            b.metric("Bài đã gán sự kiện", len(snapshot["links"]))
            c.metric("Bài chờ matching review", len(snapshot["reviews"]))
            if ev.empty:
                st.info("Chưa có sự kiện được tạo. Bài tai nạn có thể đang chờ review vì thiếu thông tin; xem tab Chờ review.")
            else:
                provinces = st.multiselect("Tỉnh/thành của sự kiện", sorted(ev["province"].dropna().unique()))
                visible = ev[ev["province"].isin(provinces)] if provinces else ev
                st.subheader("Sự kiện theo ngày xuất hiện trên báo")
                event_daily = event_periods(visible)
                if not event_daily.empty:
                    st.line_chart(event_daily[["Sự kiện"]], color="#168b88")
                    st.dataframe(event_daily.reset_index(), hide_index=True, width="stretch")
                    st.download_button("Tải thống kê sự kiện CSV", event_daily.to_csv().encode("utf-8-sig"), "event_daily_statistics.csv", "text/csv")
                st.caption("Mỗi sự kiện chỉ đếm ở ngày bài đầu tiên của vụ đó; không phải ngày xảy ra tai nạn. Thương vong là tổng số đã ghi nhận, không cộng các bài báo về cùng vụ.")
                st.bar_chart(visible["province"].value_counts().rename("Sự kiện"), color="#168b88")
                table(visible, ["event_id", "province", "district", "article_count", "total_fatalities", "total_injuries", "first_published_at", "last_published_at"], "events")
                event_id = st.selectbox("Các bài thuộc sự kiện", visible["event_id"].tolist()) if not visible.empty else None
                if event_id:
                    keys = snapshot["links"].loc[snapshot["links"]["event_id"] == event_id, "article_key"]
                    table(snapshot["articles"][snapshot["articles"]["article_key"].isin(keys)], ["title", "source", "url", "published_at"], "members")
                st.caption("Ô trống ở thương vong nghĩa là chưa có thông tin; không có nghĩa bằng 0. Thời gian biểu đồ là ngày đăng, chưa phải lúc tai nạn xảy ra.")

    with reviews_tab:
        st.subheader("Những bài cần kiểm tra")
        review_type = st.radio("Nhóm review", ["Lọc chưa chắc chắn", "Matching / trích xuất"], horizontal=True)
        if review_type == "Lọc chưa chắc chắn":
            uncertain = articles[articles["accident_label"] == "uncertain"] if "accident_label" in articles else pd.DataFrame()
            table(uncertain, ["title", "source", "filter_reason", "link", "pub_date"], "filter_review")
            st.caption("Nhóm này dùng toàn bộ dữ liệu đang chọn, không phụ thuộc bộ lọc bài báo.")
        elif snapshot is not None:
            review = snapshot["reviews"]
            if not review.empty:
                reasons = review["reasons"].map(reason_text).value_counts().rename("Bài")
                st.bar_chart(reasons, color="#efb44c")
            table(review, ["title", "source", "reasons", "url", "article_key"], "match_review")
        else:
            st.info("Chưa có kho matching để đọc review.")
        st.caption("Dashboard chỉ đọc. Kết quả kiểm duyệt không bị thay đổi khi xem hoặc tải dữ liệu.")


if __name__ == "__main__":
    main()
