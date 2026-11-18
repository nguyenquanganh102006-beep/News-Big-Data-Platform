# Tích hợp cơ chế 3.2–3.3 vào A2

Nguồn: `origin/task/32-33`, commit `468a444`. Branch tích hợp: `fix/gdd4-a2-event-matching`. Commit `62d34e3` lưu toàn bộ A2/dashboard/benchmark trước khi merge.

## Phần kết hợp

- Giữ kiến trúc Crawler → Bronze → Kafka → xử lý chung → Silver → streaming/batch → dashboard.
- Hai nhánh gọi chung `MatchingService` và thuật toán `hybrid-evidence-v3-scene-corroboration`.
- Matching bổ sung đối chiếu địa điểm cụ thể với diễn biến vụ việc, ví dụ sập cầu hoặc tai nạn liên hoàn có cùng số xe. Không tự ghép chỉ vì cùng tỉnh/ngày hoặc gần nhau về ngữ nghĩa.
- Giữ streaming 24h và batch 48h. Đối chiếu định danh trong profile theo thay đổi upstream 48h.
- Nhận các sửa lỗi trích xuất tỉnh/hiện trường/chi tiết vụ việc và lọc bài từ upstream.
- A2 cũng gọi bộ lấy thân bài upstream cho bài có khả năng tai nạn, giữ cache bằng chứng trong Silver. Không sửa Bronze hay fingerprint đầu vào. Nhãn review vẫn chỉ dùng khi fingerprint khớp; video được xác nhận thiếu thân bài không vào matching.
- Cache xử lý theo dõi cả mã matching và body-fetch để thay đổi thuật toán bắt buộc tái dựng hai projection và snapshot dashboard.
- Thống kê pipeline đếm riêng `skipped_video` để không thất thoát số dòng giữa các nhóm.

## Kiểm tra

Suite bao gồm các ca upstream về ghép sập cầu/tai nạn liên hoàn, phủ quyết khi khác địa điểm/ngày, trích xuất hiện trường và fetch body. Các test A2 bổ sung kiểm tra body đi vào extraction, được giữ khi tái sử dụng cache, fingerprint Bronze không đổi, và video thiếu body không vào matching kể cả có nhãn review dương tính.

Log chạy lại thực tế: `data_artifacts/a2_matching_v3_run.log`. Log tests: `data_artifacts/a2_merge_tests_final.log`. Kết quả hiện hành nằm ở `data_artifacts/dashboard_current.json`; báo cáo chuyển A2 trước đó là mốc lịch sử trước khi đổi matching.

Không xóa dữ liệu cũ. Không merge vào `main`. Dịch vụ Python được dừng an toàn để cập nhật rồi khởi động lại sau khi tái dựng kết quả.

## Kết quả kiểm chứng ngày 18/11/2026

- Chạy 230 tests: OK, 5 Redis integration tests bỏ qua theo cấu hình opt-in.
- Đã tính lại toàn bộ 21.049 URL từ 22.890 message Bronze, không nạp thêm bản trùng.
- Sau khử trùng: 21.037 bài, gồm 269 bài tai nạn, 33 bài chưa rõ phạm vi, 20.661 bài ngoài phạm vi và 74 trang video thiếu thân bài. Video vẫn được giữ riêng trong catalog.
- Cả streaming và batch hiện có 196 sự kiện, 217 bài đã gắn và 52 bài chờ review matching. Kết quả bằng nhau ở lần chạy này không có nghĩa hai nhánh luôn cho cùng kết quả.
- Đọc metadata trong cả hai DB đã xác nhận `hybrid-evidence-v3-scene-corroboration`; batch radius 48h, streaming radius 24h.
- AppTest kiểm tra cả hai lựa chọn kho trên dashboard: không có exception, cùng hiển thị 196 vụ, 151 tử vong và 120 bị thương đã ghi nhận. Đây là số liệu suy ra từ bằng chứng hiện có, không phải kết quả xác minh thủ công toàn bộ sự kiện.
- Dữ liệu thay đổi so với báo cáo A2 trước đó do đồng thời cập nhật matching, trích xuất hiện trường và bổ sung/kiểm tra thân bài; không quy toàn bộ chênh lệch cho riêng thuật toán matching.
