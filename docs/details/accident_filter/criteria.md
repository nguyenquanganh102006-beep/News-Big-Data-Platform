# Tiêu chí lọc bài tai nạn giao thông — task 23

Bộ nhãn do trợ lý tự gán và các thống kê phụ thuộc vào bộ nhãn đó đã được loại bỏ. Các tiêu chí dưới đây là hướng dẫn thiết kế bộ lọc, chưa phải kết quả kiểm định chất lượng. Cách đánh giá bằng nhãn được kiểm duyệt: [rules_v1.md](rules_v1.md).

## Quyết định nhãn

Đơn vị phân loại là **bài báo**, không phải vụ việc. Nhiều bài hoặc nhiều nguồn về cùng vụ vẫn có thể được chọn; dedup URL không phải gộp sự kiện.

- `accident`: nội dung chính xác nhận một tai nạn cụ thể đã xảy ra, có phương tiện tham gia giao thông và diễn biến như va chạm, tông, cán, đâm vào vật cản, mất lái hoặc lật xe. Giữ cả bài điều tra, cứu hộ, cập nhật trực tiếp một vụ cụ thể.
- `not_accident`: nội dung chính không thuật lại một tai nạn giao thông cụ thể: quy định, tư vấn, thống kê, phòng ngừa, xử phạt chưa gây tai nạn, ùn tắc, công trình; hoặc là tai nạn sinh hoạt/lao động, hành vi tấn công mà chưa có bằng chứng va chạm giao thông.
- `uncertain`: thiếu bằng chứng hoặc thuộc phạm vi chưa chốt. Đưa vào hàng chờ xem xét, không tự động bỏ và không tự động nhập vào tập tai nạn chắc chắn.

Phạm vi chắc chắn của bản đầu: đường bộ, gồm xe đạp, xe máy, ô tô, người đi bộ bị phương tiện va chạm, và va chạm tàu hỏa–phương tiện đường bộ tại giao cắt. Tai nạn đường thủy, cháy xe không kèm va chạm và xe công trình đang làm việc được để `uncertain` chờ chốt phạm vi với chủ nhiệm task. Chưa có mẫu tai nạn hàng không để kết luận.

## Các tiêu chí rút ra từ bài thật

1. Phải có **sự kiện đã xảy ra**, không chỉ có từ “tai nạn”, “tử vong”, “xe” hay “đường”. Có thể không có từ “tai nạn” nhưng mô tả rõ cú tông/va chạm.
2. Không bắt buộc có người chết/bị thương hoặc con số thương vong. Dân Trí: “Ô tô lao vào xe bán bánh chuối chiên, 3 người thoát nạn trong gang tấc” là `accident`: xe thực sự đâm vào xe bán hàng và tường. Không suy ra số bị thương bằng 0 khi bài chưa xác nhận.
3. “Suýt” phải xét theo điều nó phủ định. Thanh Niên: “Suýt chết vì xe tải dừng, đỗ ngược chiều…” là `not_accident` vì chỉ suýt va chạm; trường hợp đã đâm nhưng người thoát chết vẫn là tai nạn. Không dùng “suýt” làm từ khóa loại tuyệt đối.
4. Câu hỏi tư vấn/giả định không phải sự kiện. “Ô tô va chạm nhẹ, không ai bị thương: Có được tự đưa xe vào lề?” là tư vấn tình huống, không có vụ cụ thể được xác nhận.
5. Không loại mọi bài có “xử lý”, “điều tra”, “rà soát”. Tuổi Trẻ: “Hải Phòng rà soát các ‘lò độ xe’ sau vụ tai nạn làm 4 người chết” vẫn được chọn vì cập nhật trực tiếp một vụ xác định. Xử phạt quay đầu xe trên cao tốc mà chưa xảy ra va chạm thì loại.
6. Không coi tai nạn có phương tiện là mặc định tai nạn giao thông. Công nhân bị kiện hàng rơi từ xe nâng trong nhà máy là tai nạn lao động. Xe múc lật khi tháo dỡ nhà gây tắc đường để `uncertain`, không tự nhận là tai nạn đang lưu thông.
7. “Đâm” có thể là tấn công bằng dao; “tử vong” có thể do điện giật; “trên đường” có thể là cây đổ hoặc trâu húc. Cần quan hệ giữa phương tiện đang tham gia giao thông và diễn biến tai nạn, không chỉ đồng xuất hiện từ khóa.
8. Thống kê nhiều vụ theo tháng và cảnh báo nguy cơ không phải bài về một vụ cụ thể. “Đồng Nai kéo giảm tai nạn giao thông sau một tháng…” là `not_accident`.
9. Không bắt buộc địa điểm cấp tỉnh/huyện hoặc ngày giờ đầy đủ để giữ bài. Thanh Niên có clip taxi thực sự đâm ô tô nhưng RSS chưa nêu rõ địa phương: vẫn chọn; bước trích xuất sau có thể trả địa điểm null.
10. Ưu tiên chủ đề chính của tiêu đề + phần mô tả chính. RSS VietnamPlus và Tiền Phong có chèn link bài liên quan: “Cầu Nhật Tân xuất hiện loạt biển báo…” có mô tả chứa “Ô tô lật ngửa…” nhưng chính bài là biển báo, nên loại. Khi viết bộ lọc cần tách link liên quan từ HTML trước khi ghép văn bản; không mặc định mọi liên kết là nhiễu vì một số nguồn bọc ảnh hoặc nội dung chính trong thẻ `a`.

## Kiểm duyệt và đánh giá

Người kiểm duyệt cần chốt phạm vi các trường hợp đường thủy, cháy xe và xe công trình trước khi gán nhãn. Tách dữ liệu đánh giá theo ngày và sự kiện khỏi dữ liệu dùng xây luật; không lấy dự đoán của bộ lọc làm nhãn chuẩn cho chính nó.
