# Rà soát bổ sung các bài bị loại — 17/11/2026

## Kết luận

Không thể khẳng định toàn bộ phần còn lại không có bài tai nạn. Lần kiểm tra này xác nhận thêm **3 bài bị bỏ sót** sau lần rà trước. Đã sửa cách nhận diện và chạy lại trên **20.745 bài canonical**: **321 tai nạn, 33 cần xem xét, 20.391 không phải tai nạn**. Trước lần sửa bổ sung là 318/33/20.394.

Ba bài mới: ô tô va quệt gây kẹt đường Nguyễn Thị Thập; xe tải sụp hố trên đường Nguyễn Trãi; nhiều người đi xe máy ngã vì nhớt trên đường ở Quảng Ngãi. Danh sách kèm URL và căn cứ: [new_confirmed_misses.csv](../data_artifacts/filter_review_20261117/deep_audit/new_confirmed_misses.csv).

## Cách kiểm tra và giới hạn

- Quét máy toàn bộ 20.745 bài, cả nội dung hiện có, với mẫu sự cố/phương tiện độc lập và chuẩn hóa không dấu; không chỉ tìm từ “tai nạn”.
- Xếp hạng TF-IDF + mô hình tuyến tính để tìm bài gần các bài tai nạn đã đọc. Điểm chỉ phục vụ truy tìm, không phải xác suất hay thước đo độ chính xác độc lập.
- Sàng lọc tiêu đề của 1116 ứng viên khác nhau từ nhóm xếp hạng, tín hiệu tiêu đề, đoạn mở đầu và 100 ứng viên nội dung bổ sung; đọc mô tả/nội dung của các trường hợp đáng ngờ.
- Sàng lọc tiêu đề mẫu ngẫu nhiên 200 bài bị loại (seed 20261117), đọc sâu các trường hợp nghi vấn. Không tìm thêm vụ tường thuật đường bộ chắc chắn trong mẫu này. **Không phải đã đọc thủ công toàn văn cả 200 bài hoặc toàn bộ 20k bài.**
- Đã xem tiêu đề/mô tả 33 bài uncertain. Chưa có nhãn chuẩn độc lập cho toàn bộ dữ liệu, do đó không có cơ sở tuyên bố recall 100%.
- Một số bài chỉ có RSS, không có nội dung. Hai lần tải trang cây đè ô tô bị timeout; vẫn giữ cần xem xét. Bài cứu tài xế mắc lũ có chi tiết xe nghiêng trong nước cần phân định phạm vi. Xem `unresolved_context.csv`.
- Phạm vi theo người dùng: chỉ tin tường thuật vụ tai nạn đường bộ; loại bài thuần điều tra/khởi tố, thăm hỏi, tư vấn, thống kê và nhắc vụ cũ làm bối cảnh.

## Sửa đổi và xác minh

Bổ sung “va quệt”, “sụp/sụt/lọt hố”, “trượt ngã/té ngã”; giữ kiểm tra phương tiện/ngữ cảnh đường và các loại trừ chủ đề. Đối chiếu tất cả 20.745 bài với kết quả trước sửa: đúng 3 thay đổi not_accident → accident; không có thay đổi khác. Đã chạy 14 kiểm thử bộ lọc và 5 kiểm thử pipeline, đều đạt.

Kết quả và quyết định riêng trong `data_artifacts/filter_review_20261117/deep_audit/`; giữ bản trước sửa ở `before_deep_after_predictions.parquet` và `before_deep_comparison.json`. Chưa chạy lại Silver/Gold/Streaming hay công bố dashboard trong lượt kiểm tra này. Không dùng số đo trên tập đã chọn để tuyên bố độ chính xác toàn bộ dữ liệu.
