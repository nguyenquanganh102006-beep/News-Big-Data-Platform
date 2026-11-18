"""Event-first dashboard; articles are evidence, never accident counts."""
import pandas as pd
import altair as alt
import streamlit as st
import json
from pathlib import Path
from datetime import datetime, timezone
import time

import config
from dashboard.data import discover_datasets, discover_databases, read_database, load_pipeline_counts, load_articles
from dashboard.statistics import local_times, event_periods


def filter_events(events, provinces=(), query="", dates=None):
    result = events.copy()
    if provinces and "province" in result:
        result = result[result["province"].isin(provinces)]
    if query.strip():
        text = pd.Series("", index=result.index, dtype=str)
        for field in ("event_id", "province", "district", "ward", "location_full", "vehicles_involved"):
            if field in result:
                text = text + " " + result[field].fillna("").astype(str)
        result = result[text.str.contains(query.strip(), case=False, regex=False)]
    if dates and len(dates) == 2:
        day = local_times(result, "first_published_at").dt.date
        result = result[day.ge(dates[0]) & day.le(dates[1])]
    return result


def event_metrics(events):
    result = {"events": len(events)}
    for column in ("total_fatalities", "total_injuries"):
        values = pd.to_numeric(events.get(column, pd.Series(index=events.index, dtype=float)), errors="coerce")
        result[column] = values.sum(min_count=1)
        result[f"{column}_known"] = int(values.notna().sum())
    result["provinces"] = events["province"].nunique() if "province" in events else 0
    return result


def metrics(heading, events):
    st.subheader(heading)
    values = event_metrics(events)
    columns = st.columns(4)
    for col, label, key in zip(columns,
                              ["Vụ tai nạn đã ghi nhận", "Tử vong đã ghi nhận", "Bị thương đã ghi nhận", "Tỉnh/thành có vụ"],
                              ["events", "total_fatalities", "total_injuries", "provinces"]):
        value = values[key]
        col.metric(label, "Chưa rõ" if pd.isna(value) else f"{int(value):,}")
    st.caption(f"Có số tử vong ở {values['total_fatalities_known']}/{len(events)} vụ; "
               f"có số bị thương ở {values['total_injuries_known']}/{len(events)} vụ. "
               "Tổng chỉ cộng các giá trị đã biết, mỗi vụ một lần; chưa biết không được coi là 0.")


def render(table):
    @st.fragment(run_every=10)
    def watch_snapshot():
        pointer = Path(config.DATA_DIR).resolve().parent / "data_artifacts/dashboard_current.json"
        if not pointer.exists():
            pointer = Path(config.DATA_DIR) / "dashboard_current.json"
        stamp = pointer.stat().st_mtime_ns if pointer.exists() else None
        key = "snapshot_stamp_" + str(pointer)
        previous = st.session_state.get(key)
        st.session_state[key] = stamp
        now = time.monotonic()
        last = st.session_state.setdefault("last_live_refresh", now)
        if (previous is not None and previous != stamp) or now - last >= 30:
            st.session_state["last_live_refresh"] = now
            st.rerun()
    watch_snapshot()
    root = next(iter(discover_datasets(config.DATA_DIR).values()))
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    databases = discover_databases(root)
    with st.sidebar:
        st.markdown("### Theo dõi tai nạn")
        st.caption("Toàn bộ lịch sử trong bản dữ liệu hiện hành")
        # Prefer the reconciled batch view. Never concatenate overlapping stores.
        batch_lagging = manifest.get("architecture") == "A2" and manifest.get("batch_revision", -1) < manifest.get("revision", 0)
        preferred = "streaming" if batch_lagging else "batch"
        names = sorted(databases, key=lambda name: (preferred not in name, name))
        selected = st.selectbox("Kho tai nạn", names, key="event_store_" + root.name) if names else None
        st.caption("Batch là kết quả tổng hợp; Streaming là kết quả tạm thời. Hai kho được xem riêng để tránh đếm trùng.")
        if st.button("Đọc lại dashboard", width="stretch"):
            st.rerun()
    st.title("Theo dõi tai nạn giao thông")
    st.markdown("Số vụ, thương vong và địa phương — từ các sự kiện đã được hệ thống tổng hợp.")
    if manifest.get("architecture") == "A2":
        st.caption(f"A2 · Kafka → Python/Polars → DuckDB · snapshot {manifest.get('published_at', '')} · tự kiểm tra bản mới mỗi 10 giây.")
        if batch_lagging:
            st.info("Streaming đã có dữ liệu mới hơn kỳ batch gần nhất. Dashboard ưu tiên kho tạm thời; batch sẽ đối soát theo lịch.")
        status_path = Path(config.DATA_DIR).resolve().parent / "data_artifacts/a2/live_status.json"
        if status_path.exists():
            live = json.loads(status_path.read_text(encoding="utf-8"))
            beat = datetime.fromisoformat(live["heartbeat_at"])
            fresh = (datetime.now(timezone.utc) - beat).total_seconds() < 90
            state = live.get("phase", "unknown")
            text = "đang hoạt động" if fresh and state not in ("stopped", "retrying") else "đang chờ/đã dừng hoặc cần kiểm tra"
            st.caption(f"Dịch vụ: {text} · bước {state} · Kafka đã lưu {live.get('counts', {}).get('messages', 0):,} message.")
            if live.get("error"):
                st.warning(f"A2 đang thử lại, chưa bỏ qua dữ liệu lỗi: {live['error']}")
        crawl_path = status_path.with_name("last_crawl.json")
        if crawl_path.exists():
            crawl = json.loads(crawl_path.read_text(encoding="utf-8"))
            st.caption(f"Đợt crawl gần nhất: {len(crawl.get('sources', {}))}/7 nguồn thành công · {crawl.get('records', 0):,} bản ghi.")
            if crawl.get("errors"):
                st.warning("Nguồn đang chờ thử lại: " + ", ".join(crawl["errors"]))
    if not selected:
        st.info("Chưa có kho sự kiện. Chạy luồng xử lý và xuất bản dữ liệu để xem thống kê tai nạn.")
        return
    try:
        snapshot = read_database(databases[selected])
    except Exception as error:
        st.error(f"Chưa đọc được kho tai nạn: {error}")
        return
    events = snapshot["events"].drop_duplicates("event_id")
    with st.sidebar:
        provinces = st.multiselect("Tỉnh/thành", sorted(events["province"].dropna().unique()))
        query = st.text_input("Tìm vụ tai nạn", placeholder="Địa điểm, phương tiện hoặc mã vụ…")
        dates = None
        if st.checkbox("Lọc ngày ghi nhận đầu tiên"):
            valid = local_times(events, "first_published_at").dropna().dt.date
            if not valid.empty:
                dates = st.date_input("Khoảng ngày", value=(valid.min(), valid.max()))
    all_days = filter_events(events, provinces, query)
    visible = filter_events(events, provinces, query, dates)
    today = pd.Timestamp.now(tz="Asia/Ho_Chi_Minh").date()
    today_events = all_days[local_times(all_days, "first_published_at").dt.date.eq(today)]
    st.caption(f"{snapshot['kind']} · mỗi sự kiện được ghép là một vụ theo nhận định của hệ thống. "
               "Đây là các vụ tìm thấy trong dữ liệu báo chí, không phải thống kê đầy đủ ngoài thực tế.")
    metrics("Toàn bộ thời gian", all_days)
    metrics(f"Vụ được ghi nhận mới hôm nay · {today:%d/%m/%Y}", today_events)
    st.caption("Hôm nay và biểu đồ dùng ngày bài báo đầu tiên của vụ theo giờ Việt Nam, chưa phải ngày xảy ra tai nạn. "
               "Hai hàng tổng quan áp dụng tỉnh/thành và từ khóa; khoảng ngày chỉ thu hẹp các tab bên dưới.")
    overview, listing, quality, pipeline = st.tabs(["Thống kê tai nạn", "Danh sách vụ tai nạn", "Cần xác minh", "Luồng dữ liệu"])
    with overview:
        st.subheader("Xu hướng vụ tai nạn theo ngày ghi nhận")
        daily = event_periods(visible)
        if daily.empty:
            st.info("Chưa có vụ với ngày ghi nhận hợp lệ trong lựa chọn này.")
        else:
            st.line_chart(daily[["Sự kiện"]].rename(columns={"Sự kiện": "Vụ tai nạn"}), color="#168b88")
            st.subheader("Thương vong đã ghi nhận")
            period = st.radio("Gộp số liệu theo", ["Ngày", "Tuần", "Tháng"],
                              index=2 if (daily.index.max() - daily.index.min()).days > 90 else 0,
                              horizontal=True, key="casualty_period")
            casualties = daily[["Tử vong đã ghi nhận", "Bị thương đã ghi nhận"]]
            rule = {"Ngày": "D", "Tuần": "W-MON", "Tháng": "MS"}[period]
            casualties = casualties.resample(rule, label="left", closed="left").sum(min_count=1)
            casualties.index.name = "Bắt đầu kỳ"
            chart_data = casualties.reset_index().melt(
                id_vars="Bắt đầu kỳ", var_name="Chỉ tiêu", value_name="Số người")
            chart_data["Kỳ"] = chart_data["Bắt đầu kỳ"].dt.strftime(
                "%m/%Y" if period == "Tháng" else "%d/%m/%Y")
            chart = alt.Chart(chart_data.dropna(subset=["Số người"])).mark_bar(
                cornerRadiusTopLeft=3, cornerRadiusTopRight=3
            ).encode(
                x=alt.X("Kỳ:N", sort=casualties.index.strftime(
                    "%m/%Y" if period == "Tháng" else "%d/%m/%Y").tolist(),
                    title=None, axis=alt.Axis(labelAngle=-35, labelOverlap=True)),
                xOffset=alt.XOffset("Chỉ tiêu:N"),
                y=alt.Y("Số người:Q", title="Số người đã ghi nhận",
                        axis=alt.Axis(tickMinStep=1)),
                color=alt.Color("Chỉ tiêu:N", scale=alt.Scale(
                    domain=["Tử vong đã ghi nhận", "Bị thương đã ghi nhận"],
                    range=["#dc6258", "#3699b8"]),
                    legend=alt.Legend(title=None, orient="top")),
                tooltip=[alt.Tooltip("Kỳ:N", title="Kỳ bắt đầu"), "Chỉ tiêu:N",
                         alt.Tooltip("Số người:Q", format=".0f")],
            ).properties(height=300).configure_view(strokeWidth=0)
            st.altair_chart(chart, width="stretch")
            st.caption("Ngày trống không chứng minh ngoài thực tế không có tai nạn. Thương vong thiếu dữ liệu được giữ trống.")
            st.download_button("Tải thống kê theo ngày", daily.to_csv().encode("utf-8-sig"), "accident_daily.csv", "text/csv")
        left, right = st.columns(2)
        with left:
            st.subheader("Số vụ theo tỉnh/thành")
            if not visible.empty:
                st.bar_chart(visible["province"].fillna("Chưa rõ").value_counts().rename("Vụ tai nạn"))
        with right:
            st.subheader("Thương vong theo tỉnh/thành")
            if not visible.empty:
                grouped = visible.assign(province=visible["province"].fillna("Chưa rõ")).groupby("province")
                summary = grouped[["total_fatalities", "total_injuries"]].sum(min_count=1)
                summary.insert(0, "Số vụ", grouped.size())
                st.dataframe(summary.rename(columns={"total_fatalities": "Tử vong đã biết", "total_injuries": "Bị thương đã biết"}), width="stretch")
    with listing:
        st.subheader(f"{len(visible):,} vụ tai nạn")
        columns = ["event_id", "province", "district", "ward", "location_full", "vehicles_involved",
                   "total_fatalities", "total_injuries", "first_published_at", "last_published_at", "article_count"]
        table(visible, columns, "accident_events")
        st.download_button("Tải danh sách vụ tai nạn", visible.to_csv(index=False).encode("utf-8-sig"), "accident_events.csv", "text/csv")
        if not visible.empty:
            event_id = st.selectbox("Xem bằng chứng của vụ", visible["event_id"].tolist())
            event = visible.loc[visible["event_id"] == event_id].iloc[0]
            st.write(f"Địa điểm: {event.get('location_full') or event.get('province') or 'Chưa rõ'}")
            keys = snapshot["links"].loc[snapshot["links"]["event_id"] == event_id, "article_key"]
            members = snapshot["articles"][snapshot["articles"]["article_key"].isin(keys)]
            with st.expander(f"Nguồn tin và bằng chứng · {len(members)} bài", expanded=True):
                table(members, ["title", "source", "url", "published_at", "fatalities", "injuries"], "accident_evidence")
            st.caption("Nhiều bài có thể nói về cùng một vụ. Không cộng thương vong từ các bài này.")
    with quality:
        st.subheader("Thông tin cần xác minh trước khi thống kê thành vụ")
        st.caption("Các bản tin chưa ghép được vào vụ được giữ riêng, chưa cộng vào số vụ hoặc thương vong ở tổng quan. "
                   "Mục này dùng toàn kho, không áp dụng bộ lọc vụ tai nạn.")
        table(snapshot["reviews"], ["title", "source", "reasons", "url"], "accident_reviews")
        with st.expander("Tin chưa xác định thuộc phạm vi tai nạn"):
            articles, errors = load_articles(root)
            for error in errors:
                st.warning(error)
            uncertain = articles[articles["accident_label"] == "uncertain"] if "accident_label" in articles else pd.DataFrame()
            table(uncertain, ["title", "source", "filter_reason", "link"], "uncertain_evidence")
    with pipeline:
        st.subheader("Theo dõi xử lý dữ liệu nguồn")
        st.caption("Các con số đầu luồng đếm bài/bản ghi; chỉ bước ghép sự kiện mới tạo số vụ. "
                   "Số liệu toàn snapshot, không áp dụng bộ lọc vụ tai nạn.")
        counts = load_pipeline_counts(root)
        if counts:
            stages = {"bronze": "Bronze · dữ liệu crawl", "silver": "Silver · bài duy nhất",
                      "content_dedup": "Khử trùng nội dung", "filter": "Lọc phạm vi tai nạn",
                      "extraction": "Trích xuất thông tin", "gold": "Gold · tổng hợp vụ", "streaming": "Streaming"}
            labels = {"records": "Số bản ghi", "snapshots": "Lần crawl", "sources": "Nguồn báo",
                      "input": "Bài đầu vào", "retained": "Bài giữ lại", "duplicates": "Bài trùng",
                      "accident": "Bài về tai nạn", "uncertain": "Bài chưa rõ phạm vi",
                      "not_accident": "Bài bị loại", "articles": "Bài đã lưu", "events": "Vụ đã tạo",
                      "event_articles": "Bài đã gắn vào vụ", "unassigned_articles": "Bài chưa gắn vào vụ",
                      "pending_reviews": "Bản tin chờ xác minh", "receipts": "Bài đã tiếp nhận"}
            rows = [{"Giai đoạn": stages.get(stage, stage), "Chỉ số": labels.get(key, key), "Giá trị": str(value)}
                    for stage, values in counts.items() if isinstance(values, dict)
                    for key, value in values.items()]
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        else:
            st.info("Snapshot chưa có thống kê luồng xử lý.")
