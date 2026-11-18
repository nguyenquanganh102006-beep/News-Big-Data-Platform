# News-Big-Data-Platform

## Luồng chính A2

`Bronze → Kafka → Python/Polars → Silver → streaming/batch matching → DuckDB → dashboard`.

```powershell
$env:PYTHONPATH='src'
$env:PYTHONUTF8='1'
docker compose up -d --wait kafka
.venv/Scripts/python.exe -m main
```

Dịch vụ tự quét Bronze mỗi 5 giây, crawl RSS mỗi 5 phút và đối soát batch mỗi
15 phút khi dữ liệu thay đổi. Producer không đọc Silver. Dashboard tự nhận snapshot
mới, mặc định xem toàn bộ lịch sử: `http://localhost:8501`.

Chạy lại lịch sử và một lượt crawl mới rồi thoát:

```powershell
.venv/Scripts/python.exe -m main --rebuild --history --crawl-once --once
```

`--rebuild` tạo namespace Kafka và thế hệ dữ liệu dẫn xuất mới, giữ nguyên Bronze
và các thế hệ cũ. Dừng dịch vụ an toàn: `.venv/Scripts/python.exe -m main --stop`.
Các lệnh `--step` cũ là công cụ bảo trì legacy, không phải daemon A2.

Chi tiết kiến trúc, checkpoint và cách vận hành: [A2 đang dùng](docs/a2_live_pipeline.md).

Hướng dẫn: [cài đặt](docs/setup.md), [pipeline](docs/flow.md),
[Redis Queue và Streaming Consumer 4.1–4.2](docs/details/streaming.md).
