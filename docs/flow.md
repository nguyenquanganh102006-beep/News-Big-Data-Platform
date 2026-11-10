# Flow

## Luồng chính

RSS → Bronze → làm sạch/dedup → lọc và trích xuất thông tin → Silver theo bài → phần 3 gom sự kiện → Gold (DuckDB).

Điểm vào `src/main.py` nhận `--step` kiểu int: `0` (mặc định) chạy toàn bộ, `1` chạy crawlers, `2` chạy preprocessors, `3` chạy filters, `4` chạy extractors, `5` chạy phần sự kiện và lưu database. Các thư mục dữ liệu được tạo trước khi chạy.

Sau `python -m pip install -e .`, chạy từ thư mục gốc bằng `python -m main`.
Không cần đặt thêm `PYTHONPATH`. Hướng dẫn dễ đọc và kết quả chạy dữ liệu thật:
[lưu sự kiện vào database](details/event_database_guide.md).

Chi tiết: [luồng lọc](details/accident_filter/pipeline.md).

Luồng streaming 4.1–4.2 chạy riêng: bài Bronze → Producer → Redis List →
làm sạch/lọc/trích xuất → tìm ứng viên/matching → sự kiện tạm trong DuckDB.
Xem mục 7 bên dưới; `main --step` vẫn dành cho luồng xử lý hiện có.

## Tiêu chí và đánh giá bộ lọc tai nạn

Phiên bản hiện tại: [rules-v3-road](details/accident_filter/rules_v3.md), áp dụng
phạm vi đường bộ đã chốt; nhận cháy/vật rơi đè xe trên đường và loại bài chỉ cập
nhật xử lý sau vụ việc. Trường hợp thiếu bằng chứng vẫn giữ ở hàng review.

Xem [tiêu chí](details/accident_filter/criteria.md) và [cách sinh kết quả đánh giá](details/accident_filter/rules_v1.md). Bộ nhãn trợ lý tự gán và báo cáo điểm số cũ đã được loại bỏ. Đánh giá cần dữ liệu tham chiếu được kiểm duyệt, truyền qua `--samples`; kết quả sinh ra nằm trong `data/evaluation/accident_filter/` và không commit vào Git.

## Folder architecture

```text
News-Big-Data-Platform/
|-- docs/               # Documentations 
|-- data/               # Bronze, Silver và Gold
|-- data_artifacts/     # Dashboard snapshots và diagnostics
    |-- bronze/             # Raw data crawled from sources 
    |-- silver/             # Bài đã làm sạch
        |-- deduplicated/  # Task 2.2: cờ bài trùng và manifest
        |-- filtered/       # Kết quả lọc, chỉ gồm bài gốc
        |-- accidents/      # Bài đã trích xuất, đầu vào phần 3
    |-- gold/               # Database sự kiện và bản xuất từ database
|-- src/                # Source code of the program
    |-- config/             # Contains all the configs, schemas, global constants, ... of the program
    |-- crawlers/           # Crawlers
    |-- preprocessors/      # Cleaning and dedup
    |-- filters/            # Accident filtering
    |-- extractors/         # Accident information extraction
    |-- events/             # Candidate retrieval, matching and DuckDB storage
    |-- streaming/          # Redis producer, consumer and provisional events
    |-- main.py             # Main flow
```


## Partial flows

### 1. Config

+ structure:

```text
News-Big-Data-Platform/
|-- src/
    |-- config/
        |-- crawlers.py     # Crawler configs
        |-- ...
```


### 2. Crawler

+ Folder relationship structure

```text
News-Big-Data-Platform/
|-- data/
    |-- bronze/                 # Results saved to this folder
|-- src/
    |-- config/
        |-- crawlers.py             # Crawler configs
    |-- crawlers/
        |-- rss_crawler.py          # Handle crawling RSS Feed
        |-- run.py                  # Run the crawling pipeline
```

+ Input: `RSS_SOURCES` defined at `src/config/crawlers.py`

+ Run pipeline
```bash
cd src
python -m crawlers.run
```

+ Output: `data/bronze/<source>/YYYYMMDD_HHMMSS.parquet`.

Mỗi lần chạy crawler tạo một file riêng cho từng nguồn, timestamp theo giờ Việt Nam (UTC+7). Ví dụ: `data/bronze/vnexpress/20261024_153000.parquet`. Thư mục theo nguồn được tạo tự động. Nếu trùng timestamp, thêm hậu tố `_000001`, `_000002`, ... để không ghi đè file cũ. Các file Bronze cũ nằm trực tiếp trong `data/bronze/` được giữ nguyên.

### 3. Preprocessors

+ Folder relationship structure

```text
News-Big-Data-Platform/
|-- data/
    |-- bronze/                 # Input taken from here
    |-- silver/                 # Output saved here
|-- src/
    |-- config/
        |-- crawlers.py             # Crawler configs
    |-- preprocessors/
        |-- rss_vnexpress.py        # RSS preprocessors for source "vnexpress"
        |-- rss_tuoitre.py          # Another example
        |-- [type]_[source].py      # General format of each source
        |-- ...                     # Analogous files followed above format
        |-- utils.py                # Contains all utils, helpers, ...
        |-- run.py                  # Main file to run all the preprocessors
```

+ Input: các snapshot `.parquet` trong `data/bronze/<source>/` và snapshot lịch sử trong `data_artifacts/diagnostics/`. Silver được tích lũy sau khi loại trùng trong batch và so với lịch sử.

+ Run pipeline
```bash
cd src
python -m preprocessors.run
```

+ Output: `.parquet` files saved in `data/silver/`

Chi tiết làm sạch: [EDA preprocessors](details/preprocessor_eda.md). Cơ chế chọn file, chuẩn hóa URL và lưu lịch sử: [dedup preprocessors](details/preprocessor_dedup.md).

### 4. Filters và phát hiện bài trùng 2.2

+ Input: Silver tích lũy của cả 7 nguồn RSS.
+ Trước khi phân loại, `run_filters()` gọi `run_content_dedup()`; TF-IDF + cosine so tiêu đề và mô tả trong cửa sổ 24 giờ, ngưỡng mặc định `>= 0.85`.
+ Bài trùng được giữ trong `data/silver/deduplicated/` với `is_duplicate`, `duplicate_of_article_key` và điểm tương đồng. Chỉ bài gốc đi vào phân loại.
+ Hàm phân loại: `classify_accident()`.
+ Output: `classified.parquet`, `accident.parquet`, `not_accident.parquet`, `uncertain.parquet` trong `data/silver/filtered/<source>/`.

Chi tiết: [Task 2.2 — Duplicate Article Detection](details/content_duplicate_detection.md). Ghi chú EDA HTML VietnamPlus cũ ở [preprocessor_eda.md](details/preprocessor_eda.md) được giữ nguyên.

### 5. Extractors

+ Input: `data/silver/filtered/<source>/accident.parquet`, dùng toàn bộ `title` và `description`.
+ Hàm: `run_extractors()` gọi các bước trích xuất bằng luật, regex và từ điển.
  Riêng VnExpress, mở bài đã được filter chọn để đọc nhãn tỉnh/thành ở đầu bài.
+ Output: `data/silver/accidents/<source>.parquet`, thêm địa điểm, phương tiện, thương vong, loại sự cố và bằng chứng.
  Việc lấy nhãn địa điểm VnExpress thuộc phần 2; phần 3 nhận trường `province`
  từ Silver, không tự tải trang hay trích xuất lại tỉnh.

Chi tiết: [trích xuất thông tin tai nạn](details/accident_extraction.md).

### 6. Sự kiện tai nạn (3.1, 3.2, 3.3)

Input: `data/silver/accidents/<source>.parquet` của cả 7 nguồn RSS. Đọc chung
các nguồn, sắp bài theo ngày đăng rồi khóa bài. Kho sự kiện được đọc từ DuckDB;
sự kiện vừa tạo được dùng ngay để so sánh bài tiếp theo.

```bash
python -m main --step=5
python -m events.inspect
```

- 3.1 tìm ứng viên cùng tỉnh trong bán kính đăng bài ±48 giờ; tin theo dõi đăng
  muộn có thể được xét xa hơn khi trùng ngày vụ việc và địa điểm cụ thể, không
  có mâu thuẫn.
- 3.2 lập hồ sơ vụ việc, so TF-IDF/embedding cùng địa điểm, ngày xảy ra, đối tượng
  và phương tiện; kiểm tra bằng chứng với từng thành viên của cụm. Bài mơ hồ vào
  review. Chi tiết: [matching v2](details/event_matching_v2.md).
- 3.3 lưu vào `data/gold/events/accident_events.duckdb`; xuất Parquet trong
  `data/gold/events/exports/`.

Chạy lại giữ nguyên ID/liên kết đã lưu, không cộng trùng số bài hoặc thương vong.
Bài chưa có sự kiện được cập nhật và xét lại khi Silver bổ sung thông tin; lý do
chờ cũ được đóng và giữ làm lịch sử. Bài đã có sự kiện mà Silver thay đổi được tự
cập nhật, tính lại thông tin vụ và giữ cùng liên kết. Bản trước khi sửa được
lưu trong `article_revisions`; không đưa vào hàng chờ chỉ vì `changed_input`.
Một lần nhập lỗi thì hủy toàn bộ lần ghi đó. Chỉ chạy một tiến trình ghi database.

`data/silver/<source>.parquet` là lịch sử bài đã làm sạch của preprocessor;
`data/silver/accidents/<source>.parquet` là tập bài tai nạn đã trích xuất, đầu vào
của phần 3. Gold chỉ được ghi bởi bước sự kiện, không chứa đầu vào bài báo thô.

Chi tiết: [bộ lọc ứng viên 3.1](details/event_retrieval.md) và
[hướng dẫn database](details/event_database_guide.md).

### 7. Streaming (4.1 Redis Queue, 4.2 Streaming Consumer)

+ Folder relationship structure:

```text
News-Big-Data-Platform/
|-- compose.yaml                 # Redis local, persistent volume and AOF
|-- src/
    |-- config/
        |-- streaming.py         # Redis and streaming database configuration
    |-- streaming/
        |-- producer.py          # Enqueue Bronze articles
        |-- message.py           # Validate JSON and article identity
        |-- queue.py             # Claim, ACK, recovery and retry
        |-- pipeline.py          # Reuse cleaning, filtering, extraction and matching
        |-- repository.py        # Isolated provisional tables
        |-- consumer.py          # Consumer loop and writer lock
        |-- run.py               # Streaming entry point
|-- tests/test_streaming.py
|-- scripts/smoke_streaming.py    # Replay Bronze into an isolated test database
|-- docs/details/streaming.md
```

+ Input: một bài theo schema RSS Bronze, kèm `source` thuộc một trong 7 RSS source.
  Producer gọi `enqueue_article()` sau khi lưu
  Bronze; hiện chưa tự động thay luồng crawler cũ.
+ Config: `src/config/streaming.py`, biến môi trường trong `.env.example`:
  `REDIS_URL`, `REDIS_ARTICLE_QUEUE`, `STREAM_DATABASE_PATH`.
+ Run pipeline từ gốc repository, sau khi cài `pip install -e .`:

```powershell
docker compose up -d --wait redis
docker compose exec -T redis redis-cli ping
.venv/Scripts/python.exe -m streaming.run
```

Terminal khác gửi một file JSON Bronze:

```powershell
.venv/Scripts/python.exe -m streaming.producer article.json
```

+ Output: mặc định `data/gold/streaming/provisional.duckdb`, gồm
  `provisional_events`, `provisional_articles`, `provisional_event_articles`,
  review và receipt chống xử lý lặp. Không sửa bảng sự kiện chính thức phần 3.
+ Chỉ chạy một Consumer cho mỗi cặp queue/database. Ctrl+C dừng an toàn sau
  bài hiện tại. Message lỗi được retry hoặc giữ trong `<queue>:dead`.
+ `python -m streaming.consumer` vẫn chạy được như lệnh trực tiếp tương đương.
  Matching dùng chung với batch qua `events.service.MatchingService`; mặc định
  streaming xét 24 giờ trước timestamp bài, gồm hai biên, loại sự kiện tương lai.

Contract JSON, truy vấn DB, kiểm thử và giới hạn:
[hướng dẫn streaming](details/streaming.md).


### 8. Batch 4.3 và matching dùng chung 4.4

Silver đã trích xuất (`data/silver/accidents/*.parquet`) → dedup → matching giai đoạn 3
→ dựng lại canonical trong staging → kiểm tra → thay database chính thức.

```powershell
.venv/Scripts/python.exe -m batch.run
```

Đầu ra: `data/gold/batch/canonical.duckdb`, gồm `canonical_events`, liên kết bài–vụ,
review và manifest lần chạy. Không sửa database provisional hoặc dữ liệu Silver.
Batch đọc toàn bộ lịch sử nhưng giữ retrieval ±48 giờ của giai đoạn 3.
Hướng dẫn interface, chạy lại và giới hạn: [Batch và matching](details/batch_matching.md).

### 9. Dashboard local

```powershell
.venv/Scripts/python.exe -m streamlit run src/dashboard/app.py
```

Mở `http://127.0.0.1:8501` để xem bộ dữ liệu hiện hành, bài báo, sự kiện canonical/
provisional và các bài chờ review. Dashboard chỉ đọc; xem
[hướng dẫn dashboard](details/dashboard.md).
