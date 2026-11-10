# 2.2. Phát hiện bài báo trùng lặp (Duplicate Article Detection)

## Mục đích

Phát hiện các bài sao chép nguyên văn hoặc bản tin cập nhật gần như không đổi giữa các nguồn báo. Mỗi nhóm bài tương đồng giữ một bài gốc để đưa vào filter, extraction và ghép sự kiện; các bản còn lại được đánh dấu và lưu để kiểm tra, không xóa khỏi Silver.

**Mục tiêu:** đánh dấu bản trùng dựa trên khoảng cách văn bản, giữ một bản gốc và loại bản sao khỏi luồng xử lý downstream. Phần trước: 2.1; bước phụ thuộc phía sau: 2.3.

## Vị trí trong luồng

Phần này chạy trên lịch sử Silver của cả 7 nguồn, trước bộ lọc tai nạn:

```text
Bronze → preprocess / khử trùng theo URL → Silver lịch sử
  → TF-IDF + cosine (2.2) → filter (2.3) → extraction → sự kiện
```

Khử trùng theo URL trong `preprocessors.utils` vẫn được giữ. Đó là lớp nhận diện cùng một bài qua URL chuẩn hóa trong cùng nguồn. Phần 2.2 bổ sung lớp so nội dung để nhận ra bài đăng ở URL hoặc nguồn khác nhau.

## Thuật toán và quy tắc

1. Ghép `title` và `description` làm văn bản so sánh. HTML entity/tag được chuyển thành chữ; văn bản được chuẩn hóa Unicode NFC, chữ thường và khoảng trắng.
2. `TfidfVectorizer` tạo vector TF-IDF theo ký tự, `analyzer="char_wb"`, n-gram 3–5 và `sublinear_tf=True`. So độ gần bằng cosine similarity.
3. So với các bài gốc đã giữ trong cửa sổ thời gian đăng bài 24 giờ, không phụ thuộc nguồn báo. Thời gian có timezone được chuẩn hóa về UTC.
4. Nếu cosine **>= 0.85**, bài mới được đánh dấu là bản trùng của bài gốc có điểm cao nhất. Bài gốc là bài xuất bản sớm nhất trong nhóm; nếu cùng thời điểm thì thứ tự source và `article_key` tạo kết quả ổn định.
5. Bài thiếu `pub_date`, tiêu đề/mô tả hoặc `article_key` không bị tự động loại vì không đủ dữ liệu để so sánh. Ngưỡng và cửa sổ có thể cấu hình trong `src/config/filters.py`.

Việc so sánh chỉ cho phép bài gốc loại bài sau; các bản trùng không trở thành cầu nối để loại thêm bài khác. Cách này giữ rõ quan hệ `duplicate_of_article_key` tới một bản gốc đã được chọn.

## Lưu kết quả và tác động

`run_content_dedup()` đọc Silver tích lũy và ghi:

- `data/silver/deduplicated/<source>.parquet`: toàn bộ dòng của nguồn, có cột `is_duplicate`, `duplicate_of_article_key`, `duplicate_similarity`, `duplicate_algorithm`.
- `data/silver/deduplicated/duplicates.parquet`: các dòng được đánh dấu trùng để rà soát.
- `data/silver/deduplicated/manifest.json`: tổng đầu vào, số bản giữ/trùng, ngưỡng, cửa sổ và số liệu theo nguồn.

`python -m main --step 3` chạy phát hiện trùng trước khi phân loại. `classified.parquet`, `accident.parquet`, `not_accident.parquet` và `uncertain.parquet` chỉ nhận các bài không bị đánh dấu trùng. Bản Bronze và Silver lịch sử gốc không bị sửa. Dashboard catalog giữ cờ và quan hệ bản gốc; bài trùng được ẩn khỏi thống kê/tra cứu mặc định, có thể bật lên để kiểm tra. Batch canonical cũng chỉ nhận bài gốc.

Lệnh chạy riêng để tạo lại file chú giải trùng:

```powershell
.\.venv\Scripts\python.exe -m preprocessors.content_dedup
```

Lệnh này chỉ chạy lớp phát hiện và ghi thư mục `silver/deduplicated`; để tạo lại các partition downstream, chạy `python -m main --step 3`.

## Giới hạn phạm vi

Nguồn hiện cung cấp tiêu đề và phần mô tả RSS trong Silver; đây chưa phải toàn văn bài báo. Vì thế kết quả phát hiện trùng dựa trên nội dung RSS đang có. Bước 2.2 này thuộc luồng crawl/batch và dashboard canonical. Redis streaming hiện có idempotency theo `article_key` để chống nhận lại đúng một URL; nó chưa dùng cosine để phát hiện bản tin tương tự giữa các message khác URL.

Phần EDA cũ [preprocessor_eda.md](preprocessor_eda.md) mục VietnamPlus `2.2. description` ghi lại việc bóc HTML khỏi RSS và được giữ nguyên. Đó là ghi chú làm sạch HTML; không thay thế thuật toán trùng nội dung ở tài liệu này.
