# Báo cáo hợp nhất nhánh và kiểm tra Phần 3 — 17/11/2026

## Phạm vi

Hợp nhất `fix/23-24` (commit `22f80be`, bản sửa mới nhất của bước lọc và trích xuất Phần 2) vào `task/32-33`. Giữ bán kính tìm sự kiện ±48 giờ của nhánh hiện tại và nhận phần bổ sung về batch, streaming, dashboard của nhánh mới. Các xung đột ở tài liệu, cấu hình phụ thuộc, hồ sơ sự kiện, embedding và kiểm thử đã được xử lý trước khi chạy lại.

Dữ liệu cũ do nhóm lưu nằm ở `data/bronze/bronze/<source>/`, trong khi bộ chọn Bronze trước đó chỉ đọc `data/bronze/<source>/`. Đã bổ sung đường dẫn lồng nhau vào bộ chọn và kiểm thử riêng. File Bronze gốc không bị sửa. Thư mục `data/` được Git bỏ qua nên dữ liệu đầu vào và Parquet đầu ra chỉ nằm ở máy chạy.

## Cách chạy và kết quả

Chạy `python -m preprocessors.run` rồi `python -m filters.run` bằng `.venv/bin/python` với `PYTHONPATH=src`. Preprocessor đọc file RSS và file `history_*.parquet` của cả 7 nguồn, giữ thân bài lịch sử trong Silver. Bước khử trùng nội dung nhận 20.965 bài, đánh dấu 12 bản trùng và đưa 20.953 bài vào bộ lọc.

| Nguồn | Bài sau khử trùng | Tai nạn | Không phải tai nạn | Cần xem xét |
|---|---:|---:|---:|---:|
| Báo Xây dựng | 3.730 | 170 | 3.555 | 5 |
| Dân Trí | 476 | 17 | 458 | 1 |
| Thanh Niên | 4.081 | 21 | 4.052 | 8 |
| Tiền Phong | 4.444 | 74 | 4.363 | 7 |
| Tuổi Trẻ | 3.768 | 29 | 3.730 | 9 |
| VietnamPlus | 4.286 | 20 | 4.262 | 4 |
| VnExpress | 168 | 6 | 161 | 1 |
| **Tổng** | **20.953** | **337** | **20.581** | **35** |

Đây là số **bài báo**, không phải số vụ tai nạn. Các bản tin có nhiều vụ vẫn có thể nhận nhãn `accident` và cần tách vụ ở bước sau. Số liệu này khác báo cáo rà soát 20.745 bài trên nhánh nguồn vì lần chạy này còn đọc các snapshot RSS có sẵn trong thư mục Bronze hiện tại; không so trực tiếp hai tỷ lệ như cùng một tập đầu vào.

## Rà soát hiệu quả và sửa lỗi

Đã đọc phân bố nhãn theo nguồn và lý do, xem 100 tiêu đề đầu trong nhóm tai nạn, toàn bộ 35 tiêu đề `uncertain`, và tìm các tiêu đề bị loại dù cùng chứa từ chỉ phương tiện và va chạm. Các trường hợp bị loại nổi bật là tin pháp lý sau vụ, tư vấn luật, tin sản phẩm và tai nạn ngoài đường bộ; đó là cách xử lý phù hợp với phạm vi đã ghi trong tài liệu bộ lọc. Các trường hợp `uncertain` vẫn cần người kiểm tra, nhất là tin thiếu ngữ cảnh đường bộ.

Phát hiện một lỗi chắc chắn: bài “Liên tục xảy ra tai nạn trên đường ven biển qua Gia Lai dù chưa đưa vào khai thác” là bài về tình trạng an toàn trên tuyến đường, không tường thuật một vụ cụ thể, nhưng bộ lọc nhận `accident` do tìm thấy tín hiệu va chạm trong thân bài. Đã bổ sung nhận diện tiêu đề tổng hợp “liên tục xảy ra tai nạn” trước khi xét nội dung; số bài `accident` giảm từ 339 còn 338.

Khi chạy 338 bài qua Phần 3, phát hiện thêm bài “Khánh Hòa: Ưu tiên mổ cấp cứu, nhiều nạn nhân vụ sạt lở đèo Khánh Lê qua cơn nguy kịch” chỉ cập nhật việc điều trị sau tai nạn. Đã bổ sung quy tắc loại tin điều trị này, thêm kiểm thử hồi quy và chạy lại bộ lọc. Đầu vào cuối cùng còn **337 bài tai nạn**; phiên bản quy tắc là `rules-v5.2-exclude-medical-followup`.

Không có tập nhãn độc lập cho toàn bộ dữ liệu hiện tại, nên các số trên không chứng minh precision hoặc recall. Rà soát tiêu đề và tìm kiếm theo từ khóa có thể bỏ sót các cách diễn đạt khác. Cần người kiểm duyệt một mẫu ngẫu nhiên ở cả ba nhóm trước khi công bố điểm chất lượng.

## Chạy toàn bộ Phần 3 trên bài tai nạn thật

Đã đưa **cả 338 bài ban đầu** qua trích xuất và ghép sự kiện với embedding mặc định. Lần đó tạo 173 sự kiện mới, ghép 13 bài với sự kiện có sẵn và để 152 bài chờ xem xét. Sau khi loại một bài cập nhật điều trị, đã chạy lại **toàn bộ 337 bài** qua trích xuất và ghép sự kiện trên database kiểm thử mới. Cả 6 bài VnExpress lấy được dấu địa phương từ trang nguồn khi chạy với kết nối mạng.

| Kết quả Phần 3 trên đầu vào cuối | Số lượng |
|---|---:|
| Bài đầu vào | 337 |
| Sự kiện mới | 173 |
| Bài được ghép vào sự kiện | 13 |
| Bài liên kết với sự kiện | 186 |
| Bài chờ xem xét, chưa liên kết | 151 |

Trong 151 bài chờ, 119 bài thiếu tỉnh/thành đã trích xuất, 34 bài có dấu hiệu chứa nhiều vụ, 37 bài thiếu chi tiết diễn biến và 7 bài chưa đủ căn cứ để ghép. Các lý do có thể cùng xuất hiện trên một bài nên không cộng các số này. Tỷ lệ chờ cao cho thấy giới hạn của dữ liệu và bước trích xuất hiện tại; hệ thống giữ các bài đó riêng thay vì tự gộp khi thiếu bằng chứng. Kiểm tra các sự kiện có nhiều bài cho thấy 11 sự kiện gồm hai bài và một sự kiện gồm ba bài; các cặp/nhóm đã xem nói về cùng vụ. Chưa có nhãn cùng vụ/khác vụ độc lập để đo độ đúng trên toàn bộ tập.

Chạy lại trên cùng database giữ nguyên 173 sự kiện, 186 liên kết và 151 bài chờ; 186 bài đã liên kết được nhận là đã xử lý, không tạo thêm sự kiện hoặc liên kết trùng.

Database kiểm thử nằm tại `data/evaluation/phase3_337_20261117/events.duckdb`; Parquet xuất tại thư mục `exports/` bên cạnh. Lần kiểm thử 338 bài trước khi sửa được giữ riêng tại `data/evaluation/phase3_338_20261117/`. Cả hai thư mục nằm trong `data/` và không được push lên GitHub.

## Kiểm thử và tái chạy

`python -m unittest discover -s tests -q`: **184 kiểm thử đạt, 5 bỏ qua**. Các kiểm thử gồm phát hiện Bronze lồng thư mục, lọc tai nạn, truyền thân bài, khử trùng và logic ghép sự kiện. Năm kiểm thử bị bỏ qua là kiểm thử tích hợp tùy chọn. Đã chạy Gold Phần 3 trên toàn bộ bài tai nạn; chưa chạy Redis replay, batch hoặc dashboard trên toàn bộ dữ liệu.

Để tái tạo từ Bronze đến Phần 3 trên database kiểm thử riêng tại thư mục gốc (Linux):

```bash
PYTHONPATH=src .venv/bin/python -m preprocessors.run
PYTHONPATH=src .venv/bin/python -m filters.run
PYTHONPATH=src .venv/bin/python -m extractors.run
PYTHONPATH=src .venv/bin/python -m events.run --database data/evaluation/phase3_337_20261117/events.duckdb --export-dir data/evaluation/phase3_337_20261117/exports
.venv/bin/python -m unittest discover -s tests -q
```

Đầu ra lọc nằm tại `data/silver/filtered/<source>/classified.parquet` và các file theo nhãn. Thống kê khử trùng nằm ở `data/silver/deduplicated/manifest.json`.
