# Tiến độ triển khai benchmark

Nhánh: `benchmark/a2-a4-a5`, tạo từ `fix/23-24`.

Đã triển khai:

- Xuất cố định 20.745 bài Silver thật; manifest có SHA256, số nhãn và 7 nguồn.
- Stack Kafka KRaft/PostgreSQL/Python/Spark/Delta riêng, Docker Linux volumes.
- Producer cùng payload/rate, bốn cấu hình B0/A2/A4/A5, commit ledger và kiểm tra đầu ra.
- A2 ghi Polars/Arrow batch vào DuckDB, một writer; A4 foreachBatch ghi
  transaction PostgreSQL; A5 foreachBatch ghi Delta với transaction ID ổn định.
- Bộ chạy tuần tự, namespace topic/group/checkpoint/output mới cho mỗi run,
  giám sát RAM/CPU của cả ba container, lưu phiên bản và hash code.
- Đối chiếu khóa, số lượng, nội dung, kết quả SQL và thử phát lại batch đã commit.
- Script tổng hợp CSV, báo cáo Markdown và biểu đồ PNG; script reset có giới hạn phạm vi.
- Năm kiểm thử hồi quy chạy thành công trong image benchmark, gồm phục hồi queue Redis sau commit trước ACK.

Phạm vi được chọn theo phương án dự phòng trong plan: **ingest → parse → transform chung → storage**.
Không đưa lọc/trích xuất/matching/embedding vào thời
gian đo kiến trúc; matching Python đã đo riêng 3 lượt trên 322 bài với model mặc định,
median 5,826 giây, warm-up model/cache 48,837 giây được ghi riêng. Không gọi workload 20K bài là
20K vụ tai nạn. Truy vấn event bị bỏ qua khi không có event_id đáng tin.

Các pilot qua filesystem Windows và adapter ghi từng dòng được lưu riêng trong
`results/pilot_*.csv`, không đưa vào bảng so sánh chính. Log lỗi phát triển được
giữ ở `results/logs/`, không xóa để che lỗi.

Kết quả đợt Kafka ban đầu: **21 lượt đo kiến trúc thành công** — T1/T2 mỗi kiến trúc 3 lượt,
T3 mỗi kiến trúc 1 lượt. Cả 21 có đủ output, không mất/trùng bài, khớp digest nội
dung và kết quả SQL giữa các kiến trúc; qua thử phát lại microbatch đã commit.
Chưa kiểm thử kill/restart toàn tiến trình hoặc lỗi hạ tầng. Năm unit tests hiện tại thành công.

Bổ sung baseline B0: Redis 7.4 AOF/everysec + ArticleQueue hiện hành + Polars +
DuckDB, một bài/transaction. Đã xong T1/T2 mỗi tải 3 lượt và T3 một lượt, thêm
7 lượt vào bảng chính, tổng **28 lượt**. Các pilot Redis flush log từng bài được
giữ riêng; ledger các lượt chính được đệm để tránh I/O đo lường qua Windows.
Lượt A2/T2 đối chứng dùng ledger đệm được giữ riêng ở `results/baseline_control.csv`.
Đối chứng đạt 196,02 bài/giây, gần median Kafka cũ 198,06 bài/giây; đầu ra khớp.
Baseline đo cùng transform/schema benchmark, không chạy nguyên ArticleProcessor/NLP.
Do khác chính sách commit với A2, không quy chênh lệch throughput cho broker riêng lẻ.
Redis còn 4.711 message của namespace pilot đã hủy (~16,68 MiB key memory), không
được tiêu thụ vào các lượt chính. RAM baseline có bao gồm phần tồn này; không coi
là footprint Redis sạch, xem caveat và JSON chẩn đoán trong báo cáo.

Definition of Done trong plan đã đạt. Kết quả: `results/runs.csv`,
`results/summary.csv`, `results/report.md`, `results/comparison.png`.
Stack benchmark đã dừng để giải phóng RAM; volume/output/log vẫn giữ lại.
Dashboard chính vẫn phản hồi HTTP 200; không xuất bản kết quả benchmark vào Gold/dashboard.
