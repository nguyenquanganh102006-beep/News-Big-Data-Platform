# Phạm vi đã chốt — rules-v3-road

Người dùng xác nhận ngày 10/11/2026:

1. Chỉ giao thông đường bộ. Sự cố thuần đường thủy, đường sắt, hàng không ngoài
   phạm vi; va chạm tàu với phương tiện đường bộ tại giao cắt vẫn có đối tượng
   giao thông đường bộ.
2. Có tính cháy phương tiện trên đường dù không có va chạm.
3. Có tính cây, đá, công trình hoặc vật rơi đè phương tiện tham gia giao thông.
4. Có tính máy cày/xe công trình di chuyển trên đường hoặc qua cầu; sự cố thuần
   thi công trong công trường/nhà máy không phải giao thông đường bộ.
5. Không bắt buộc có người bị thương; phải là sự cố thật, không chỉ suýt va chạm.
6. Loại bài chỉ điều tra, khởi tố, cứu hộ hoặc khắc phục sau vụ việc. Bài tường
   thuật trực tiếp vụ tai nạn không bị loại chỉ vì mô tả có nhắc công an điều tra.

`uncertain` không còn có nghĩa là nhóm chưa quyết định phạm vi đường thủy/cháy xe.
Nó chỉ dùng khi dữ liệu chưa đủ áp dụng phạm vi, ví dụ “Xe tải bốc cháy” nhưng
không rõ đang trên đường hay trong nơi sửa chữa, hoặc “Cây đè ô tô” chưa rõ bối cảnh.
Không tự suy đoán nội dung toàn văn từ tiêu đề.

Đã cập nhật rule, các ca kiểm thử và nhãn giải thích trên dashboard. Bộ test
143/143 đạt, gồm integration streaming với Memurai. Phạm vi là chính sách đã chốt;
classifier từ khóa vẫn có thể sai và cần tiếp tục đánh giá trên bài mới.

Các tài liệu rules-v1/v2 và báo cáo kiểm chứng cũ ghi lại kết quả tại thời điểm
đó; số liệu cũ không tự đổi sau khi cập nhật chính sách. Dữ liệu chạy lại được
lưu riêng trong `data_artifacts/diagnostics/scope_road_*/` để chọn trên dashboard.
