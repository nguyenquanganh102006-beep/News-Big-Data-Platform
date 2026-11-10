"""Publication-time statistics; no invented incident times or missing casualties."""
import pandas as pd

LABELS = {"accident": "Tai nạn", "uncertain": "Cần xem xét", "not_accident": "Không phải tai nạn"}


def local_times(frame, column="pub_date"):
    values = frame[column] if column in frame else pd.Series(index=frame.index, dtype=object)
    return pd.to_datetime(values, utc=True, errors="coerce").dt.tz_convert("Asia/Ho_Chi_Minh")


def article_periods(frame, frequency="D", dates=None):
    if frequency not in ("D", "W-MON", "MS"):
        raise ValueError("Unsupported frequency")
    times = local_times(frame)
    valid = times.notna()
    if not valid.any():
        return pd.DataFrame()
    # Strip timezone only after converting to local wall-clock time.
    index = pd.DatetimeIndex(times[valid].dt.tz_localize(None))
    work = pd.DataFrame({label: (frame.loc[valid, "accident_label"].to_numpy() == code).astype(int)
                         for code, label in LABELS.items()}, index=index)
    work["Tổng bài"] = 1
    rule = dict(rule=frequency, label="left", closed="left")
    result = work.resample(**rule).sum()
    if dates and len(dates) == 2:
        bounds = pd.Series([1, 1], index=pd.to_datetime([dates[0], dates[1]])).resample(**rule).sum().index
        result = result.reindex(bounds, fill_value=0)
    result["Tỷ lệ tai nạn (%)"] = (result["Tai nạn"].div(result["Tổng bài"].replace(0, float("nan"))) * 100).round(1)
    result.index.name = "Bắt đầu kỳ"
    return result


def source_statistics(frame):
    if frame.empty or "accident_label" not in frame:
        return pd.DataFrame()
    result = pd.crosstab(frame["source"], frame["accident_label"]).reindex(columns=list(LABELS), fill_value=0).rename(columns=LABELS)
    result["Tổng bài"] = result.sum(axis=1)
    result["Tỷ lệ tai nạn (%)"] = (100 * result["Tai nạn"] / result["Tổng bài"]).round(1)
    return result.sort_values("Tổng bài", ascending=False)


def event_periods(events):
    times = local_times(events, "first_published_at")
    valid = times.notna()
    if not valid.any():
        return pd.DataFrame()
    work = pd.DataFrame({"Sự kiện": 1}, index=pd.DatetimeIndex(times[valid].dt.tz_localize(None)))
    for field, label in (("total_fatalities", "Tử vong đã ghi nhận"), ("total_injuries", "Bị thương đã ghi nhận")):
        values = pd.to_numeric(events.loc[valid, field], errors="coerce")
        work[label] = values.to_numpy()
    # min_count prevents all-null casualties from being displayed as zero.
    result = work.resample("D").sum(min_count=1)
    result["Sự kiện"] = result["Sự kiện"].fillna(0).astype(int)
    result.index.name = "Ngày xuất hiện đầu tiên"
    return result
