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
