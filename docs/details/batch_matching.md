# Batch 4.3 và interface matching 4.4

## Chạy batch

Từ gốc repository, dùng môi trường đã cài `pip install -e .`:

```powershell
.venv/Scripts/python.exe -m batch.run
```

Lệnh đọc **toàn bộ snapshot lịch sử** trong
`data/silver/accidents/<source>.parquet` của đủ 7 nguồn, không chỉ các bài mới.
Đây là Silver đã lọc tai nạn và trích xuất thông tin; batch không crawl,
không gọi mạng, không làm lại extraction và không sửa Silver.

Database mặc định: `data/gold/batch/canonical.duckdb`. Chạy thử vào nơi riêng:

```powershell
.venv/Scripts/python.exe -m batch.run --database data_artifacts/diagnostics/batch_demo/canonical.duckdb
```

Để chọn rõ thư mục và tập nguồn con:

```powershell
.venv/Scripts/python.exe -m batch.run --input-dir data/silver/accidents --sources vietnamplus tuoitre --database data_artifacts/diagnostics/batch_subset/canonical.duckdb
```

Thiếu một nguồn đã chọn, schema lỗi, cùng article key có payload xung đột hoặc
snapshot hoàn toàn rỗng sẽ báo lỗi và giữ nguyên database cũ. File nguồn rỗng
có schema hợp lệ được chấp nhận nếu tổng snapshot vẫn có bài. Bài thiếu tỉnh,
ngày hoặc key được giữ ở review, không ép thành sự kiện. Bản giống nhau theo
article key chỉ tính một lần; bản thiếu key giống hệt nhau giữ một payload review.

## Cách dựng lại và xuất bản

1. Khóa writer theo đường dẫn database; xác thực và hash đầu vào trước/sau đọc.
2. Sắp bài ổn định theo thời gian và key; dựng TF-IDF trên toàn bộ tập đầu vào.
3. Tạo database staging trống, tính lại mọi liên kết bằng logic giai đoạn 3.
4. Kiểm tra số bài đã gán + số review bằng tổng đầu vào sau dedup, commit,
   checkpoint và đóng database staging.
5. Thay file canonical bằng thao tác replace trên cùng filesystem. Lỗi xử lý
   hoặc lỗi replace giữ nguyên file canonical cũ; không xóa file cũ trước.

Trên Windows, nếu một ứng dụng giữ file canonical khiến replace thất bại, đóng
kết nối đọc rồi chạy lại. Một writer khác cùng đường dẫn bị từ chối. Database
đích có bảng ngoài namespace canonical bị từ chối để tránh ghi đè nhầm dữ liệu.
Không dùng các đường dẫn alias/symlink khác nhau cho cùng database khi chạy đồng thời.

Batch không kế thừa liên kết từ lần chạy trước. Khi Silver/cấu hình đổi, việc
gom cụm có thể đổi; cùng snapshot và cấu hình cho cùng phân nhóm và event ID.
Metadata thời gian/run ID có thể khác. Nếu bài neo hoặc thành phần cụm đổi,
event ID có thể đổi. Không có cam kết tự sửa mọi lỗi gom cụm khi thuật toán và
đầu vào vẫn giống nhau.

## Dữ liệu đầu ra

- `canonical_events`: sự kiện chính thức và tổng hợp thương vong.
- `canonical_articles`: bài có key, gồm payload extraction.
- `canonical_event_articles`: một liên kết trên mỗi bài đã gán sự kiện.
- `canonical_match_reviews`: bài chưa đủ dữ liệu hoặc matching chưa chắc chắn;
  kể cả payload thiếu key.
- `canonical_event_runs`: manifest nguồn, hash, thống kê, cấu hình và model fingerprint
  của snapshot hiện hành. Mỗi lần rebuild thay snapshot nên không giữ lịch sử
  các lần batch trước trong file này; lưu báo cáo chạy riêng nếu cần audit lâu dài.
- Các bảng hỗ trợ và view đều có tiền tố `canonical_`.

Các key thống kê `articles`, `accident_events`, `event_articles`, `match_reviews`
trong JSON là tên chỉ số kế thừa giai đoạn 3; bảng thực có namespace canonical.
Batch hiện không xuất Parquet tự động. DuckDB là sản phẩm chính thức.

```python
import duckdb
with duckdb.connect('data/gold/batch/canonical.duckdb', read_only=True) as c:
    print(c.sql('SELECT event_id, province, article_count FROM canonical_events'))
    print(c.sql('SELECT article_key, event_id FROM canonical_event_articles'))
    print(c.sql('SELECT article_key, reasons FROM canonical_match_reviews'))
```

## Interface dùng chung

`events.service.MatchingService(config, past_only=False)` cung cấp:

```python
decision = service.decide(article, repository, articles, model)
```

- `article`: kết quả `events.adapter.prepare_article()`.
- `repository`: hỗ trợ `find_candidates(article, config, articles)`; chỉ đọc.
- `articles`: snapshot bài chuẩn hóa theo key, phục vụ lấy các thành viên cụm.
- `model`: `TextModel` dùng thống nhất trong lần xử lý; batch dựng một lần trên
  toàn bộ đầu vào, streaming dựng theo các bài hiện có.
- Kết quả: `decision` thuộc `new_event`, `matched`, `needs_review`, `reasons`,
  `scores`, fingerprint cấu hình/model và `match_version`; `event_id`/`score`
  xuất hiện khi matched. Với new event, repository tạo ID khi lưu assignment.

Service không ghi database hoặc ack queue. Caller sở hữu transaction, lưu review,
assignment và aggregation. `events.run`, streaming và batch đều gọi service;
`decide_match()` vẫn dùng được trực tiếp cho các caller/test cũ.

Batch giữ retrieval cùng tỉnh và khoảng cách **±48 giờ so với thời gian đăng**
của giai đoạn 3, dù đọc toàn bộ lịch sử. Streaming mặc định chọn khoảng
**[thời gian đăng bài − 24 giờ, thời gian đăng bài]**, gồm hai biên và loại candidate
có timestamp tương lai. Dùng timestamp bài để replay không phụ thuộc đồng hồ máy.
Đây chưa phải thời gian xảy ra tai nạn được trích xuất. Không thay ngưỡng chấm
điểm hoặc dùng embedding mới trong lần triển khai này.

## Kiểm thử

```powershell
$env:STREAM_TEST_REDIS_URL='redis://localhost:6379/0'
.venv/Scripts/python.exe -m unittest discover -s tests
```

Biến Redis chỉ cần cho integration test streaming, batch không cần server Redis.
Nếu không đặt biến, 5 test streaming integration bị bỏ qua. Memurai chạy trên
Windows có thể dùng để kiểm tra giao thức Redis; kết quả đó không chứng minh
Redis trong Docker đã chạy.

Chạy batch không sửa `provisional_events` hoặc database giai đoạn 3. Crawler →
producer, extraction địa danh, lịch chạy, Docker/WSL và đồng bộ ngược canonical
sang provisional nằm ngoài phạm vi này. Chất lượng matching còn phụ thuộc vào
Silver và thuật toán giai đoạn 3.
