# Flow

## Luồng chính

RSS → file Bronze theo lần crawl → preprocess/dedup → Silver tích lũy → lọc tai nạn vào `data/filtered/<source>/`.

Điểm vào `src/main.py` nhận `--step` kiểu int: `0` (mặc định) chạy toàn bộ, `1` chạy crawlers, `2` chạy preprocessors, `3` chạy filters, `4` chạy extractors. Các thư mục dữ liệu được tạo trước khi chạy.

Chi tiết: [luồng lọc](details/accident_filter/pipeline.md).

## Tiêu chí và đánh giá bộ lọc tai nạn

Xem [tiêu chí](details/accident_filter/criteria.md) và [cách sinh kết quả đánh giá](details/accident_filter/rules_v1.md). Bộ nhãn trợ lý tự gán và báo cáo điểm số cũ đã được loại bỏ. Đánh giá cần dữ liệu tham chiếu được kiểm duyệt, truyền qua `--samples`; kết quả sinh ra nằm trong `data/evaluation/accident_filter/` và không commit vào Git.

## Folder architecture

```text
News-Big-Data-Platform/
|-- docs/               # Documentations 
|-- data/               # Contains output data of the program
    |-- bronze/             # Raw data crawled from sources 
    |-- silver/             # Cleaning data
    |-- gold/               # Final data ready for business services
|-- src/                # Source code of the program
    |-- config/             # Contains all the configs, schemas, global constants, ... of the program
    |-- crawlers/           # Crawlers
    |-- preprocessors/      # Cleaning and dedup
    |-- filters/            # Accident filtering
    |-- extractors/         # Accident information extraction
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
+ Output: `classified.parquet`, `accident.parquet`, `not_accident.parquet`, `uncertain.parquet` trong `data/filtered/<source>/`.

### 5. Extractors

+ Input: `data/filtered/<source>/accident.parquet`, dùng toàn bộ `title` và `description`.
+ Hàm: `run_extractors()` gọi các bước trích xuất bằng luật, regex và từ điển.
+ Output: `data/gold/accidents/<source>.parquet`, thêm địa điểm, phương tiện, thương vong, loại sự cố và bằng chứng.

Chi tiết: [trích xuất thông tin tai nạn](details/accident_extraction.md).
