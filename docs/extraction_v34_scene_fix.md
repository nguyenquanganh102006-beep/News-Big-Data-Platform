# Sửa trích xuất địa điểm hiện trường — v3.4

## Vấn đề và thay đổi

Một số bài có tỉnh trong văn bản nhưng bị chuyển review vì quy tắc ngữ cảnh quá hẹp. Bản sửa:

- Nhận tỉnh trong ngoặc sau tên cầu/quốc lộ có bằng chứng tai nạn; vẫn loại quê quán, biển số và hướng di chuyển.
- Mở rộng nhận diện dateline đầu body sang cháy xe, mất kiểm soát và các dạng diễn biến đã có trong cấu hình trích xuất.
- Bổ sung ngữ cảnh cháy xe, khi vừa qua địa điểm, sụp hố vào bước nhận tỉnh từ thân bài.
- Giữ nhận diện tham chiếu “khu vực trên thuộc…” và tìm địa điểm ở phần sau bài, thay vì giới hạn tám đoạn đầu.
- Tăng phiên bản extraction lên `rules-v3.4-scene-context`. A2 tự vô hiệu cache và dựng lại hai projection.

Không gán tỉnh dựa trên tên cao tốc, cơ quan công an hoặc địa danh quen thuộc khi chưa có bằng chứng hiện trường. Không tự chọn một tỉnh cho bài nhiều vụ hay ép địa điểm nước ngoài vào danh mục tỉnh Việt Nam.

## Kiểm chứng

Đối chiếu trước/sau trên toàn bộ 269 bài tai nạn của snapshot sau lượt crawl sáng 18/11/2026:

| Bài | Trước | Sau |
|---|---|---|
| Ôtô lao xuống hồ Trị An, hai vợ chồng thoát nạn | null | Đồng Nai |
| Nhiều người chạy tán loạn khi ô tô đầu kéo lao vào hiện trường vụ lật xe | null | Hà Tĩnh |
| Cháy xe container trên quốc lộ 51, giao thông ùn tắc kéo dài | null | Đồng Nai |
| Cầu sắt bất ngờ gãy đôi, máy cày chở xe cuốc rơi xuống kênh | null | Tây Ninh |

Không có bài nào đang nhận được tỉnh ở bộ trích xuất cũ bị mất tỉnh hoặc đổi tỉnh trong phép so sánh này. Đây là kiểm tra thay đổi trên tập hiện có, chưa phải đánh giá precision/recall độc lập cho toàn bộ trường thông tin.

235 tests: OK, 5 Redis integration tests opt-in bỏ qua. Test mới có các ca địa điểm thực tế, phản ví dụ quê quán/tên tuyến đường, tham chiếu hiện trường và địa điểm sau đoạn thứ tám.

Bằng chứng cục bộ:

- `data_artifacts/review_location_audit/extraction_v34_changes.json`
- `data_artifacts/extraction_v34_tests_final.log`
- `data_artifacts/a2_extraction_v34_live.log`

Thiếu thân bài vẫn cần crawler lấy thêm bằng chứng. Xác định được tỉnh không đồng nghĩa bài đã đủ điều kiện ghép vào một sự kiện; các cờ nhiều vụ, thiếu diễn biến hoặc matching chưa chắc chắn vẫn được giữ.

## Kết quả chạy lại thực tế

Cả hai kho đã được dựng lại và dịch vụ trở về `running`: 269 bài đầu vào matching, 199 sự kiện, 221 bài đã gắn, 48 bài chờ review (trước đó 52). Trong hàng chờ, số bài có `province_missing` giảm từ 45 xuống 39; thay đổi này còn bao gồm bằng chứng thân bài được fetch lại, không quy hết cho bốn quy tắc địa điểm. Đã kiểm tra trực tiếp bốn địa điểm sửa trong catalog xuất bản đều đúng tỉnh và có extraction version v3.4.
