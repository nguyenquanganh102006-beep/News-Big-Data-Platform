# Flow

## Luồng chính

Đã tích hợp bộ lọc tai nạn `rules-v1` sau Silver dedup. Từ thư mục gốc:

```powershell
.\.venv\Scripts\python.exe -m pipeline
```

Luồng: crawl RSS → Bronze theo từng lần crawl → preprocess/dedup → Silver tích lũy → lọc vào `data/filtered/<source>/`. Dùng `--skip-crawl` để dùng Bronze mới nhất; dùng `python -m filters.run` để chỉ lọc lại Silver. Hỗ trợ 3 nguồn đã có preprocessor. Chi tiết input/output, schema, cấu hình, xử lý lỗi và test: [hướng dẫn luồng lọc](details/accident_filter/pipeline.md).

## Khảo sát tiêu chí lọc tai nạn (task 23)

Đã chạy nguyên luật v1 trên 414 bài: [kết quả và lỗi cụ thể](details/accident_filter/evaluation_v1_414/report.md). Lệnh chạy lại được ghi trong báo cáo.

Đã đọc và gán nhãn đủ 414 bài: xem [bảng đọc thủ công đầy đủ](details/accident_filter/manual_review_414.md), dữ liệu nhãn `reviewed_all_414.jsonl` cùng thư mục. Kết quả 30 bài tai nạn, 375 bài không phù hợp và 9 bài chưa chốt phạm vi; bước gán nhãn không sửa Bronze/Silver.

Bộ lọc if/else v1 và cách chạy đánh giá: [rules_v1.md](details/accident_filter/rules_v1.md). Chạy từ thư mục gốc: `.\.venv\Scripts\python.exe -m filters.evaluate`. Lệnh chỉ đánh giá mẫu và ghi báo cáo, chưa lọc trực tiếp Silver hay tạo Gold.

Xem [tiêu chí và kết quả đọc mẫu](details/accident_filter/criteria.md). Bộ mẫu gán nhãn thủ công nằm trong `docs/details/accident_filter/reviewed_samples.jsonl`; danh sách 3 lần crawl trong `crawl_manifest.json` cùng thư mục. Đây là bước khảo sát, chưa chạy bộ lọc tự động hoặc tạo Gold.

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
```


## Partial flows

Chạy trên Windows PowerShell từ thư mục gốc sau khi setup theo `docs/setup.md`:

```powershell
New-Item -ItemType Directory -Force data/bronze, data/silver, data/gold | Out-Null
.\.venv\Scripts\python.exe -m crawlers.run
.\.venv\Scripts\python.exe -m preprocessors.run
```

Chạy crawler trước để tạo dữ liệu Bronze đầu vào cho preprocessors. Lệnh dùng trực tiếp Python trong `.venv`, không cần kích hoạt môi trường ảo.

### 1. Config

+ structure:

```text
News-Big-Data-Platform/
|-- src/
    |-- config/
        |-- crawlers.py     # Crawler configs
        |-- ...
```

>[!NOTE]
> Tất cả các config của cả cái dự án này đều phải để trong `src/config/`, ví dụ như biến lấy từ `.env`, global constants (biến dùng chung) giữa các luồng, ...  

>[!WARNING]
> Sau này có thêm luồng nào thì nhớ sửa cái folder structure ở trên  
> KHÔNG hardcode các biến somewhere bên ngoài cái `config/` này  



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

Mỗi lần chạy crawler tạo một snapshot riêng cho từng nguồn, timestamp theo giờ Việt Nam (UTC+7). Ví dụ: `data/bronze/vnexpress/20261024_153000.parquet`. Thư mục theo nguồn được tạo tự động. Nếu trùng timestamp, thêm hậu tố `_000001`, `_000002`, ... để không ghi đè file cũ. Các file Bronze cũ nằm trực tiếp trong `data/bronze/` được giữ nguyên.

> [!NOTE]
> Hỗ trợ Python >= 3.10. Khi dùng f-string có truy cập dictionary, dùng dấu nháy khác nhau cho chuỗi ngoài và key bên trong, ví dụ: `f"{source['bronze_save_path']}"`.



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

+ Input: snapshot `.parquet` mới nhất theo tên timestamp trong `data/bronze/<source>/` (output của `crawlers`). Chạy crawler trước nếu chưa có snapshot. Silver được tích lũy sau khi loại trùng trong batch và so với lịch sử.

+ Run pipeline
```bash
cd src
python -m preprocessors.run
```

+ Output: `.parquet` files saved in `data/silver/`

Silver bổ sung `source`, `normalized_url` và `article_key`. Khóa là SHA-256 của `source + "\n" + normalized_url`, ổn định qua các lần crawl. Chuẩn hóa bỏ khoảng trắng ở hai đầu URL, fragment `#...`, chuyển scheme/host sang chữ thường và bỏ các tham số tracking trong `src/config/dedup.py` (không phân biệt hoa thường). Các query khác, thứ tự và encoding được giữ nguyên để tránh mất ID bài. Không gộp HTTP/HTTPS hoặc các URL khác path.

URL thiếu hoặc không hợp lệ có `normalized_url` và `article_key` là null; bản ghi vẫn được giữ lại. Dedup không gộp các bản có khóa null.

Kiểm tra khóa nhận diện từ thư mục gốc:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

### Silver history dedup

Sau khi tạo khóa, loại trùng trong batch theo `article_key`, giữ bản xuất hiện cuối cùng và giữ thứ tự tương đối của các bản còn lại. Sau đó dùng Polars `anti join` với lịch sử `data/silver/<source>.parquet` để lấy bài mới, rồi lưu lịch sử cũ + bài mới. Nếu chưa có Silver thì toàn bộ batch được xem là mới. Silver cũ chưa có khóa được bổ sung khóa từ `link`. Bài đã có giữ nguyên dữ liệu cũ.

Ghi vào file tạm rồi thay thế file đích sau khi ghi thành công. Chỉ chạy một tiến trình ghi cho mỗi nguồn tại một thời điểm. Hàm preprocessor trả về **các bài mới**; `save_file=False` chỉ tính kết quả, không ghi file.

Thống kê luôn được in, kể cả khi `DEBUG=False`:

```text
[Silver] source=..., input=..., batch_duplicates=..., history_duplicates=..., new=..., silver_total=..., status=saved
```

`input` là số dòng trước dedup; `batch_duplicates` là số bản dư trong batch; `history_duplicates` là số bản sau batch dedup đã có trong lịch sử; `new` là số bài mới. Luôn có `input = batch_duplicates + history_duplicates + new`. `silver_total` là tổng sau gộp; `status=dry_run` là kết quả dự kiến, chưa ghi file.

Chạy lại cùng batch có khóa hợp lệ cho `new=0`. Các bản khóa null vẫn được giữ và có thể lặp qua các lần chạy. Lịch sử bắt đầu từ Silver hiện có; chưa tự động nạp lại các snapshot Bronze cũ.
