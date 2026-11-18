"""Read a local event database and show a short, human-readable summary."""

import argparse
from pathlib import Path

import duckdb

from config import EVENT_DATABASE_PATH


def show_database(database_path=EVENT_DATABASE_PATH, limit=10):
    path = Path(database_path)
    if not path.is_file():
        raise FileNotFoundError(f"Chưa có database tại {path}. Chạy python -m main --step=5 trước.")
    if limit < 1:
        raise ValueError("limit phải lớn hơn 0")
    with duckdb.connect(str(path), read_only=True) as connection:
        articles = connection.execute("SELECT count(*) FROM articles").fetchone()[0]
        events = connection.execute("SELECT count(*) FROM accident_events").fetchone()[0]
        pending = connection.execute("SELECT count(*) FROM match_reviews WHERE status='pending'").fetchone()[0]
        print(f"Database: {path.resolve()}")
        print(f"Bài báo đã lưu: {articles}; sự kiện: {events}; trường hợp chờ xem xét: {pending}.")
        rows = connection.execute(
            "SELECT e.event_id,a.title,e.province,e.article_count,e.total_fatalities,e.total_injuries "
            "FROM accident_events e JOIN articles a ON e.anchor_article_key=a.article_key "
            "ORDER BY e.anchor_published_at,e.event_id LIMIT ?", [limit],
        ).fetchall()
        for event_id, title, province, count, fatalities, injuries in rows:
            deaths = "chưa rõ" if fatalities is None else str(fatalities)
            hurt = "chưa rõ" if injuries is None else str(injuries)
            print(f"\n{title}\n  Mã sự kiện: {event_id}\n  Địa điểm: {province}; {count} bài liên quan.")
            print(f"  Tử vong: {deaths}; bị thương: {hurt}.")
        if pending:
            print("\nCác bài chờ xem xét được giữ trong bảng match_reviews; chưa tính thành vụ mới.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Xem nhanh dữ liệu sự kiện đã lưu")
    parser.add_argument("--database", type=Path, default=EVENT_DATABASE_PATH)
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    show_database(args.database, args.limit)
