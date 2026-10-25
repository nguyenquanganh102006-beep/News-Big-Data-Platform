# Bộ luật lọc tai nạn v1 và kết quả thử

## Cách chạy

Từ thư mục gốc, sau khi cài dependencies:

```powershell
.\.venv\Scripts\python.exe -m filters.evaluate
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

`src/filters/accident.py` nhận title/description và trả về label, reason, evidence, version. Chưa nối vào pipeline Silver/Gold, không sửa dữ liệu bài báo. Lệnh đánh giá đọc bộ 70 mẫu thủ công và ghi `evaluation_v1/metrics.json` cùng `evaluation_v1/predictions.jsonl` có kết quả từng bài. Chạy trên mẫu khác bằng `--samples <file.jsonl> --output <thư_mục>`.

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

## Kết quả lần đo đầu

Đây là **đánh giá trên mẫu phát triển đã dùng xây tiêu chí**, không phải test độc lập. Không chỉnh luật sau lần đo này để che lỗi.

| Nhãn thủ công | Dự đoán accident | Dự đoán not_accident | Dự đoán uncertain |
|---|---:|---:|---:|
| accident (28) | 27 | 0 | 1 |
| not_accident (35) | 0 | 35 | 0 |
| uncertain (7) | 0 | 0 | 7 |

- Accuracy trên 63 mẫu có nhãn chắc chắn: 62/63 = **98,41%**. Dự đoán uncertain trên một mẫu chắc chắn tính là sai.
- Precision lớp accident: 27/27 = **100%** trên mẫu này.
- Recall lớp accident: 27/28 = **96,43%**; bản uncertain bị tính là bỏ sót.
- F1 lớp accident: **98,18%**.
- Khớp cả 3 nhãn trên 70 bài: 69/70 = **98,57%**. Bảy bài uncertain không được coi là mẫu âm để tính precision/recall nhị phân.

Bài bỏ sót `thanhnien:4`: “Xe taxi quyết không nhường đường ô tô đi ngược chiều, dẫn đến tai nạn đối đầu”. Lead dùng “lao thẳng vào”, trong khi mẫu luật chỉ nhận “lao vào”/“lao trúng”; tiêu đề “dẫn đến tai nạn” cũng chưa có trong nhánh sự kiện cụ thể. Kết quả là uncertain, không tự động chọn.

## Giới hạn trước khi dùng thật

Mẫu nhỏ, chọn có chủ đích và nhiều bài cùng một sự kiện Hải Phòng nên các kết quả không độc lập về sự kiện. Chưa chứng minh mức 98% trên feed mới. Không có mẫu ngẫu nhiên đủ lớn để ước lượng tỷ lệ tai nạn thực tế.

Luật từ vựng có thể nhầm phủ định, giả định chưa nằm trong danh sách, bài trộn nhiều tin, từ đồng nghĩa và quan hệ giữa phương tiện với tai nạn. Dùng câu đầu có thể bỏ mất bằng chứng hoặc cắt nhầm dấu chấm trong địa danh; chặn từ khóa chủ đề có thể loại nhầm bài xử phạt thực sự phát sinh từ tai nạn. Nhãn uncertain cần người xem lại.

Bước tiếp theo: khóa phiên bản v1, thu và gán nhãn bộ mới vào ngày khác, tránh trùng URL **và cùng vụ việc** với 70 mẫu này, rồi đo lại. Nếu sửa luật từ lỗi hiện tại thì tăng phiên bản và báo kết quả riêng; không gọi mẫu cũ là test độc lập.
