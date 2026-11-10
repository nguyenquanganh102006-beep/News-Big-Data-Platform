# Flow

## Luồng chính

RSS → Bronze → làm sạch/dedup → lọc và trích xuất thông tin → Silver theo bài → phần 3 gom sự kiện → Gold (DuckDB).

Điểm vào `src/main.py` nhận `--step` kiểu int: `0` (mặc định) chạy toàn bộ, `1` chạy crawlers, `2` chạy preprocessors, `3` chạy filters, `4` chạy extractors, `5` chạy phần sự kiện và lưu database. Các thư mục dữ liệu được tạo trước khi chạy.

Sau `python -m pip install -e .`, chạy từ thư mục gốc bằng `python -m main`.
Không cần đặt thêm `PYTHONPATH`. Hướng dẫn dễ đọc và kết quả chạy dữ liệu thật:
[lưu sự kiện vào database](details/event_database_guide.md).

Chi tiết: [luồng lọc](details/accident_filter/pipeline.md).

## Tiêu chí và đánh giá bộ lọc tai nạn

Xem [tiêu chí](details/accident_filter/criteria.md) và [cách sinh kết quả đánh giá](details/accident_filter/rules_v1.md). Bộ nhãn trợ lý tự gán và báo cáo điểm số cũ đã được loại bỏ. Đánh giá cần dữ liệu tham chiếu được kiểm duyệt, truyền qua `--samples`; kết quả sinh ra nằm trong `data/evaluation/accident_filter/` và không commit vào Git.

## Folder architecture

```text
News-Big-Data-Platform/
|-- docs/               # Documentations 
|-- data/               # Contains output data of the program
    |-- bronze/             # Raw data crawled from sources 
    |-- silver/             # Bài đã làm sạch
        |-- filtered/       # Kết quả lọc theo nguồn
        |-- accidents/      # Bài đã trích xuất, đầu vào phần 3
    |-- gold/               # Database sự kiện và bản xuất từ database
|-- src/                # Source code of the program
    |-- config/             # Contains all the configs, schemas, global constants, ... of the program
    |-- crawlers/           # Crawlers
    |-- preprocessors/      # Cleaning and dedup
    |-- filters/            # Accident filtering
    |-- extractors/         # Accident information extraction
    |-- events/             # Candidate retrieval, matching and DuckDB storage
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

+ Input: file `.parquet` mới nhất theo tên timestamp trong `data/bronze/<source>/` (output của `crawlers`). Chạy crawler trước nếu chưa có file. Silver được tích lũy sau khi loại trùng trong batch và so với lịch sử.

+ Run pipeline
```bash
cd src
python -m preprocessors.run
```

+ Output: `.parquet` files saved in `data/silver/`

Chi tiết làm sạch: [EDA preprocessors](details/preprocessor_eda.md). Cơ chế chọn file, chuẩn hóa URL và lưu lịch sử: [dedup preprocessors](details/preprocessor_dedup.md).

### 4. Filters

+ Input: Silver tích lũy của VnExpress, VietnamPlus, Tuổi Trẻ.
+ Hàm: `run_filters()` phân loại bằng `classify_accident()`.
+ Output: `classified.parquet`, `accident.parquet`, `not_accident.parquet`, `uncertain.parquet` trong `data/silver/filtered/<source>/`.

### 5. Extractors

+ Input: `data/silver/filtered/<source>/accident.parquet`, dùng toàn bộ `title` và `description`.
+ Hàm: `run_extractors()` gọi các bước trích xuất bằng luật, regex và từ điển.
  Riêng VnExpress, mở bài đã được filter chọn để đọc nhãn tỉnh/thành ở đầu bài.
+ Output: `data/silver/accidents/<source>.parquet`, thêm địa điểm, phương tiện, thương vong, loại sự cố và bằng chứng.
  Việc lấy nhãn địa điểm VnExpress thuộc phần 2; phần 3 nhận trường `province`
  từ Silver, không tự tải trang hay trích xuất lại tỉnh.

Chi tiết: [trích xuất thông tin tai nạn](details/accident_extraction.md).

### 6. Sự kiện tai nạn (3.1, 3.2, 3.3)

Input: `data/silver/accidents/<source>.parquet` của ba nguồn hiện có. Đọc chung
các nguồn, sắp bài theo ngày đăng rồi khóa bài. Kho sự kiện được đọc từ DuckDB;
sự kiện vừa tạo được dùng ngay để so sánh bài tiếp theo.

```bash
python -m main --step=5
python -m events.inspect
```

- 3.1 tìm cùng tỉnh trong khoảng ±48 giờ theo ngày đăng.
- 3.2 lập hồ sơ vụ việc từ văn bản, so TF-IDF và embedding mặc định, đối chiếu
  địa điểm/ngày xảy ra/đối tượng/phương tiện, kiểm tra mâu thuẫn với cả cụm rồi
  gộp/tạo mới hoặc giữ bài chờ nếu chưa đủ bằng chứng. Quy trình và tùy chọn tắt
  embedding: [matching v2](details/event_matching_v2.md).
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
