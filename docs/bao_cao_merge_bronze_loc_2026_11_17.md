# Báo cáo hợp nhất nhánh và kiểm tra bộ lọc — 17/11/2026

## Phạm vi

Hợp nhất `fix/23-24` (commit `22f80be`, bản sửa mới nhất của bước lọc và trích xuất Phần 2) vào `task/32-33`. Giữ bán kính tìm sự kiện ±48 giờ của nhánh hiện tại và nhận phần bổ sung về batch, streaming, dashboard của nhánh mới. Các xung đột ở tài liệu, cấu hình phụ thuộc, hồ sơ sự kiện, embedding và kiểm thử đã được xử lý trước khi chạy lại.

Dữ liệu cũ do nhóm lưu nằm ở `data/bronze/bronze/<source>/`, trong khi bộ chọn Bronze trước đó chỉ đọc `data/bronze/<source>/`. Đã bổ sung đường dẫn lồng nhau vào bộ chọn và kiểm thử riêng. File Bronze gốc không bị sửa. Thư mục `data/` được Git bỏ qua nên dữ liệu đầu vào và Parquet đầu ra chỉ nằm ở máy chạy.

## Cách chạy và kết quả

Chạy `python -m preprocessors.run` rồi `python -m filters.run` bằng `.venv/bin/python` với `PYTHONPATH=src`. Preprocessor đọc file RSS và file `history_*.parquet` của cả 7 nguồn, giữ thân bài lịch sử trong Silver. Bước khử trùng nội dung nhận 20.965 bài, đánh dấu 12 bản trùng và đưa 20.953 bài vào bộ lọc.

| Nguồn | Bài sau khử trùng | Tai nạn | Không phải tai nạn | Cần xem xét |
|---|---:|---:|---:|---:|
| Báo Xây dựng | 3.730 | 171 | 3.554 | 5 |
| Dân Trí | 476 | 17 | 458 | 1 |
| Thanh Niên | 4.081 | 21 | 4.052 | 8 |
| Tiền Phong | 4.444 | 74 | 4.363 | 7 |
| Tuổi Trẻ | 3.768 | 29 | 3.730 | 9 |
| VietnamPlus | 4.286 | 20 | 4.262 | 4 |
| VnExpress | 168 | 6 | 161 | 1 |
| **Tổng** | **20.953** | **338** | **20.580** | **35** |

Đây là số **bài báo**, không phải số vụ tai nạn. Các bản tin có nhiều vụ vẫn có thể nhận nhãn `accident` và cần tách vụ ở bước sau. Số liệu này khác báo cáo rà soát 20.745 bài trên nhánh nguồn vì lần chạy này còn đọc các snapshot RSS có sẵn trong thư mục Bronze hiện tại; không so trực tiếp hai tỷ lệ như cùng một tập đầu vào.

## Rà soát hiệu quả và sửa lỗi

Đã đọc phân bố nhãn theo nguồn và lý do, xem 100 tiêu đề đầu trong nhóm tai nạn, toàn bộ 35 tiêu đề `uncertain`, và tìm các tiêu đề bị loại dù cùng chứa từ chỉ phương tiện và va chạm. Các trường hợp bị loại nổi bật là tin pháp lý sau vụ, tư vấn luật, tin sản phẩm và tai nạn ngoài đường bộ; đó là cách xử lý phù hợp với phạm vi đã ghi trong tài liệu bộ lọc. Các trường hợp `uncertain` vẫn cần người kiểm tra, nhất là tin thiếu ngữ cảnh đường bộ.

Phát hiện một lỗi chắc chắn: bài “Liên tục xảy ra tai nạn trên đường ven biển qua Gia Lai dù chưa đưa vào khai thác” là bài về tình trạng an toàn trên tuyến đường, không tường thuật một vụ cụ thể, nhưng bộ lọc nhận `accident` do tìm thấy tín hiệu va chạm trong thân bài. Đã bổ sung nhận diện tiêu đề tổng hợp “liên tục xảy ra tai nạn” trước khi xét nội dung, thêm kiểm thử hồi quy và đổi phiên bản sang `rules-v5.1-aggregate-headline`. Trên cùng 20.953 bài, số bài `accident` giảm từ 339 còn 338; bài này chuyển sang `not_accident`.

Không có tập nhãn độc lập cho toàn bộ dữ liệu hiện tại, nên các số trên không chứng minh precision hoặc recall. Rà soát tiêu đề và tìm kiếm theo từ khóa có thể bỏ sót các cách diễn đạt khác. Cần người kiểm duyệt một mẫu ngẫu nhiên ở cả ba nhóm trước khi công bố điểm chất lượng.

## Kiểm thử và tái chạy

`python -m unittest discover -s tests -q`: **184 kiểm thử đạt, 5 bỏ qua**. Các kiểm thử gồm phát hiện Bronze lồng thư mục, lọc tai nạn, truyền thân bài, khử trùng và logic ghép sự kiện. Năm kiểm thử bị bỏ qua là kiểm thử tích hợp tùy chọn; lần này chưa chạy Redis replay, Gold hoặc dashboard trên toàn bộ dữ liệu.

Để tái tạo riêng kết quả lọc từ thư mục gốc (Linux):

```bash
PYTHONPATH=src .venv/bin/python -m preprocessors.run
PYTHONPATH=src .venv/bin/python -m filters.run
.venv/bin/python -m unittest discover -s tests -q
```

Đầu ra lọc nằm tại `data/silver/filtered/<source>/classified.parquet` và các file theo nhãn. Thống kê khử trùng nằm ở `data/silver/deduplicated/manifest.json`.
