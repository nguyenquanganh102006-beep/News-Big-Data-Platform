# Tiêu chí lọc bài tai nạn giao thông — task 23

## Cập nhật: đã đọc đủ 414 bài

Đã mở rộng từ 70 mẫu có chủ đích sang toàn bộ 414 bài của đúng 3 lần crawl trong manifest: **30 accident, 375 not_accident, 9 uncertain**. Đọc tiêu đề và mô tả RSS của từng bài, không dùng rules-v1 để gán nhãn. Các nhãn của 70 bài cũ được đối chiếu theo nguồn + URL và giữ nguyên.

Xem [bảng đầy đủ 414 bài và danh sách được chọn](manual_review_414.md). `reviewed_all_414.jsonl` chứa văn bản bằng chứng, lý do, nhãn, snapshot và chỉ số đọc cho từng bài. `selected_accidents_30.jsonl` chỉ gồm 30 bài được chọn; `needs_review_9.jsonl` chứa 9 bài chưa chốt. Tổng hợp theo nguồn nằm ở `manual_review_summary.json`.

So với 70 mẫu cũ, phát hiện thêm 2 bài tai nạn của Dân Trí (tai nạn trên cao tốc TP.HCM–Long Thành và người đi xe đạp va chạm container), cùng 2 bài đường thủy cần chốt phạm vi. Các bài mới còn lại được gán not_accident theo chủ đề chính. Không coi nhiều bài cùng vụ là nhiều vụ tai nạn khác nhau.

“Thủ công” ở đây là trợ lý đọc và quyết định từ title + description, không phải con người xác nhận hoặc kiểm chứng ngoài đời, và chưa đọc thân bài. Bộ 414 vẫn cùng đợt crawl, có chứa 70 mẫu phát triển; không được gọi là test độc lập.

## Dữ liệu khảo sát

Chạy crawler RSS 3 lần liên tiếp, mỗi lần 410 bản tin từ 7 nguồn. Tổng cộng 1.230 dòng, gộp theo `(source, link)` còn 414 bài. Chi tiết tên snapshot và số dòng trong `crawl_manifest.json`. Các lần chạy gần nhau nên phần lớn bài giống nhau; đây chưa phải mẫu đại diện theo nhiều ngày.

Đọc và gán nhãn thủ công 70 bài có chủ đích, gồm bài rõ ràng và các trường hợp dễ nhầm: 28 `accident`, 35 `not_accident`, 7 `uncertain`. Không dùng keyword hay mô hình để tự gán nhãn. Nhãn dựa trên tiêu đề và mô tả RSS, không phải xác minh sự kiện ngoài đời hay đọc toàn bộ thân bài. Danh sách có URL, văn bản đã đọc, nhãn, lý do và snapshot trong `reviewed_samples.jsonl`. Chỉ 70 bài được gán nhãn, không suy diễn nhãn cho toàn bộ 414 bài.

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

## Trường hợp cần xem thêm

7 mẫu `uncertain` bao gồm cháy xe, chìm phà/tàu, tàu va cầu cảng và xe múc lật khi thi công. Cần chốt phạm vi nghiệp vụ trước khi đổi nhãn. Bài nhiều tin tổng hợp hoặc thiếu mô tả nên đưa vào `uncertain` khi chưa xác định được tai nạn là nội dung chính. Chưa gán nhãn cho loại nhiều tin trong bộ mẫu này.

## Dùng cho bước tiếp theo

Chưa có bộ lọc tự động và chưa thay đổi Silver/Gold. Có thể dùng mẫu này để thiết kế luật, nhưng không dùng chính mẫu thiết kế để báo cáo độ chính xác tổng quát. Cần thêm mẫu độc lập ở các ngày khác, bài không thương vong, bài nhiều sự kiện và mẫu âm khó trước khi nghiệm thu. Các tỷ lệ 28/35/7 là thành phần mẫu chọn có chủ đích, không phải tỷ lệ bài tai nạn trong feed hoặc precision/recall.
