# Đánh giá rules-v1 trên 414 bài

Giữ nguyên luật v1, không sửa luật sau khi xem kết quả. Nhãn tham chiếu do trợ lý đọc tiêu đề và mô tả RSS, chưa được người dùng xác nhận hoặc kiểm tra thân bài. Tập này chứa 70 mẫu dùng xây tiêu chí và nhiều bài cùng sự kiện; không phải test độc lập theo thời gian/sự kiện.

```powershell
.\.venv\Scripts\python.exe -m filters.evaluate --samples docs/details/accident_filter/reviewed_all_414.jsonl --output docs/details/accident_filter/evaluation_v1_414
```

| Nhãn tham chiếu | accident | not_accident | uncertain |
|---|---:|---:|---:|
| accident (30) | 28 | 0 | 2 |
| not_accident (375) | 0 | 375 | 0 |
| uncertain (9) | 0 | 1 | 8 |

- Accuracy trên 405 bài có nhãn chắc chắn: 403/405 = **99,51%**.
- Precision accident: 28/28 = **100%**.
- Recall accident: 28/30 = **93,33%** (2 bản uncertain tính là bỏ sót).
- F1 accident: **96,55%**.
- Khớp cả ba nhãn: 411/414 = **99,28%**.

Hai bài tai nạn chưa được chọn:

1. Dân Trí: “Tai nạn trên cao tốc TPHCM - Long Thành khiến phụ xe tử vong”. Luật chưa bắt cụm “Tai nạn trên”; mô tả dùng “vụ tai nạn giữa xe tải và xe đầu kéo” mà không chứa động từ va chạm trong danh sách.
2. Thanh Niên: “Xe taxi quyết không nhường đường ô tô đi ngược chiều, dẫn đến tai nạn đối đầu”. Thiếu mẫu “dẫn đến tai nạn” và “lao thẳng vào”.

Một bài cần xem xét bị loại: Dân Trí “Bốn ngư dân bám mũi ghe đang chìm, bật đèn tín hiệu cầu cứu giữa biển”. Luật chưa nhận dạng “ghe đang chìm” là trường hợp đường thủy chưa chốt phạm vi.

Không nên chỉ nhìn accuracy vì 375/405 bài chắc chắn là âm; luôn dự đoán not_accident cũng đạt 92,59% trên nhóm này. Chỉ số cần theo dõi chính khi lọc bài là precision và recall của accident. Kết quả này chưa đảm bảo chất lượng trên ngày/nguồn/sự kiện mới.

`metrics.json` chứa số liệu máy đọc được; `predictions.jsonl` chứa nhãn tham chiếu và kết quả cho từng bài.
