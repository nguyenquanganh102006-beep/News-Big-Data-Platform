# Bộ luật lọc tai nạn v1 và cách sinh kết quả

## Đánh giá trên dữ liệu được kiểm duyệt

Sau khi cài đặt theo [pipeline.md](pipeline.md), chuẩn bị `data/reviewed_accidents.jsonl` do người kiểm duyệt cung cấp. Mỗi dòng là một object JSON có `sample_id`, `title`, `description_text` (có thể null), `label`. Nhãn hợp lệ: `accident`, `not_accident`, `uncertain`. File này không được script tự tạo nhãn chuẩn; không dùng kết quả của bộ lọc làm nhãn tham chiếu.

Từ thư mục gốc:

```powershell
.\.venv\Scripts\python.exe -m filters.evaluate --samples data/reviewed_accidents.jsonl --output data/evaluation/accident_filter
```

`src/filters/evaluate.py` đọc từng dòng, gọi `classify_accident(title, description_text)` trong `src/filters/accident.py`, rồi ghi:

- `predictions.jsonl`: giữ dữ liệu đầu vào và thêm object `prediction` gồm nhãn, lý do, bằng chứng và phiên bản luật.
- `metrics.json`: số mẫu, ma trận nhầm lẫn, accuracy, precision, recall, F1 và ID các mẫu không khớp nhãn tham chiếu.

Thư mục đầu ra tự tạo; hai file được ghi đè khi chạy lại. Nếu không truyền `--output`, mặc định dùng `data/evaluation/accident_filter`. Cần truyền `--samples` rõ ràng. `data/` đã được bỏ qua trong Git; các thư mục `docs/details/accident_filter/evaluation_*/` và file JSON/JSONL trực tiếp trong thư mục này cũng được bỏ qua để tránh commit lại đầu ra cũ.

## Dữ liệu cũ đã loại bỏ

Đã xóa bộ nhãn trợ lý tự gán (`reviewed_samples.jsonl`, `reviewed_all_414.jsonl`), các bản trích/tổng hợp (`selected_accidents_30.jsonl`, `needs_review_9.jsonl`, `manual_review_summary.json`, `manual_review_414.md`), bản manifest khảo sát không có lệnh tái tạo được xác minh và báo cáo đánh giá phụ thuộc vào chúng. Không có lệnh sinh lại nhãn chuẩn tự động. Các điểm số cũ không còn được dùng làm bằng chứng chất lượng.

## Thứ tự if/else

1. Chuẩn hóa HTML entity, Unicode, chữ thường và khoảng trắng. Với description lấy câu đầu làm lead để giảm nhiễu từ tiêu đề bài liên quan; đây chỉ là heuristic, không phải parser hoàn chỉnh cho từng nguồn.
2. Thiếu tiêu đề → uncertain.
3. Tiêu đề tư vấn/giả định → not_accident.
4. Mô tả suýt gây va chạm, một số tai nạn sinh hoạt/lao động → not_accident.
5. Đường thủy, xe công trình hoặc cháy xe chưa chốt phạm vi → uncertain.
6. Tiêu đề thống kê tổng hợp → not_accident.
7. Có phương tiện và diễn biến va chạm thật trong tiêu đề → accident.
8. Tiêu đề nói vụ tai nạn/cập nhật vụ cụ thể, kèm ngữ cảnh giao thông → accident.
9. Chủ đề chính là biển báo, ùn tắc, quy định, thi công, xử phạt… → not_accident.
10. Chưa quyết định: phương tiện + diễn biến va chạm trong lead → accident; chỉ có từ tai nạn chưa đủ bằng chứng → uncertain; còn lại not_accident.

Luật không đọc nhãn, lý do thủ công, URL, tên nguồn hay sample_id để quyết định. Không yêu cầu có tử vong. Mỗi quyết định có mã lý do để kiểm tra.

## Giới hạn và kiểm tra

Luật từ vựng có thể nhầm phủ định, giả định, bài trộn nhiều tin và quan hệ giữa phương tiện với tai nạn. Câu đầu mô tả có thể thiếu bằng chứng; nhóm uncertain cần được xem xét. Chưa có kết quả đánh giá độc lập được giữ lại trong repo. Bộ kiểm tra chức năng không thay thế đánh giá chất lượng trên dữ liệu thực.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```
