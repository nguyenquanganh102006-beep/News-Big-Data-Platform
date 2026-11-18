# Rà soát lý do thiếu tỉnh/thành trong hàng chờ review

Đối chiếu snapshot A2 sau lượt crawl sáng 18/11/2026: 52 bài pending review ở kho batch. Dữ liệu kiểm tra là tiêu đề, mô tả, thân bài thực tế đã lưu, trạng thái fetch, tỉnh được trích xuất và lý do review. Chưa xác minh lại toàn bộ 52 trang gốc trên Internet.

## Số liệu

- 45/52 bài có lý do `province_missing`; 7 bài còn lại chờ review vì diễn biến hoặc matching.
- Trong 45 bài đó, chỉ 4 bài không có thân bài; 41 bài có thân bài. Vì vậy thiếu thân bài không giải thích được phần lớn trường hợp.
- 20/45 bài đồng thời có cờ `multiple_events_in_article`. Nhiều bài là bản tin tổng hợp tai nạn theo ngày. Hệ thống chủ động để tỉnh null, nhưng dashboard vẫn hiển thị chung “Thiếu tỉnh/thành”. Cần rà độ đúng của cờ nhiều vụ trước khi tự tách hoặc tự gán tỉnh.
- Trong 25 bài không có cờ nhiều vụ: 4 bài thiếu thân bài; 12 bài nói về nước ngoài; 9 bài trong nước có thân bài nhưng chưa có tỉnh được chấp nhận.
- Tổng cả 52 bài: 8 bài thiếu thân bài, gồm cả các bài đã xác định được tỉnh nhưng thiếu diễn biến/bằng chứng matching.

## Các lỗi trích xuất tái hiện được

| Bài | Bằng chứng đã có trong dữ liệu | Kết quả hiện tại |
|---|---|---|
| Nhiều người chạy tán loạn khi ô tô đầu kéo lao vào hiện trường vụ lật xe | Mô tả ghi quốc lộ 8A (Hà Tĩnh); thân bài 1.090 ký tự | province null |
| Cháy xe container trên quốc lộ 51, giao thông ùn tắc kéo dài | Thân bài 974 ký tự ghi xã Phước Thái, Đồng Nai tại vị trí xe bắt đầu cháy | province null |
| Ôtô lao xuống hồ Trị An, hai vợ chồng thoát nạn | Thân bài 1.006 ký tự bắt đầu bằng dateline Đồng Nai | province null |
| Cầu sắt bất ngờ gãy đôi, máy cày chở xe cuốc rơi xuống kênh | Chưa có body nhưng mô tả đã ghi cầu Tân Thành (Tây Ninh) | province null |

Chạy lại trực tiếp `extract_accident` trên dữ liệu đang lưu vẫn trả null ở các trường hợp trên: đây là lỗi/giới hạn quy tắc trích xuất, không chỉ là kết quả cache cũ.

## Nguyên nhân trong code

`src/extractors/accident.py` dùng điều kiện ngữ cảnh chặt để tránh lấy nhầm tỉnh từ quê quán, biển số, tên tuyến đường hoặc cơ quan công an. Tuy nhiên:

- Các dạng tỉnh trong ngoặc sau tên cầu/quốc lộ có thể bị bỏ qua khi không khớp từ khóa ngữ cảnh.
- Dateline tỉnh đứng đầu body hiện chỉ được nhận với một số động từ; dạng “Đồng Nai Ôtô ... mất kiểm soát lao xuống hồ” không khớp.
- Khi lấy tỉnh từ body, danh sách động từ hiện trường chưa bao phủ đầy đủ cháy xe/bốc cháy.
- Bài nước ngoài vẫn đi vào nhánh matching dùng danh mục tỉnh Việt Nam, nên bị báo thiếu tỉnh thay vì một lý do địa lý riêng.
- Bài tổng hợp nhiều vụ cũng dùng chung nhãn thiếu tỉnh, dễ khiến người xem hiểu là crawler không tải được địa danh.

Không thể sửa bằng cách lấy bất kỳ tên tỉnh nào xuất hiện: “Hà Nội – Hải Phòng” có thể là tên cao tốc, “Khánh Hòa” có thể là biển số, “Đồng Nai” có thể là quê tài xế.

## Kết luận

Có cả lỗi fetch và lỗi trích xuất, nhưng phần lớn 45 trường hợp thiếu tỉnh đã có body. Cần sửa quy tắc nhận diện hiện trường và tách lý do review thành thiếu văn bản, chưa xác định được tỉnh hiện trường, bài nhiều vụ, và địa điểm nước ngoài. Chưa thay đổi code hay gán lại tỉnh trong đợt rà soát này.

Danh sách chi tiết cục bộ: `data_artifacts/review_location_audit/audit.json`.
