# PLAN BENCHMARK NHANH: A2, A4, A5

**Dự án:** News Big Data Platform  
**Nhánh tham chiếu:** `fix/23-24`  
**Mục tiêu:** Chạy thử ba kiến trúc trên cùng dữ liệu, xuất kết quả benchmark so sánh. Không xây dashboard mới, không tối ưu thuật toán trong đợt này.

## 1. Kiến trúc thử nghiệm

| ID | Broker | Processing | Storage | Ghi chú |
|---|---|---|---|---|
| A2 | Kafka | Python / Polars | DuckDB | Một writer DuckDB; tận dụng logic hiện tại |
| A4 | Kafka | Spark Structured Streaming | PostgreSQL | `foreachBatch`, ghi transactional |
| A5 | Kafka | Spark Structured Streaming | Delta Lake + DuckDB | Spark ghi Delta; DuckDB dùng để truy vấn bản snapshot tương thích (hoặc Parquet export) |

**Giữ cố định:** dữ liệu đầu vào, thứ tự bài, cấu hình matching, embedding model, ngưỡng lọc, phần cứng, cấu hình Kafka và cách tính thời gian.

**Phạm vi benchmark chính:** từ lúc producer gửi bài vào Kafka đến lúc dữ liệu đã được commit vào storage. Nếu dùng Silver đã trích xuất, phải ghi rõ đây là benchmark *Kafka → xử lý/matching → lưu trữ*, không phải RSS end-to-end.

## 2. Chuẩn bị chung (ưu tiên làm trước)

- [ ] Checkout `fix/23-24`, tạo branch `benchmark/a2-a4-a5`.
- [ ] Xuất `benchmark/data/articles.jsonl` từ Silver đã chuẩn hóa; mỗi dòng có `article_key`, `source`, `published_at`, nội dung và các trường extraction cần thiết.
- [ ] Tạo 3 tập kiểm thử: **1.000**, **10.000**, **20.000** bài (nếu dữ liệu Silver tai nạn không đủ, sử dụng bài Silver nói chung hoặc dữ liệu tổng hợp; ghi rõ tập nào và không giả vờ đó là 20K vụ tai nạn).
- [ ] Tạo Docker Compose tối thiểu: **Kafka (KRaft), Spark, PostgreSQL**. DuckDB và Polars chạy trong Python; Delta Lake trên volume local.
- [ ] Tạo producer dùng chung `benchmark/producer.py`: gửi JSON vào một topic; thêm `run_id`, `sent_at` để đo latency.
- [ ] Tạo schema đầu ra chung: `article_key`, `event_id`, `status`, `processed_at`, `run_id` (và trường bổ sung nếu cần).
- [ ] Tạo script reset topic/consumer group và database/output giữa các lần chạy.

## 3. Triển khai ba adapter tối thiểu

### A2: Kafka + Python/Polars + DuckDB
- [ ] Consumer Kafka nhận message; gọi lại xử lý hiện có.
- [ ] Ghi DuckDB bằng **một writer**, transaction theo batch.
- [ ] Commit Kafka offset sau khi DB commit; xử lý idempotent theo `article_key`/`run_id`.
- [ ] Log `received`, `committed`, `failed`, `latency_ms`.

### A4: Kafka + Spark Structured Streaming + PostgreSQL
- [ ] Spark `readStream.format("kafka")`, parse JSON theo schema chung.
- [ ] `foreachBatch`: gọi phần logic tương đương A2, ghi PostgreSQL theo batch.
- [ ] Dùng unique key + upsert để tránh duplicate sau retry.
- [ ] Ghi checkpoint riêng cho từng `run_id`.

### A5: Kafka + Spark Structured Streaming + Delta Lake + DuckDB
- [ ] Spark đọc cùng topic/schema và xử lý như A4.
- [ ] Ghi Delta Lake theo micro-batch, đảm bảo idempotency khi retry.
- [ ] Xuất snapshot Parquet (hoặc dùng khả năng đọc Delta đã xác minh tương thích) để DuckDB chạy truy vấn analytics.
- [ ] Tách thời gian **ingestion/commit Delta** và **thời gian snapshot → query DuckDB**; không trộn hai số.

> **Nguyên tắc công bằng:** Nếu không tái sử dụng được đúng cùng logic matching trên Spark, benchmark trước phần ingest + parse + transform + storage chung cho cả ba, và báo cáo riêng benchmark matching bằng Python. Không so throughput hai pipeline thực hiện khối lượng công việc khác nhau.

## 4. Kịch bản chạy

| Test | Input | Producer rate | Consumer | Mục đích |
|---|---:|---:|---|---|
| Smoke | 100 bài | 10 bài/s | 1 | Kiểm tra output và lỗi |
| T1 | 1.000 bài | 50 bài/s | 1 | Đo latency |
| T2 | 10.000 bài | 200 bài/s | 1 | Đo throughput và tài nguyên |
| T3 | 20.000 bài | Gửi nhanh nhất có thể | 1 | Đo backlog và thời gian drain |

Chạy **ít nhất 3 lần/kiến trúc/workload** nếu đủ thời gian. Khởi động trước và warm-up model; reset output/checkpoint giữa các run. Có thể bắt đầu với T2 để lấy kết quả sớm.

## 5. Metrics bắt buộc

| Metric | Cách đo |
|---|---|
| `throughput_articles_s` | Số bài commit thành công / thời gian từ message đầu tiên đến commit cuối |
| `latency_p50_ms`, `latency_p95_ms` | `committed_at - sent_at` theo từng bài, đồng bộ clock |
| `total_duration_s` | Tổng thời gian xử lý workload |
| `peak_ram_mb` | RAM đỉnh của các tiến trình liên quan |
| `avg_cpu_pct` | CPU trung bình trong khoảng benchmark |
| `failed_count` | Số bài lỗi |
| `missing_count` | Bài gửi nhưng không có trong output |
| `duplicate_count` | Bài được ghi trùng không mong muốn |
| `output_count` | Tổng bài duy nhất đã commit |
| `query_p95_ms` | p95 trên cùng tập SQL analytics, đo riêng ingestion |

**Tối thiểu 3 query analytics:** đếm bài theo nguồn; đếm sự kiện theo tỉnh/ngày; top sự kiện theo số bài liên kết. Nếu dùng dữ liệu không có nhãn sự kiện, chỉ đo query có trường tương ứng, không tự tạo số liệu.

## 6. File kết quả

`benchmark/results/runs.csv`:

```csv
architecture,workload,run_id,input_count,output_count,total_duration_s,throughput_articles_s,latency_p50_ms,latency_p95_ms,peak_ram_mb,avg_cpu_pct,failed_count,missing_count,duplicate_count,query_p95_ms
```

`benchmark/results/summary.csv`: median theo `architecture,workload` và độ dao động giữa các lần chạy.

`benchmark/results/report.md`: bảng so sánh A2/A4/A5; biểu đồ throughput, latency p95, RAM; lỗi/giới hạn; kiến trúc đề xuất.

## 7. Tiêu chí quyết định

1. **Loại** cấu hình có mất dữ liệu, sai số lượng đầu ra hoặc không phục hồi đúng sau retry.
2. Trong các cấu hình đạt correctness, so **throughput**, **p95 latency**, **RAM** và **query latency**.
3. Nếu khác biệt hiệu năng nhỏ, ưu tiên phương án **đơn giản, dễ chạy trên máy hiện tại**.
4. Nếu A4/A5 chỉ thắng khi dữ liệu lớn, ghi rõ **ngưỡng workload bắt đầu có lợi**, không kết luận Spark luôn nhanh hơn.

## 8. Thứ tự thực hiện nhanh nhất

**Buổi 1:** Chuẩn bị dataset, Docker Compose, producer, metrics; chạy xong A2.  
**Buổi 2:** Adapter A4 và A5; chạy T1–T3, xuất CSV và báo cáo ngắn.

**Definition of Done:** Ba kiến trúc đều có log chạy thật, mỗi kiến trúc có kết quả ít nhất T1 và T2, có `runs.csv`, `summary.csv`, `report.md`, nêu rõ workload và giới hạn của phép so sánh.

## 9. Kết quả triển khai ngày 17/11/2026

Đã triển khai trên nhánh `benchmark/a2-a4-a5`, theo phương án **ingest + parse + transform chung + storage** nêu trong nguyên tắc công bằng. Matching Python đo riêng; không đưa kết quả của nó vào throughput Kafka.

- 21 lượt đo kiến trúc: T1/T2 mỗi kiến trúc 3 lượt, T3 mỗi kiến trúc 1 lượt.
- Đủ output, không mất/trùng bài; digest nội dung và kết quả SQL khớp giữa các kiến trúc. Đã thử phát lại cùng microbatch sau commit; chưa kiểm thử kill/restart hoặc lỗi hạ tầng.
- Matching Python: 3 lượt trên 322 bài, median 5,826 giây; warm-up model/cache 48,837 giây ghi riêng.
- **Definition of Done đã đạt** cho phạm vi benchmark chung. Các truy vấn event bỏ qua vì workload không có event_id đáng tin; dùng ba truy vấn thống kê bài có cùng schema, không tự tạo số vụ.
- Stack benchmark đã dừng, giữ nguyên volume và log; không thay đổi Gold/dashboard chính.

Chi tiết: [báo cáo kết quả](../benchmark/results/report.md), [hướng dẫn chạy](../benchmark/README.md), [trạng thái và giới hạn](../benchmark/STATUS.md).

## 10. Bổ sung baseline Redis theo yêu cầu

- **B0:** Redis 7.4 (AOF/everysec) → ArticleQueue hiện hành → Python/Polars → DuckDB; một bài/transaction, ACK sau commit.
- Cùng dataset, transform và schema đầu ra với A2/A4/A5; chưa đưa toàn bộ lọc/trích xuất/matching vào thời gian đo.
- Đã chạy T1/T2 mỗi tải 3 lượt, T3 một lượt; bảng chính có thêm 7 lượt, tổng 28 lượt.
- T1 median khoảng 50 bài/giây, p95 36,3 ms; T2 median 69,5 bài/giây, p95 89,0 giây; T3 58,45 bài/giây.
- A2/T2 đối chứng với ledger đệm lưu riêng trong `baseline_control.csv`, không trộn vào median Kafka cũ.
- Chênh lệch B0/A2 gồm cả xử lý/commit từng bài so với gom batch; chưa thể suy ra Kafka nhanh hơn Redis chỉ từ bảng này.
- Năm tests thành công, gồm phục hồi sau commit trước ACK; baseline dùng Redis Docker riêng, không chạm Redis/Memurai và Gold/dashboard chính.
